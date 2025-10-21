#!/usr/bin/env python3
"""
YouTube Data Extraction via yt-dlp
Robust channel and video metadata extraction
"""

import re
import logging
from typing import Optional, Dict, List, Tuple
from time import sleep
from datetime import datetime

import yt_dlp


logger = logging.getLogger(__name__)


class YTDLPClient:
    """Client for YouTube data extraction via yt-dlp"""

    MAX_RETRIES = 3
    RETRY_DELAY_BASE = 10  # seconds

    DEFAULT_OPTIONS = {
        'quiet': True,
        'no_warnings': True,
        'extract_flat': False,
        'skip_download': True,
        'ignoreerrors': False,
        'no_check_certificate': True,
        'extractor_retries': 3,
    }

    def __init__(self):
        """Initialize yt-dlp client"""
        self.ydl_opts = self.DEFAULT_OPTIONS.copy()
        logger.debug("YTDLPClient initialized")

    def extract_channel_info(self, channel_input: str) -> Optional[Dict]:
        """
        Extract channel ID and name from any URL format

        Supports:
        - UC channel IDs: UCddiUEpeqJcYeBxX1IVBKvQ
        - @handles: @mkbhd
        - Channel URLs: youtube.com/channel/UC...
        - Custom URLs: youtube.com/c/LinusTechTips
        - User URLs: youtube.com/user/marquesbrownlee

        Returns:
        {
            'channel_id': 'UC...',
            'channel_name': 'Display Name',
            'channel_url': 'https://...'
        }
        """
        url = self._normalize_channel_url(channel_input)
        logger.debug(f"Extracting channel info from: {url}")

        for attempt in range(self.MAX_RETRIES):
            try:
                opts = self.ydl_opts.copy()
                opts['extract_flat'] = 'in_playlist'
                opts['playlistend'] = 1

                with yt_dlp.YoutubeDL(opts) as ydl:
                    info = ydl.extract_info(url, download=False)

                    if not info:
                        logger.warning(f"No info returned for: {channel_input}")
                        return None

                    channel_id = info.get('channel_id') or info.get('uploader_id')
                    channel_name = info.get('channel') or info.get('uploader')
                    channel_url = info.get('channel_url')

                    if channel_id:
                        logger.info(f"✓ Channel found: {channel_name} ({channel_id})")
                        return {
                            'channel_id': channel_id,
                            'channel_name': channel_name,
                            'channel_url': channel_url,
                        }
                    else:
                        logger.warning(f"No channel_id in response for: {channel_input}")
                        return None

            except yt_dlp.utils.DownloadError as e:
                error_str = str(e)
                if '429' in error_str or 'rate' in error_str.lower():
                    if attempt < self.MAX_RETRIES - 1:
                        delay = self.RETRY_DELAY_BASE * (2 ** attempt)
                        logger.warning(f"Rate limited, retrying in {delay}s (attempt {attempt+1}/{self.MAX_RETRIES})")
                        sleep(delay)
                        continue
                logger.error(f"yt-dlp download error: {e}")
                return None

            except Exception as e:
                logger.error(f"yt-dlp error extracting channel: {e}")
                return None

        logger.error(f"Max retries reached for: {channel_input}")
        return None

    def get_channel_videos(self, channel_id: str, max_videos: int = 5, skip_shorts: bool = True) -> List[Dict]:
        """
        Fetch recent videos from channel

        Returns: List of video metadata dicts
        """
        # Build channel URL
        if channel_id.startswith('@'):
            channel_url = f"https://www.youtube.com/{channel_id}/videos"
        else:
            channel_url = f"https://www.youtube.com/channel/{channel_id}/videos"

        logger.debug(f"Fetching videos from: {channel_url}")

        for attempt in range(self.MAX_RETRIES):
            try:
                opts = self.ydl_opts.copy()
                opts['playlistend'] = max_videos * 3  # Account for shorts
                opts['extract_flat'] = 'in_playlist'

                with yt_dlp.YoutubeDL(opts) as ydl:
                    info = ydl.extract_info(channel_url, download=False)

                    if not info or 'entries' not in info:
                        logger.debug(f"No entries for channel: {channel_id}")
                        return []

                    videos = []
                    for entry in info['entries']:
                        if not entry:
                            continue

                        # Skip shorts if configured
                        video_url = entry.get('url', '')
                        if skip_shorts and '/shorts/' in video_url:
                            logger.debug(f"Skipping short: {entry.get('title', 'Unknown')[:40]}")
                            continue

                        videos.append({
                            'id': entry['id'],
                            'title': entry.get('title', 'Unknown'),
                            'url': video_url,
                            'published': entry.get('upload_date', ''),
                        })

                        if len(videos) >= max_videos:
                            break

                    logger.debug(f"Found {len(videos)} videos")
                    return videos

            except Exception as e:
                if attempt < self.MAX_RETRIES - 1:
                    delay = self.RETRY_DELAY_BASE * (2 ** attempt)
                    logger.warning(f"Error fetching videos, retrying in {delay}s (attempt {attempt+1}/{self.MAX_RETRIES})")
                    sleep(delay)
                    continue
                logger.error(f"Failed to fetch videos: {e}")
                return []

        return []

    def get_video_metadata(self, video_id: str) -> Optional[Dict]:
        """
        Extract detailed video metadata

        Returns metadata dict with duration, views, upload_date, etc.
        """
        video_url = f"https://www.youtube.com/watch?v={video_id}"
        logger.debug(f"Fetching metadata for: {video_id}")

        for attempt in range(self.MAX_RETRIES):
            try:
                with yt_dlp.YoutubeDL(self.ydl_opts) as ydl:
                    info = ydl.extract_info(video_url, download=False)

                    if not info:
                        logger.warning(f"No metadata for: {video_id}")
                        return None

                    # Extract and format metadata
                    duration_sec = info.get('duration', 0)
                    duration_str = self._format_duration(duration_sec)

                    views = info.get('view_count', 0)
                    views_str = self._format_views(views)

                    upload_date = info.get('upload_date', '')
                    upload_date_str = self._format_upload_date(upload_date)

                    metadata = {
                        'id': info.get('id'),
                        'title': info.get('title'),
                        'url': info.get('webpage_url'),
                        'duration': duration_sec,
                        'duration_string': duration_str,
                        'view_count': views,
                        'view_count_string': views_str,
                        'upload_date': upload_date,
                        'upload_date_string': upload_date_str,
                        'description': info.get('description', ''),
                        'uploader': info.get('uploader'),
                        'channel_id': info.get('channel_id'),
                    }

                    logger.debug(f"✓ Metadata: {duration_str}, {views_str}")
                    return metadata

            except Exception as e:
                if attempt < self.MAX_RETRIES - 1:
                    delay = self.RETRY_DELAY_BASE * (2 ** attempt)
                    logger.warning(f"Error fetching metadata, retrying in {delay}s")
                    sleep(delay)
                    continue
                logger.error(f"Failed to get metadata for {video_id}: {e}")
                return None

        return None

    def get_subtitles(self, video_id: str) -> Optional[Tuple[str, str]]:
        """
        Extract subtitles/transcript via yt-dlp

        Supports multiple subtitle formats: JSON3, VTT, SRV (XML)
        Tries languages in order: German (de), English (en)
        Prefers manual subtitles over auto-generated

        Returns: (transcript_text, duration_string) or (None, None)
        """
        video_url = f"https://www.youtube.com/watch?v={video_id}"
        logger.debug(f"Attempting yt-dlp subtitle extraction for: {video_id}")

        try:
            opts = self.ydl_opts.copy()
            opts['writesubtitles'] = True
            opts['writeautomaticsub'] = True
            opts['subtitleslangs'] = ['de', 'en']  # Try German first, then English
            opts['skip_download'] = True

            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(video_url, download=False)

                if not info:
                    return None, None

                # Try to get subtitles data
                subtitles = info.get('subtitles', {})
                auto_subs = info.get('automatic_captions', {})

                # Try languages in order: de manual, en manual, de auto, en auto
                subs_data = None
                lang_used = None
                for lang in ['de', 'en']:
                    if subtitles.get(lang):
                        subs_data = subtitles[lang]
                        lang_used = lang
                        logger.debug(f"Using manual {lang} subtitles")
                        break
                    elif auto_subs.get(lang):
                        subs_data = auto_subs[lang]
                        lang_used = lang
                        logger.debug(f"Using auto-generated {lang} subtitles")
                        break

                if not subs_data:
                    logger.debug(f"No subtitles found for: {video_id}")
                    return None, None

                # Get duration
                duration_sec = info.get('duration', 0)
                duration_str = self._format_duration(duration_sec)

                # Parse subtitle data from the available formats
                transcript_text = self._parse_subtitle_data(subs_data)

                if transcript_text:
                    logger.info(f"✓ yt-dlp extracted transcript ({len(transcript_text)} chars, {lang_used})")
                    return transcript_text, duration_str
                else:
                    logger.debug(f"Failed to parse subtitle data for {video_id}")
                    return None, None

        except Exception as e:
            logger.error(f"yt-dlp subtitle extraction failed for {video_id}: {e}")
            return None, None

    # Helper methods

    def _parse_subtitle_data(self, subs_data: List[Dict]) -> Optional[str]:
        """
        Parse subtitle data from yt-dlp subtitle formats

        Args:
            subs_data: List of subtitle format dicts with 'url' and 'ext' keys

        Returns:
            Concatenated transcript text or None
        """
        import urllib.request

        # Try to find a JSON3 format first (easiest to parse), then VTT, then SRT
        preferred_formats = ['json3', 'vtt', 'srv3', 'srv2', 'srv1']

        selected_format = None
        for fmt in preferred_formats:
            for sub_format in subs_data:
                if sub_format.get('ext') == fmt:
                    selected_format = sub_format
                    break
            if selected_format:
                break

        # If no preferred format, just use the first one
        if not selected_format and subs_data:
            selected_format = subs_data[0]

        if not selected_format or 'url' not in selected_format:
            return None

        try:
            # Download subtitle data
            url = selected_format['url']
            ext = selected_format.get('ext', 'unknown')

            logger.debug(f"Downloading subtitle format: {ext} from {url[:100]}...")

            with urllib.request.urlopen(url, timeout=30) as response:
                content = response.read().decode('utf-8')

            # Parse based on format
            if ext == 'json3':
                return self._parse_json3_subtitles(content)
            elif ext == 'vtt':
                return self._parse_vtt_subtitles(content)
            elif ext in ['srv1', 'srv2', 'srv3']:
                return self._parse_srv_subtitles(content)
            else:
                # Try VTT parser as fallback
                return self._parse_vtt_subtitles(content)

        except Exception as e:
            logger.debug(f"Failed to download/parse subtitles: {e}")
            return None

    def _parse_json3_subtitles(self, content: str) -> Optional[str]:
        """Parse YouTube JSON3 subtitle format"""
        import json

        try:
            data = json.loads(content)
            events = data.get('events', [])

            text_parts = []
            for event in events:
                if 'segs' in event:
                    for seg in event['segs']:
                        if 'utf8' in seg:
                            text_parts.append(seg['utf8'])

            return ' '.join(text_parts).strip()
        except Exception as e:
            logger.debug(f"JSON3 parsing failed: {e}")
            return None

    def _parse_vtt_subtitles(self, content: str) -> Optional[str]:
        """Parse WebVTT subtitle format"""
        import re

        try:
            # Remove VTT header and timing lines
            lines = content.split('\n')
            text_parts = []

            for line in lines:
                line = line.strip()
                # Skip empty lines, WEBVTT header, and timestamp lines
                if not line or line.startswith('WEBVTT') or '-->' in line:
                    continue
                # Skip cue identifiers (numbers or NOTE lines)
                if line.isdigit() or line.startswith('NOTE'):
                    continue
                # Skip styling tags
                if line.startswith('<') and line.endswith('>'):
                    continue

                # Remove HTML-style tags from text
                clean_line = re.sub(r'<[^>]+>', '', line)
                if clean_line:
                    text_parts.append(clean_line)

            return ' '.join(text_parts).strip()
        except Exception as e:
            logger.debug(f"VTT parsing failed: {e}")
            return None

    def _parse_srv_subtitles(self, content: str) -> Optional[str]:
        """Parse YouTube SRV (XML) subtitle format"""
        import re

        try:
            # Extract text from <text> tags
            text_pattern = r'<text[^>]*>(.*?)</text>'
            matches = re.findall(text_pattern, content, re.DOTALL)

            text_parts = []
            for match in matches:
                # Remove HTML entities and extra whitespace
                clean_text = match.replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>')
                clean_text = clean_text.replace('&#39;', "'").replace('&quot;', '"')
                clean_text = re.sub(r'\s+', ' ', clean_text).strip()
                if clean_text:
                    text_parts.append(clean_text)

            return ' '.join(text_parts).strip()
        except Exception as e:
            logger.debug(f"SRV parsing failed: {e}")
            return None

    def _normalize_channel_url(self, channel_input: str) -> str:
        """Convert any channel input to a valid YouTube URL"""
        # Already a URL
        if channel_input.startswith('http'):
            # Ensure /videos suffix for better results
            if '/videos' not in channel_input:
                channel_input = channel_input.rstrip('/') + '/videos'
            return channel_input

        # @handle
        if channel_input.startswith('@'):
            return f"https://www.youtube.com/{channel_input}/videos"

        # UC channel ID
        if re.match(r'^UC[\w-]{22}$', channel_input):
            return f"https://www.youtube.com/channel/{channel_input}/videos"

        # Fallback: treat as handle
        return f"https://www.youtube.com/@{channel_input}/videos"

    def _format_duration(self, seconds: int) -> str:
        """Format seconds to human-readable duration"""
        if not seconds:
            return "Unknown"

        if seconds < 60:
            return f"{seconds}s"
        elif seconds < 3600:
            mins = seconds // 60
            secs = seconds % 60
            return f"{mins}m {secs}s"
        else:
            hours = seconds // 3600
            mins = (seconds % 3600) // 60
            secs = seconds % 60
            if secs > 0:
                return f"{hours}h {mins}m {secs}s"
            else:
                return f"{hours}h {mins}m"

    def _format_views(self, views: int) -> str:
        """Format view count to human-readable string"""
        if not views:
            return "Unknown views"

        if views < 1000:
            return f"{views:,} views"
        elif views < 1_000_000:
            return f"{views/1000:.1f}K views"
        else:
            return f"{views/1_000_000:.1f}M views"

    def _format_upload_date(self, upload_date: str) -> str:
        """Format YYYYMMDD to YYYY-MM-DD"""
        if not upload_date or len(upload_date) != 8:
            return "Unknown"

        try:
            # Parse and format
            dt = datetime.strptime(upload_date, '%Y%m%d')
            return dt.strftime('%Y-%m-%d')
        except:
            return upload_date
