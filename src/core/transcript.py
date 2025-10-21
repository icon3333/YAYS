#!/usr/bin/env python3
"""
YouTube Transcript Extraction
Uses yt-dlp for robust transcript fetching
"""

import logging
from typing import Optional, Tuple

from src.core.ytdlp_client import YTDLPClient


logger = logging.getLogger(__name__)


class TranscriptExtractor:
    """Extracts transcripts from YouTube videos using yt-dlp"""

    def __init__(self):
        """Initialize with yt-dlp client"""
        self.ytdlp = YTDLPClient()
        logger.debug("TranscriptExtractor initialized with yt-dlp")

    def get_transcript(self, video_id: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Fetch transcript for video using yt-dlp

        Tries languages in order: German (de), English (en)
        Prefers manual subtitles over auto-generated

        Returns (transcript_text, duration_string) or (None, None)
        """
        logger.debug(f"Extracting transcript for {video_id} using yt-dlp")

        result = self.ytdlp.get_subtitles(video_id)

        if result and result[0]:
            logger.info(f"✓ Transcript extracted for {video_id}")
            return result
        else:
            logger.debug(f"No transcript available for {video_id}")
            return None, None
