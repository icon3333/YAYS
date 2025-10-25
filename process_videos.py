#!/usr/bin/env python3
"""
YouTube Video Processing Engine
Main entry point for video summarization
"""

import os
import sys
import logging
from datetime import datetime, timedelta
from time import sleep, time
from typing import Dict, List
from pathlib import Path

# Import core modules
from src.core.youtube import YouTubeClient
from src.core.transcript import TranscriptExtractor
from src.core.ai_summarizer import AISummarizer
from src.core.email_sender import EmailSender
from src.core.constants import (
    STATUS_PENDING, STATUS_PROCESSING, STATUS_SUCCESS,
    STATUS_FAILED_TRANSCRIPT, STATUS_FAILED_AI, STATUS_FAILED_EMAIL,
    RATE_LIMIT_DELAY
)

# Import managers
from src.managers.config_manager import ConfigManager
from src.managers.settings_manager import SettingsManager
from src.managers.database import VideoDatabase

# Import utilities
from src.utils.validators import is_valid_email


# Configure structured logging
def setup_logging():
    """Setup logging with rotation and formatting.

    - Console: only messages from the 'summarizer' logger
    - File: capture ALL module logs to help diagnose transcript issues
    """
    log_dir = 'logs'
    os.makedirs(log_dir, exist_ok=True)

    log_level = os.getenv('LOG_LEVEL', 'INFO').upper()

    # Create our app logger
    logger = logging.getLogger('summarizer')
    logger.setLevel(getattr(logging, log_level, logging.INFO))

    # Console handler (only for summarizer logger)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_format = logging.Formatter(
        '%(asctime)s [%(levelname)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    console_handler.setFormatter(console_format)
    logger.addHandler(console_handler)

    # File handler with rotation on ROOT to capture all module logs
    from logging.handlers import RotatingFileHandler
    file_handler = RotatingFileHandler(
        os.path.join(log_dir, 'summarizer.log'),
        maxBytes=10*1024*1024,  # 10MB
        backupCount=5,
        encoding='utf-8'
    )
    file_handler.setLevel(logging.DEBUG)
    file_format = logging.Formatter(
        '%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    file_handler.setFormatter(file_format)

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    root_logger.addHandler(file_handler)

    return logger


class VideoProcessor:
    """Main video processing orchestrator"""

    def __init__(self):
        """Initialize with config, credentials, and logging"""
        self.logger = setup_logging()
        self.logger.info("="*60)
        self.logger.info("YouTube Summarizer v2.0 Initializing")
        self.logger.info("="*60)

        # Initialize database and managers
        self.db = VideoDatabase('data/videos.db')
        self.config_manager = ConfigManager(db_path='data/videos.db')
        self.settings_manager = SettingsManager(db_path='data/videos.db')

        # Load configuration from database
        channels, channel_names = self.config_manager.get_channels()
        self.logger.info(f"Loaded config: {len(channels)} channels")

        # Get settings from database
        all_settings = self.settings_manager.get_all_settings(mask_secrets=False)
        config_settings = self.config_manager.get_settings()

        # Load and validate credentials from database
        self.openai_key = all_settings.get('OPENAI_API_KEY', {}).get('value', '')
        self.target_email = all_settings.get('TARGET_EMAIL', {}).get('value', '')
        self.smtp_user = all_settings.get('SMTP_USER', {}).get('value', '')
        self.smtp_pass = all_settings.get('SMTP_PASS', {}).get('value', '')

        missing = []
        if not self.openai_key:
            missing.append('OPENAI_API_KEY')
        if not self.target_email:
            missing.append('TARGET_EMAIL')
        if not self.smtp_user:
            missing.append('SMTP_USER')
        if not self.smtp_pass:
            missing.append('SMTP_PASS')

        if missing:
            self.logger.error("Missing required settings in database:")
            for var in missing:
                self.logger.error(f"  - {var}")
            self.logger.error("Please configure settings using the web UI and restart")
            sys.exit(1)

        # Validate email format
        if not is_valid_email(self.target_email):
            self.logger.error(f"Invalid TARGET_EMAIL format: {self.target_email}")
            sys.exit(1)

        # Initialize components
        use_ytdlp = True  # Always use ytdlp

        self.youtube_client = YouTubeClient(use_ytdlp=use_ytdlp)

        # Configure transcript extractor based on provider setting
        transcript_provider = all_settings.get('TRANSCRIPT_PROVIDER', {}).get('value', 'legacy')
        supadata_api_key = all_settings.get('SUPADATA_API_KEY', {}).get('value', '')

        # Log the provider being used
        self.logger.info(f"Using transcript provider: {transcript_provider}")

        self.transcript_extractor = TranscriptExtractor(
            provider=transcript_provider,
            supadata_api_key=supadata_api_key if transcript_provider == 'supadata' else None,
            cache=self.db
        )

        # Get model from database or use default
        openai_model = all_settings.get('OPENAI_MODEL', {}).get('value', 'gpt-4o-mini')
        self.summarizer = AISummarizer(self.openai_key, model=openai_model)
        self.email_sender = EmailSender(self.smtp_user, self.smtp_pass, self.target_email)

        # Store channels and settings for later use
        self.channels = channels
        self.channel_names = channel_names
        self.config_settings = config_settings
        self.send_email = all_settings.get('SEND_EMAIL_SUMMARIES', {}).get('value', 'true').lower() == 'true'

        self.logger.info("Database initialized")

        # Initialize lock file for process heartbeat
        self.lock_file = Path('data/.processing.lock')
        self.last_heartbeat = time()
        self._update_heartbeat()

        # Statistics
        self.stats = {
            'videos_processed': 0,
            'videos_skipped': 0,
            'videos_failed': 0,
            'api_calls': 0,
            'api_errors': 0,
            'email_sent': 0,
            'email_failed': 0
        }

        self.logger.info("Initialization complete")

    def _update_heartbeat(self):
        """Update process heartbeat lock file with current timestamp"""
        try:
            self.lock_file.parent.mkdir(parents=True, exist_ok=True)
            self.lock_file.write_text(str(time()))
            self.last_heartbeat = time()
        except Exception as e:
            self.logger.warning(f"Failed to update heartbeat: {e}")

    def _is_processor_alive(self, threshold_seconds: int = 120) -> bool:
        """Check if another processor is actively running"""
        try:
            if not self.lock_file.exists():
                return False

            last_update = float(self.lock_file.read_text())
            age = time() - last_update
            return age < threshold_seconds
        except Exception:
            return False

    def cleanup_stuck_videos(self):
        """
        Smart detection and cleanup of stuck videos using hybrid approach:
        1. Quick check: 2+ minutes without heartbeat
        2. Medium check: 5+ minutes in processing
        3. Absolute timeout: 10+ minutes regardless
        """
        try:
            # Get all videos currently in processing state
            with self.db._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT id, title, processed_date, retry_count
                    FROM videos
                    WHERE processing_status = 'processing'
                """)
                processing_videos = cursor.fetchall()

            if not processing_videos:
                return

            stuck_videos = []
            now = datetime.now()
            processor_alive = self._is_processor_alive()

            for row in processing_videos:
                video_id = row['id']
                title = row['title'][:50]
                processed_date = row['processed_date']
                retry_count = row['retry_count'] or 0

                if not processed_date:
                    continue

                # Calculate time in processing
                process_time = now - datetime.fromisoformat(processed_date)
                minutes_processing = process_time.total_seconds() / 60

                # Tier 1: Quick check (2+ minutes and no active processor)
                if minutes_processing > 2 and not processor_alive:
                    self.logger.warning(f"Stuck (no heartbeat): {title} ({minutes_processing:.1f} min)")
                    stuck_videos.append((video_id, retry_count))
                    continue

                # Tier 2: Medium check (5+ minutes regardless of heartbeat)
                if minutes_processing > 5:
                    self.logger.warning(f"Stuck (timeout): {title} ({minutes_processing:.1f} min)")
                    stuck_videos.append((video_id, retry_count))
                    continue

                # Tier 3: Absolute timeout (10+ minutes failsafe)
                if minutes_processing > 10:
                    self.logger.warning(f"Stuck (absolute): {title} ({minutes_processing:.1f} min)")
                    stuck_videos.append((video_id, retry_count))

            # Reset stuck videos
            if stuck_videos:
                with self.db._get_connection() as conn:
                    cursor = conn.cursor()
                    for video_id, retry_count in stuck_videos:
                        # Check retry limit
                        if retry_count >= 3:
                            # Mark as permanently failed after 3 attempts
                            cursor.execute("""
                                UPDATE videos
                                SET processing_status = 'failed_permanent',
                                    error_message = 'Max retries exceeded (3 attempts)'
                                WHERE id = ?
                            """, (video_id,))
                            self.logger.info(f"Marked as permanent failure: {video_id}")
                        else:
                            # Reset to pending for retry
                            cursor.execute("""
                                UPDATE videos
                                SET processing_status = 'pending',
                                    error_message = 'Reset from stuck processing state'
                                WHERE id = ?
                            """, (video_id,))
                            self.logger.info(f"Reset to pending: {video_id}")

                    conn.commit()

                self.logger.info(f"✅ Cleaned up {len(stuck_videos)} stuck videos")

        except Exception as e:
            self.logger.error(f"Error cleaning stuck videos: {e}")

    def process_video(self, video: Dict, channel_id: str, channel_name: str) -> bool:
        """
        Process a single video: extract transcript, summarize, save to DB, and optionally email
        Returns True if successful (summary generated and saved)
        """
        self.logger.info(f"   ▶️  {video['title'][:60]}...")

        # Update heartbeat to show we're actively processing
        self._update_heartbeat()

        # Get enhanced metadata (if using yt-dlp)
        metadata = self.youtube_client.get_video_metadata(video['id'])
        if metadata:
            duration_seconds = metadata.get('duration', 0)
            view_count = metadata.get('view_count', 0)
            upload_date = metadata.get('upload_date_string', '')
            duration_str = metadata.get('duration_string', 'Unknown')

            self.logger.debug(f"      Metadata: {duration_str}, {metadata.get('view_count_string', 'Unknown views')}")

            # Update video dict with metadata
            video['duration_seconds'] = duration_seconds
            video['view_count'] = view_count
            video['upload_date'] = upload_date
            video['duration_string'] = duration_str
        else:
            # No metadata available (RSS fallback)
            video['duration_seconds'] = None
            video['view_count'] = None
            video['upload_date'] = None
            video['duration_string'] = 'Unknown'

        # Check if video already exists in database
        if self.db.is_processed(video['id']):
            existing = self.db.get_video_by_id(video['id'])

            # Check retry limit (max 3 attempts)
            retry_count = existing.get('retry_count', 0)
            if retry_count >= 3 and existing.get('processing_status') != STATUS_SUCCESS:
                self.logger.info(f"      Skipping after {retry_count} failed attempts")
                return False

            # Skip if already successfully processed
            if existing and existing.get('processing_status') not in [STATUS_PENDING, None]:
                if existing.get('processing_status') != 'failed_permanent':
                    self.logger.debug(f"      Already processed: {existing.get('processing_status')}")
                return False

        # Mark as processing and increment retry count
        if self.db.is_processed(video['id']):
            existing = self.db.get_video_by_id(video['id'])
            current_retry = existing.get('retry_count', 0)
            self.db.update_video_processing(
                video['id'],
                STATUS_PROCESSING,
                retry_count=current_retry + 1
            )
        else:
            self.db.add_video(
                video_id=video['id'],
                channel_id=channel_id,
                channel_name=channel_name,
                title=video['title'],
                duration_seconds=video.get('duration_seconds'),
                view_count=video.get('view_count'),
                upload_date=video.get('upload_date'),
                processing_status=STATUS_PROCESSING
            )

        # STEP 1: Extract transcript
        self.logger.debug(f"      Fetching transcript for {video['id']}")
        self._update_heartbeat()  # Keep heartbeat alive
        transcript, duration = self.transcript_extractor.get_transcript(video['id'])
        if not transcript:
            self.logger.info(f"      ❌ No transcript available")
            self.db.update_video_processing(
                video['id'],
                status=STATUS_FAILED_TRANSCRIPT,
                error_message='Transcript not available for this video'
            )
            self.stats['videos_skipped'] += 1
            return False

        # Use metadata duration if available, otherwise use transcript duration
        if not video.get('duration_string') or video['duration_string'] == 'Unknown':
            video['duration_string'] = duration or 'Unknown'

        # STEP 2: Generate AI summary
        use_summary_length = self.config_settings.get('USE_SUMMARY_LENGTH', 'false') == 'true'
        max_tokens = int(self.config_settings.get('SUMMARY_LENGTH', '500')) if use_summary_length else None
        prompt_template = self.config_manager.get_prompt()
        self._update_heartbeat()  # Keep heartbeat alive
        summary = self.summarizer.summarize_with_retry(
            video=video,
            transcript=transcript,
            duration=video['duration_string'],
            prompt_template=prompt_template,
            max_tokens=max_tokens
        )

        if not summary:
            self.logger.info(f"      ❌ AI summarization failed")
            self.db.update_video_processing(
                video['id'],
                status=STATUS_FAILED_AI,
                error_message='Failed to generate summary using OpenAI API'
            )
            self.stats['videos_failed'] += 1
            self.stats['api_errors'] += 1
            return False

        self.stats['api_calls'] += 1

        # STEP 3: Save summary to database
        self.db.update_video_processing(
            video['id'],
            status=STATUS_SUCCESS,
            summary_text=summary,
            summary_length=len(summary)
        )
        self.logger.info(f"      ✅ Summary generated ({len(summary)} chars)")

        # STEP 4: Optionally send email
        if self.send_email:
            if self.email_sender.send_email(video, summary, channel_name):
                self.db.update_video_processing(video['id'], status=STATUS_SUCCESS, email_sent=True)
                self.stats['email_sent'] += 1
                self.logger.info(f"      📧 Email sent")
            else:
                # Email failed but summary is saved - mark as failed_email
                self.db.update_video_processing(
                    video['id'],
                    status=STATUS_FAILED_EMAIL,
                    error_message='Summary generated but email delivery failed',
                    email_sent=False
                )
                self.stats['email_failed'] += 1
                self.logger.warning(f"      ⚠️  Email failed (summary saved)")
        else:
            self.logger.info(f"      📝 Email disabled (summary saved only)")

        # Statistics
        self.stats['videos_processed'] += 1

        # Rate limiting
        sleep(RATE_LIMIT_DELAY)
        return True

    def run(self):
        """Main processing loop"""
        self.logger.info("")
        self.logger.info("="*60)
        self.logger.info(f"Starting processing run at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        self.logger.info("="*60)

        # Clean up any stuck videos from previous runs
        self.logger.info("🔍 Checking for stuck videos...")
        self.cleanup_stuck_videos()

        if not self.channels:
            self.logger.warning("No channels configured!")
            self.logger.warning("Add channels using the web UI")
            return

        # Get settings
        max_videos = int(self.config_settings.get('MAX_VIDEOS_PER_CHANNEL', '5'))
        skip_shorts = self.config_settings.get('SKIP_SHORTS', 'true').lower() == 'true'

        # STEP 1: Process any pending videos from database (retries, manual adds, etc.)
        pending_videos = self.db.get_pending_videos()
        if pending_videos:
            self.logger.info(f"🔄 Processing {len(pending_videos)} pending videos from database")
            for video in pending_videos:
                channel_id = video.get('channel_id', 'unknown')
                channel_name = video.get('channel_name', 'Unknown')
                self.logger.info(f"   ▶️  {video['title'][:50]}...")
                self.process_video(video, channel_id, channel_name)

        # STEP 2: Process each channel for new videos
        for channel_id in self.channels:
            channel_name = self.channel_names.get(channel_id, channel_id)
            self.logger.info(f"📡 Checking: {channel_name}")

            videos = self.youtube_client.get_channel_videos(
                channel_id=channel_id,
                max_videos=max_videos,
                skip_shorts=skip_shorts
            )

            if not videos:
                self.logger.info(f"   📭 No new videos")
                continue

            # Process each video
            for video in videos:
                # Check database status - only process if pending or not in DB
                if self.db.is_processed(video['id']):
                    existing = self.db.get_video_by_id(video['id'])
                    if existing and existing.get('processing_status') not in [STATUS_PENDING, None]:
                        self.logger.debug(f"   Skipping {existing.get('processing_status')}: {video['title'][:40]}")
                        continue

                # Process the video
                self.process_video(video, channel_id, channel_name)

        # Print summary
        self.logger.info("")
        self.logger.info("="*60)
        self.logger.info("Processing Complete")
        self.logger.info(f"   ✅ Processed: {self.stats['videos_processed']} videos")
        self.logger.info(f"   📧 Sent: {self.stats['email_sent']} emails")

        if self.stats['videos_skipped'] > 0:
            self.logger.info(f"   ⏭️  Skipped: {self.stats['videos_skipped']} videos (no transcript)")

        if self.stats['videos_failed'] > 0:
            self.logger.warning(f"   ❌ Failed: {self.stats['videos_failed']} videos")

        if self.stats['api_errors'] > 0:
            self.logger.warning(f"   ⚠️  API Errors: {self.stats['api_errors']}")

        # Log API usage
        self.logger.info(f"   📊 API Calls: {self.stats['api_calls']}")
        estimated_cost = self.stats['api_calls'] * 0.0014  # Rough estimate
        self.logger.info(f"   💰 Estimated Cost: ${estimated_cost:.4f}")

        self.logger.info("="*60)
        self.logger.info("")


def main():
    """Entry point with error handling"""
    try:
        processor = VideoProcessor()
        processor.run()
    except KeyboardInterrupt:
        print("\n\n👋 Stopped by user")
        sys.exit(0)
    except Exception as e:
        logger = logging.getLogger('summarizer')
        logger.critical(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
