#!/usr/bin/env python3
"""
YouTube Video Processing Engine
Main entry point for video summarization
"""

import os
import sys
import logging
import re
from datetime import datetime
from time import sleep
from typing import Dict

from dotenv import load_dotenv

# Load environment variables (override=True to force reload)
load_dotenv(override=True)

# Import core modules
from src.core.youtube import YouTubeClient
from src.core.transcript import TranscriptExtractor
from src.core.ai_summarizer import AISummarizer
from src.core.email_sender import EmailSender

# Import managers
from src.managers.config_manager import ConfigManager, ProcessedVideos
from src.managers.database import VideoDatabase


# Configure structured logging
def setup_logging():
    """Setup logging with rotation and formatting"""
    log_dir = 'logs'
    os.makedirs(log_dir, exist_ok=True)

    log_level = os.getenv('LOG_LEVEL', 'INFO').upper()

    # Create logger
    logger = logging.getLogger('summarizer')
    logger.setLevel(getattr(logging, log_level, logging.INFO))

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_format = logging.Formatter(
        '%(asctime)s [%(levelname)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    console_handler.setFormatter(console_format)

    # File handler with rotation
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

    # Add handlers
    logger.addHandler(console_handler)
    logger.addHandler(file_handler)

    return logger


class VideoProcessor:
    """Main video processing orchestrator"""

    RATE_LIMIT_DELAY = 3  # Delay between API calls

    def __init__(self):
        """Initialize with config, credentials, and logging"""
        self.logger = setup_logging()
        self.logger.info("="*60)
        self.logger.info("YouTube Summarizer v2.0 Initializing")
        self.logger.info("="*60)

        # Load configuration
        self.config_manager = ConfigManager('config.txt')
        self.config = self.config_manager.read_config()
        self.logger.info(f"Loaded config: {len(self.config['channels'])} channels")

        # Load and validate environment variables
        self.openai_key = os.getenv('OPENAI_API_KEY')
        self.target_email = os.getenv('TARGET_EMAIL')
        self.smtp_user = os.getenv('SMTP_USER')
        self.smtp_pass = os.getenv('SMTP_PASS')

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
            self.logger.error("Missing required environment variables:")
            for var in missing:
                self.logger.error(f"  - {var}")
            self.logger.error("Please check your .env file and restart")
            self.logger.error("See .env.example for required variables")
            sys.exit(1)

        # Validate email format
        if not re.match(r'^[\w\.\-+]+@[\w\.\-]+\.\w+$', self.target_email):
            self.logger.error(f"Invalid TARGET_EMAIL format: {self.target_email}")
            sys.exit(1)

        # Initialize components
        use_ytdlp = self.config['settings'].get('USE_YTDLP', 'true').lower() == 'true'

        self.youtube_client = YouTubeClient(use_ytdlp=use_ytdlp)
        self.transcript_extractor = TranscriptExtractor()

        # Get model from environment or use default
        openai_model = os.getenv('OPENAI_MODEL', 'gpt-4o-mini')
        self.summarizer = AISummarizer(self.openai_key, model=openai_model)
        self.email_sender = EmailSender(self.smtp_user, self.smtp_pass, self.target_email)

        # Setup processed videos tracking (legacy)
        max_entries = int(os.getenv('MAX_PROCESSED_ENTRIES', '10000'))
        self.processed = ProcessedVideos(
            file_path='data/processed.txt',
            max_entries=max_entries,
            keep_entries=max_entries // 2
        )
        stats = self.processed.get_stats()
        self.logger.info(f"Loaded {stats['total']} processed videos (legacy)")

        # Initialize database
        self.db = VideoDatabase('data/videos.db')
        self.logger.info("Database initialized")

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

    def process_video(self, video: Dict, channel_id: str, channel_name: str) -> bool:
        """
        Process a single video: extract transcript, summarize, save to DB, and optionally email
        Returns True if successful (summary generated and saved)
        """
        self.logger.info(f"   ▶️  {video['title'][:60]}...")

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
            if existing and existing.get('processing_status') != 'pending':
                self.logger.debug(f"      Already processed: {existing.get('processing_status')}")
                return False

        # Mark as processing
        if self.db.is_processed(video['id']):
            self.db.update_video_processing(video['id'], 'processing')
        else:
            self.db.add_video(
                video_id=video['id'],
                channel_id=channel_id,
                channel_name=channel_name,
                title=video['title'],
                duration_seconds=video.get('duration_seconds'),
                view_count=video.get('view_count'),
                upload_date=video.get('upload_date'),
                processing_status='processing'
            )

        # STEP 1: Extract transcript
        transcript, duration = self.transcript_extractor.get_transcript(video['id'])
        if not transcript:
            self.logger.info(f"      ❌ No transcript available")
            self.db.update_video_processing(
                video['id'],
                status='failed_transcript',
                error_message='Transcript not available for this video'
            )
            self.processed.mark_processed(video['id'])
            self.stats['videos_skipped'] += 1
            return False

        # Use metadata duration if available, otherwise use transcript duration
        if not video.get('duration_string') or video['duration_string'] == 'Unknown':
            video['duration_string'] = duration

        # STEP 2: Generate AI summary
        use_summary_length = self.config['settings'].get('USE_SUMMARY_LENGTH', 'false') == 'true'
        max_tokens = int(self.config['settings'].get('SUMMARY_LENGTH', '500')) if use_summary_length else None
        summary = self.summarizer.summarize_with_retry(
            video=video,
            transcript=transcript,
            duration=video['duration_string'],
            prompt_template=self.config['prompt'],
            max_tokens=max_tokens
        )

        if not summary:
            self.logger.info(f"      ❌ AI summarization failed")
            self.db.update_video_processing(
                video['id'],
                status='failed_ai',
                error_message='Failed to generate summary using OpenAI API'
            )
            self.processed.mark_processed(video['id'])
            self.stats['videos_failed'] += 1
            self.stats['api_errors'] += 1
            return False

        self.stats['api_calls'] += 1

        # STEP 3: Save summary to database
        self.db.update_video_processing(
            video['id'],
            status='success',
            summary_text=summary,
            summary_length=len(summary)
        )
        self.logger.info(f"      ✅ Summary generated ({len(summary)} chars)")

        # STEP 4: Optionally send email
        send_email = os.getenv('SEND_EMAIL_SUMMARIES', 'true').lower() == 'true'

        if send_email:
            if self.email_sender.send_email(video, summary, channel_name):
                self.db.update_video_processing(video['id'], status='success', email_sent=True)
                self.stats['email_sent'] += 1
                self.logger.info(f"      📧 Email sent")
            else:
                # Email failed but summary is saved - mark as failed_email
                self.db.update_video_processing(
                    video['id'],
                    status='failed_email',
                    error_message='Summary generated but email delivery failed',
                    email_sent=False
                )
                self.stats['email_failed'] += 1
                self.logger.warning(f"      ⚠️  Email failed (summary saved)")
        else:
            self.logger.info(f"      📝 Email disabled (summary saved only)")

        # Mark as processed (legacy tracking)
        self.processed.mark_processed(video['id'])
        self.stats['videos_processed'] += 1

        # Rate limiting
        sleep(self.RATE_LIMIT_DELAY)
        return True

    def run(self):
        """Main processing loop"""
        self.logger.info("")
        self.logger.info("="*60)
        self.logger.info(f"Starting processing run at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        self.logger.info("="*60)

        if not self.config['channels']:
            self.logger.warning("No channels configured!")
            self.logger.warning("Add channels to config.txt or use the web UI")
            return

        # Get settings
        max_videos = int(self.config['settings'].get('MAX_VIDEOS_PER_CHANNEL', '5'))
        skip_shorts = self.config['settings'].get('SKIP_SHORTS', 'true').lower() == 'true'

        # Process each channel
        for channel_id in self.config['channels']:
            channel_name = self.config['channel_names'].get(channel_id, channel_id)
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
                    if existing and existing.get('processing_status') not in ['pending', None]:
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

        # Log processed stats
        proc_stats = self.processed.get_stats()
        self.logger.info(f"   📝 Total Processed: {proc_stats['total']}/{proc_stats['max']}")

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
