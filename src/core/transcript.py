#!/usr/bin/env python3
"""
YouTube Transcript Extraction
Supports multiple providers: legacy (youtube-transcript-api) and Supadata.ai
"""

import html
import os
import logging
import random
import time
from typing import Any, Dict, List, Optional, Tuple

from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import (
    TranscriptsDisabled,
    NoTranscriptFound,
    VideoUnavailable,
    IpBlocked,
    RequestBlocked,
)


logger = logging.getLogger(__name__)


class TranscriptExtractor:
    """Extract transcripts from YouTube videos using youtube-transcript-api."""

    DEFAULT_LANGUAGES = ["en", "en-US", "en-GB", "de", "de-DE"]
    DEFAULT_ALLOW_AUTO = True
    DEFAULT_MAX_RETRIES = 3
    DEFAULT_BACKOFF_BASE = 2  # seconds
    DEFAULT_BACKOFF_CAP = 30  # seconds
    CACHE_SKIP_STATUSES = {"disabled", "not_found", "video_unavailable"}

    def __init__(
        self,
        provider: str = "legacy",  # "legacy" or "supadata"
        supadata_api_key: Optional[str] = None,
        preferred_languages: Optional[List[str]] = None,
        allow_auto_generated: bool = DEFAULT_ALLOW_AUTO,
        max_retries: int = DEFAULT_MAX_RETRIES,
        backoff_base: int = DEFAULT_BACKOFF_BASE,
        backoff_cap: int = DEFAULT_BACKOFF_CAP,
        cache: Optional[Any] = None,
        cookies: Optional[str] = None,
        proxy_url: Optional[str] = None,
    ):
        """
        Initialize TranscriptExtractor with configurable provider.

        Args:
            provider: Either "legacy" (youtube-transcript-api) or "supadata" (Supadata.ai)
            supadata_api_key: API key for Supadata.ai (required if provider="supadata")
            preferred_languages: List of language codes in order of preference
            allow_auto_generated: Whether to use auto-generated transcripts as fallback
            max_retries: Maximum number of retry attempts
            backoff_base: Base delay for exponential backoff (seconds)
            backoff_cap: Maximum delay for exponential backoff (seconds)
            cache: Cache instance for storing unavailable video status
            cookies: YouTube cookies for authentication
            proxy_url: Proxy URL for requests
        """
        self.provider = provider
        self.supadata_client = None

        # Initialize Supadata client if provider is supadata
        if provider == "supadata":
            if not supadata_api_key:
                raise ValueError("supadata_api_key is required when using Supadata provider")
            try:
                from supadata import Supadata
                self.supadata_client = Supadata(api_key=supadata_api_key)
                logger.info("Initialized Supadata client successfully")
            except ImportError:
                raise ImportError(
                    "Supadata package not installed. Run: pip install supadata"
                )
            except Exception as e:
                logger.error("Failed to initialize Supadata client: %s", e)
                raise

        self.preferred_languages = (
            [lang.strip() for lang in preferred_languages if lang.strip()]
            if preferred_languages
            else self.DEFAULT_LANGUAGES
        )
        self.allow_auto_generated = allow_auto_generated
        self.max_retries = max(1, max_retries)
        self.backoff_base = max(1, backoff_base)
        self.backoff_cap = max(self.backoff_base, backoff_cap)
        self.cache = cache

        # Optional cookies/proxy support (helps with consent/age/region issues)
        env_cookies = os.getenv("TRANSCRIPT_COOKIES")
        env_cookies_file = os.getenv("TRANSCRIPT_COOKIES_FILE")
        self.cookies: Optional[str] = cookies or env_cookies
        if not self.cookies and env_cookies_file and os.path.exists(env_cookies_file):
            try:
                with open(env_cookies_file, "r", encoding="utf-8", errors="ignore") as f:
                    self.cookies = f.read().strip() or None
            except Exception:
                # Non-fatal; proceed without cookies
                self.cookies = None

        env_proxy = os.getenv("TRANSCRIPT_PROXY_URL")
        proxy_url = proxy_url or env_proxy
        self.proxies = None
        if proxy_url:
            self.proxies = {"http": proxy_url, "https": proxy_url}

        # Initialize the API client instance (for v1.2.3+)
        self.api = YouTubeTranscriptApi()

        logger.debug(
            "TranscriptExtractor initialized (provider=%s, languages=%s, allow_auto=%s, retries=%s, cache=%s)",
            self.provider,
            self.preferred_languages,
            self.allow_auto_generated,
            self.max_retries,
            bool(self.cache),
        )

    def get_transcript(self, video_id: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """
        Fetch transcript text and derived duration for a YouTube video.
        Routes to appropriate provider (legacy or supadata) based on configuration.

        Args:
            video_id: YouTube video ID

        Returns:
            Tuple of (transcript_text, duration, method_used) or (None, None, None) if unavailable
            method_used will be one of: 'youtube-transcript-api', 'supadata', or None
        """
        # Check cache first (applies to both providers)
        cached = self._get_cached_status(video_id)
        if cached:
            logger.debug(
                "Transcript cache hit for %s (status=%s) — skipping fetch",
                video_id,
                cached.get('status'),
            )
            return None, None, None

        # Route to appropriate provider
        if self.provider == "supadata":
            text, duration = self._get_transcript_supadata(video_id)
            return text, duration, 'supadata' if text else None
        else:
            text, duration = self._get_transcript_legacy(video_id)
            return text, duration, 'youtube-transcript-api' if text else None

    def _get_transcript_legacy(self, video_id: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Original implementation using youtube-transcript-api.

        Args:
            video_id: YouTube video ID

        Returns:
            Tuple of (transcript_text, duration) or (None, None) if unavailable
        """
        for attempt in range(self.max_retries):
            try:
                transcript_text, duration = self._fetch_transcript(video_id)
                if transcript_text:
                    self._clear_cache(video_id)
                    logger.info("✓ Transcript extracted for %s", video_id)
                    return transcript_text, duration

                logger.debug("No transcript returned for %s", video_id)
                return None, None

            except TranscriptsDisabled:
                logger.info("Transcripts disabled for %s", video_id)
                self._cache_unavailable(video_id, "disabled", "Transcripts disabled by uploader")
                break
            except VideoUnavailable:
                logger.info("Video unavailable for transcript: %s", video_id)
                self._cache_unavailable(video_id, "video_unavailable", "Video unavailable")
                break
            except NoTranscriptFound:
                logger.info("No transcript found for %s in preferred languages", video_id)
                self._cache_unavailable(video_id, "not_found", "No transcripts in preferred languages")
                break
            except (IpBlocked, RequestBlocked) as exc:
                # YouTube is blocking our IP - don't cache this as it's temporary
                logger.warning(
                    "YouTube blocked request for %s: %s. Retrying in %.1fs (attempt %s/%s)",
                    video_id,
                    type(exc).__name__,
                    self._compute_backoff_delay(attempt),
                    attempt + 1,
                    self.max_retries,
                )
                time.sleep(self._compute_backoff_delay(attempt))
            except Exception as exc:  # Broad catch to log unexpected failures
                # Check if this is a rate limiting error (HTTP 429)
                error_str = str(exc).lower()
                is_rate_limit = '429' in error_str or 'too many requests' in error_str or 'rate limit' in error_str

                delay = self._compute_backoff_delay(attempt)

                if is_rate_limit:
                    logger.warning(
                        "Rate limited fetching transcript for %s. Retrying in %.1fs (attempt %s/%s)",
                        video_id,
                        delay,
                        attempt + 1,
                        self.max_retries,
                    )
                else:
                    logger.warning(
                        "Unexpected error fetching transcript for %s: %s. Retrying in %.1fs",
                        video_id,
                        exc,
                        delay,
                    )
                time.sleep(delay)

        logger.debug("Transcript extraction exhausted retries for %s", video_id)
        return None, None

    def _get_transcript_supadata(self, video_id: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Fetch transcript via Supadata.ai API.

        Args:
            video_id: YouTube video ID

        Returns:
            Tuple of (transcript_text, duration) or (None, None) if unavailable
        """
        if not self.supadata_client:
            logger.error("Supadata client not initialized")
            return None, None

        for attempt in range(self.max_retries):
            try:
                logger.debug("Fetching transcript via Supadata for %s (attempt %s/%s)",
                           video_id, attempt + 1, self.max_retries)

                # Call Supadata API with first preferred language
                result = self.supadata_client.youtube.transcript(
                    video_id=video_id,
                    lang=self.preferred_languages[0] if self.preferred_languages else "en",
                    text=True,  # Get plain text format
                    mode="native"  # Use existing YouTube transcripts only (no AI generation)
                )

                # Extract transcript text from result
                transcript_text = result.content if hasattr(result, 'content') else str(result)

                if not transcript_text:
                    logger.debug("No transcript returned from Supadata for %s", video_id)
                    return None, None

                # Get duration using existing ytdlp infrastructure
                duration = self._get_duration_from_ytdlp(video_id)

                # Clear any previous cache and log success
                self._clear_cache(video_id)
                logger.info("✓ Transcript extracted via Supadata for %s", video_id)

                return transcript_text, duration

            except Exception as e:
                error_str = str(e).lower()
                error_type = getattr(e, 'error', None)

                # Map Supadata errors to existing cache logic
                if "transcript_not_available" in error_str or error_type == "TRANSCRIPT_NOT_AVAILABLE":
                    logger.info("No transcript available via Supadata for %s", video_id)
                    self._cache_unavailable(video_id, "not_found", "No transcript available")
                    break
                elif "video_unavailable" in error_str or error_type == "VIDEO_UNAVAILABLE":
                    logger.info("Video unavailable via Supadata for %s", video_id)
                    self._cache_unavailable(video_id, "video_unavailable", "Video unavailable")
                    break
                elif "rate" in error_str or "429" in error_str or "quota" in error_str:
                    # Rate limiting - retry with backoff
                    delay = self._compute_backoff_delay(attempt)
                    logger.warning(
                        "Supadata rate limit for %s. Retrying in %.1fs (attempt %s/%s)",
                        video_id, delay, attempt + 1, self.max_retries
                    )
                    time.sleep(delay)
                else:
                    # Unexpected error - retry
                    delay = self._compute_backoff_delay(attempt)
                    logger.warning(
                        "Supadata error for %s: %s. Retrying in %.1fs (attempt %s/%s)",
                        video_id, e, delay, attempt + 1, self.max_retries
                    )
                    time.sleep(delay)

        logger.debug("Supadata transcript extraction exhausted retries for %s", video_id)
        return None, None

    def _get_duration_from_ytdlp(self, video_id: str) -> Optional[str]:
        """
        Get video duration using existing ytdlp client.
        This reuses the existing infrastructure for metadata extraction.

        Args:
            video_id: YouTube video ID

        Returns:
            Duration string in H:MM:SS or M:SS format, or None if unavailable
        """
        try:
            # Import the YtDlpClient to get duration
            from src.core.ytdlp_client import YtDlpClient

            client = YtDlpClient()
            video_url = f"https://www.youtube.com/watch?v={video_id}"

            # Extract metadata without downloading
            info = client.extract_info(video_url, download=False)

            if info and 'duration' in info:
                return self._format_duration(info['duration'])

        except Exception as e:
            logger.debug("Failed to get duration via ytdlp for %s: %s", video_id, e)

        return None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _fetch_transcript(self, video_id: str) -> Tuple[Optional[str], Optional[str]]:
        """Fetch transcript using manual-first then language-priority fallbacks."""
        transcript = self._select_transcript(video_id)
        if not transcript:
            # Fallback: try direct API call which may succeed with cookies/proxy
            try:
                segments = self._direct_get_transcript(video_id)
            except Exception as exc:  # Defensive logging only
                logger.debug("Direct transcript fetch failed for %s: %s", video_id, exc)
                segments = None

            if not segments:
                return None, None

            cleaned_text = self._segments_to_text(segments)
            duration_seconds = self._estimate_duration(segments)
            return cleaned_text, self._format_duration(duration_seconds)

        segments = transcript.fetch()
        if not segments:
            return None, None

        cleaned_text = self._segments_to_text(segments)
        duration_seconds = self._estimate_duration(segments)

        return cleaned_text, self._format_duration(duration_seconds)

    def _select_transcript(self, video_id: str):
        """Select the best transcript honoring manual preference and language fallbacks."""
        # Use instance method with new API (v1.2.3+)
        transcript_list = self.api.list(video_id)

        # Build list of available transcripts
        all_transcripts = []
        try:
            # Try to get manually created transcripts
            for lang in self.preferred_languages:
                try:
                    transcript = transcript_list.find_manually_created_transcript([lang])
                    all_transcripts.append(transcript)
                except:
                    pass
        except:
            pass

        # Get auto-generated transcripts if allowed
        auto_transcripts = []
        if self.allow_auto_generated:
            try:
                for lang in self.preferred_languages:
                    try:
                        transcript = transcript_list.find_generated_transcript([lang])
                        auto_transcripts.append(transcript)
                    except:
                        pass
            except:
                pass

        # Prefer manual transcripts over auto-generated
        if all_transcripts:
            return all_transcripts[0]

        if auto_transcripts:
            logger.debug("Using auto-generated transcript fallback for %s", video_id)
            return auto_transcripts[0]

        # Final fallback: try to find any transcript
        try:
            return transcript_list.find_transcript(self.preferred_languages)
        except:
            pass

        return None

    def _direct_get_transcript(self, video_id: str) -> Optional[List[dict]]:
        """Attempt a direct fetch call using the API instance.

        This can succeed in scenarios where listing tracks fails due to consent/region.
        """
        # Try to fetch directly with preferred languages
        try:
            fetched = self.api.fetch(video_id, languages=tuple(self.preferred_languages))
            return fetched.fetch()
        except Exception as e:
            logger.debug("Direct fetch failed for %s: %s", video_id, e)
            return None

    def _pick_by_priority(self, transcripts: List[Any]) -> Optional[Any]:
        """Return the first transcript whose language matches preferred order."""
        if not transcripts or not self.preferred_languages:
            return None

        priority = [lang.lower() for lang in self.preferred_languages]
        for lang in priority:
            for transcript in transcripts:
                code = (transcript.language_code or "").lower()
                if code == lang:
                    return transcript
        return None

    @staticmethod
    def _segments_to_text(segments: List[dict]) -> str:
        """Join transcript segments into cleaned plaintext."""
        cleaned_parts: List[str] = []

        for segment in segments:
            # Handle both dict and object formats
            if hasattr(segment, 'text'):
                text = segment.text.strip() if segment.text else ""
            else:
                text = segment.get("text", "").strip()

            if not text:
                continue

            # Remove common bracketed stage directions while keeping inline content
            if text.startswith("[") and text.endswith("]"):
                lowered = text[1:-1].strip().lower()
                if lowered in {"music", "applause", "laughter", "silence", "background music"}:
                    continue

            cleaned_parts.append(html.unescape(text))

        combined = " ".join(cleaned_parts)
        return " ".join(combined.split())  # Normalize whitespace

    @staticmethod
    def _estimate_duration(segments: List[dict]) -> Optional[float]:
        """Estimate total transcript duration from the last segment."""
        if not segments:
            return None

        last_segment = segments[-1]
        # Handle both dict and object formats
        if hasattr(last_segment, 'start'):
            start = float(last_segment.start) if last_segment.start else 0
            duration = float(last_segment.duration) if last_segment.duration else 0
        else:
            start = float(last_segment.get("start", 0))
            duration = float(last_segment.get("duration", 0))

        total_seconds = start + duration
        return total_seconds if total_seconds > 0 else None

    def _compute_backoff_delay(self, attempt: int) -> float:
        """Compute exponential backoff with jitter for retry attempts."""
        exponent = min(self.backoff_cap, self.backoff_base * (2 ** attempt))
        jitter = random.uniform(0, self.backoff_base)
        return min(self.backoff_cap, exponent + jitter)

    @staticmethod
    def _format_duration(total_seconds: Optional[float]) -> Optional[str]:
        """Format second count into H:MM:SS string used by downstream prompts."""
        if not total_seconds:
            return None

        total_seconds = int(total_seconds)
        hours, remainder = divmod(total_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)

        if hours:
            return f"{hours}:{minutes:02d}:{seconds:02d}"
        return f"{minutes}:{seconds:02d}"

    def _get_cached_status(self, video_id: str) -> Optional[Dict[str, Any]]:
        """Lookup cached transcript status for a video."""
        cache = self.cache
        if not cache or not hasattr(cache, "get_transcript_cache"):
            return None

        try:
            entry = cache.get_transcript_cache(video_id)
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.debug("Transcript cache lookup failed for %s: %s", video_id, exc)
            return None

        if entry and entry.get("status") in self.CACHE_SKIP_STATUSES:
            return entry

        return None

    def _cache_unavailable(self, video_id: str, status: str, reason: str) -> None:
        """Persist unavailability result to avoid redundant fetches."""
        cache = self.cache
        if not cache or not hasattr(cache, "set_transcript_cache"):
            return

        try:
            cache.set_transcript_cache(video_id, status, reason)
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.debug("Failed to store transcript cache for %s: %s", video_id, exc)

    def _clear_cache(self, video_id: str) -> None:
        """Clear cached transcript status after a successful fetch."""
        cache = self.cache
        if not cache or not hasattr(cache, "clear_transcript_cache"):
            return

        try:
            cache.clear_transcript_cache(video_id)
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.debug("Failed to clear transcript cache for %s: %s", video_id, exc)

    # ------------------------------------------------------------------
    # Multi-fallback cascade
    # ------------------------------------------------------------------

    def get_transcript_cascade(self, video_id: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """
        Try 4 methods in sequence until one succeeds.
        Clean, simple cascade with detailed logging.

        Args:
            video_id: YouTube video ID

        Returns:
            Tuple of (transcript_text, duration, method_used) or (None, None, None) if all methods fail
            method_used will be one of: 'youtube-transcript-api', 'yt-dlp', 'timedtext', 'supadata', or None
        """
        # Check cache first
        cached = self._get_cached_status(video_id)
        if cached:
            logger.debug(
                "Transcript cache hit for %s (status=%s) — skipping fetch",
                video_id,
                cached.get('status'),
            )
            return None, None, None

        methods = [
            ('youtube-transcript-api', 'youtube-transcript-api', self._method_1_youtube_api),
            ('yt-dlp subtitles', 'yt-dlp', self._method_2_ytdlp),
            ('timedtext API', 'timedtext', self._method_3_timedtext),
            ('Supadata', 'supadata', self._method_4_supadata),
        ]

        for i, (display_name, method_name, method_func) in enumerate(methods, 1):
            logger.info(f"📝 Method {i}/4: {display_name}...")
            try:
                result = method_func(video_id)
                if result and result[0]:  # (text, duration)
                    logger.info(f"✅ Success via {display_name}")
                    self._clear_cache(video_id)
                    return result[0], result[1], method_name
                else:
                    logger.debug(f"   Method {i} returned no transcript")
            except Exception as e:
                logger.debug(f"   Method {i} failed: {e}")
                continue

        logger.info("❌ All 4 methods exhausted")
        return None, None, None

    def _method_1_youtube_api(self, video_id: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Method 1: youtube-transcript-api (existing implementation)
        Reuses existing _get_transcript_legacy logic
        """
        return self._get_transcript_legacy(video_id)

    def _method_2_ytdlp(self, video_id: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Method 2: Extract subtitles via yt-dlp
        Tries manual transcripts first, then auto-generated
        """
        import yt_dlp

        url = f"https://www.youtube.com/watch?v={video_id}"
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'skip_download': True,
            'writesubtitles': True,
            'writeautomaticsub': True,
            'subtitleslangs': self.preferred_languages,
            'socket_timeout': 30,
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)

            # Try manual subtitles first
            for lang in self.preferred_languages:
                if info.get('subtitles', {}).get(lang):
                    for fmt in info['subtitles'][lang]:
                        if fmt.get('ext') in ['json3', 'srv3']:
                            text = self._fetch_subtitle_json3(fmt['url'])
                            if text:
                                logger.debug(f"   Found manual subtitle in {lang}")
                                duration = self._format_duration(info.get('duration', 0))
                                return text, duration

            # Try auto-generated captions
            for lang in self.preferred_languages:
                if info.get('automatic_captions', {}).get(lang):
                    for fmt in info['automatic_captions'][lang]:
                        if fmt.get('ext') in ['json3', 'srv3']:
                            text = self._fetch_subtitle_json3(fmt['url'])
                            if text:
                                logger.debug(f"   Found auto caption in {lang}")
                                duration = self._format_duration(info.get('duration', 0))
                                return text, duration

            return None, None

        except Exception as e:
            logger.debug(f"   yt-dlp extraction failed: {e}")
            return None, None

    def _fetch_subtitle_json3(self, url: str) -> Optional[str]:
        """
        Fetch and parse JSON3 subtitle format from yt-dlp
        """
        import requests

        try:
            r = requests.get(url, timeout=30)
            if r.status_code == 200:
                data = r.json()
                if 'events' in data:
                    texts = []
                    for event in data['events']:
                        if 'segs' in event:
                            for seg in event['segs']:
                                if 'utf8' in seg:
                                    texts.append(seg['utf8'])
                    text = ' '.join(texts).strip()
                    # Clean up whitespace
                    return ' '.join(text.split()) if text else None
        except Exception as e:
            logger.debug(f"   JSON3 parsing failed: {e}")

        return None

    def _method_3_timedtext(self, video_id: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Method 3: Direct YouTube timedtext API scraping
        Simple XML parsing approach
        """
        import requests
        from bs4 import BeautifulSoup

        for lang in self.preferred_languages:
            url = f"https://www.youtube.com/api/timedtext?v={video_id}&lang={lang}"
            try:
                r = requests.get(url, timeout=30)
                if r.status_code == 200 and r.text and '<transcript>' in r.text:
                    soup = BeautifulSoup(r.text, 'xml')
                    texts = [tag.get_text() for tag in soup.find_all('text')]
                    if texts:
                        full_text = ' '.join(texts)
                        # Clean up whitespace
                        full_text = ' '.join(full_text.split())
                        logger.debug(f"   Found timedtext in {lang}")
                        return full_text, None
            except Exception as e:
                logger.debug(f"   timedtext API ({lang}) failed: {e}")
                continue

        return None, None

    def _method_4_supadata(self, video_id: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Method 4: Supadata API (existing implementation)
        Reuses existing _get_transcript_supadata logic
        """
        if self.provider != 'supadata' and not self.supadata_client:
            # Skip if Supadata not configured
            logger.debug("   Supadata not configured, skipping")
            return None, None

        return self._get_transcript_supadata(video_id)
