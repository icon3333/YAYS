"""
Export Manager - Handles data export operations for YAYS.

Supports two export levels:
1. Feed Export - Channels + videos with summaries
2. Complete Backup - Feed + settings + AI prompt (no credentials)

Supports two formats:
- JSON (structured, import-capable)
- CSV (analysis-friendly, videos only)
"""

import csv
import io
import logging
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

from src.managers.database import VideoDatabase
from src.managers.config_manager import ConfigManager
from src.managers.settings_manager import SettingsManager


logger = logging.getLogger(__name__)


class ExportManager:
    """Manages export operations for channels, videos, and settings."""

    # Schema version for export files (semver format)
    SCHEMA_VERSION = "1.0"

    # Application metadata
    APP_NAME = "YAYS"
    APP_VERSION = "2.2.0"

    # Export levels
    EXPORT_LEVEL_FEED = "feed"
    EXPORT_LEVEL_COMPLETE = "complete"

    # Fields to exclude from settings export (security)
    EXCLUDED_SETTINGS = {
        "OPENAI_API_KEY",
        "SMTP_SERVER",
        "SMTP_PORT",
        "SMTP_USERNAME",
        "SMTP_PASSWORD",
        "INOREADER_EMAIL",
        "EMAIL_ENABLED",
        "LOG_LEVEL",
    }

    def __init__(
        self,
        db_path: str = "data/videos.db",
        config_path: str = "config.txt",
        env_path: str = ".env",
    ):
        """
        Initialize ExportManager.

        Args:
            db_path: Path to SQLite database
            config_path: Path to config.txt
            env_path: Path to .env file
        """
        self.db = VideoDatabase(db_path)
        self.config_manager = ConfigManager(config_path)
        self.settings_manager = SettingsManager(env_path)

    def export_feed_json(self) -> Dict[str, Any]:
        """
        Export Feed level data to JSON structure.

        Returns:
            Dictionary with export_level, channels, videos, metadata

        Raises:
            Exception: If database or config read fails
        """
        logger.info("Generating Feed Export (JSON)")

        try:
            channels = self._get_channels()
            videos = self._get_videos()

            export_data = {
                "export_level": self.EXPORT_LEVEL_FEED,
                "export_timestamp": datetime.now(timezone.utc).isoformat(),
                "schema_version": self.SCHEMA_VERSION,
                "metadata": {
                    "application": self.APP_NAME,
                    "application_version": self.APP_VERSION,
                    "total_channels": len(channels),
                    "total_videos": len(videos),
                },
                "channels": channels,
                "videos": videos,
            }

            logger.info(
                f"Feed Export generated: {len(channels)} channels, {len(videos)} videos"
            )
            return export_data

        except Exception as e:
            logger.error(f"Feed Export failed: {e}")
            raise

    def export_complete_backup_json(self) -> Dict[str, Any]:
        """
        Export Complete Backup level data to JSON structure.

        Includes: Feed data + settings + AI prompt (no credentials)

        Returns:
            Dictionary with all exportable data

        Raises:
            Exception: If database, config, or settings read fails
        """
        logger.info("Generating Complete Backup Export (JSON)")

        try:
            # Start with Feed Export data
            export_data = self.export_feed_json()

            # Override export level
            export_data["export_level"] = self.EXPORT_LEVEL_COMPLETE

            # Add settings (non-secret only)
            settings = self._get_settings()
            export_data["settings"] = settings

            logger.info(
                f"Complete Backup generated: {len(export_data['channels'])} channels, "
                f"{len(export_data['videos'])} videos, {len(settings)} settings"
            )
            return export_data

        except Exception as e:
            logger.error(f"Complete Backup Export failed: {e}")
            raise

    def export_videos_csv(self) -> str:
        """
        Export videos to CSV format.

        Returns:
            CSV string with headers and all video rows

        Raises:
            Exception: If database read fails
        """
        logger.info("Generating Videos Export (CSV)")

        try:
            videos = self._get_videos()

            # Create CSV in memory
            output = io.StringIO()

            # Write UTF-8 BOM for Excel compatibility
            output.write("\ufeff")

            # Define CSV columns (19 total)
            fieldnames = [
                "video_id",
                "title",
                "channel_id",
                "channel_name",
                "duration_seconds",
                "duration_formatted",
                "view_count",
                "upload_date",
                "processing_status",
                "summary_text",
                "summary_length",
                "email_sent",
                "processed_date",
                "error_message",
                "hours_saved",
                "youtube_url",
                "channel_url",
                "created_at",
                "updated_at",
            ]

            writer = csv.DictWriter(
                output,
                fieldnames=fieldnames,
                quoting=csv.QUOTE_NONNUMERIC,
                lineterminator="\r\n",
            )

            writer.writeheader()

            # Write video rows
            for video in videos:
                row = self._format_csv_row(video)
                writer.writerow(row)

            csv_content = output.getvalue()
            output.close()

            logger.info(f"CSV Export generated: {len(videos)} videos")
            return csv_content

        except Exception as e:
            logger.error(f"CSV Export failed: {e}")
            raise

    def _get_channels(self) -> List[Dict[str, Any]]:
        """
        Extract channels from ConfigManager.

        Returns:
            List of channel dictionaries with channel_id, channel_name, added_date
        """
        channels_list = []

        try:
            # Get channels from config
            channels_raw = self.config_manager.get_value("Channels", "CHANNELS", "")

            if not channels_raw:
                logger.warning("No channels found in config")
                return []

            # Parse channels (format: "ID|Name" or "ID" per line)
            for line in channels_raw.strip().split("\n"):
                line = line.strip()
                if not line:
                    continue

                parts = line.split("|", 1)
                channel_id = parts[0].strip()
                channel_name = parts[1].strip() if len(parts) > 1 else None

                channels_list.append(
                    {
                        "channel_id": channel_id,
                        "channel_name": channel_name,
                        "added_date": None,  # Not tracked in config currently
                    }
                )

            logger.debug(f"Extracted {len(channels_list)} channels from config")
            return channels_list

        except Exception as e:
            logger.error(f"Failed to extract channels: {e}")
            raise

    def _get_videos(self) -> List[Dict[str, Any]]:
        """
        Extract all videos from VideoDatabase.

        Returns:
            List of video dictionaries with all fields
        """
        try:
            videos = self.db.export_all_videos()
            logger.debug(f"Extracted {len(videos)} videos from database")
            return videos

        except Exception as e:
            logger.error(f"Failed to extract videos: {e}")
            raise

    def _get_settings(self) -> Dict[str, Any]:
        """
        Extract non-secret settings from ConfigManager.

        Excludes credentials for security.

        Returns:
            Dictionary of settings
        """
        settings = {}

        try:
            # Get application settings from config.txt
            settings_keys = [
                "SUMMARY_LENGTH",
                "USE_SUMMARY_LENGTH",
                "SKIP_SHORTS",
                "MAX_VIDEOS_PER_CHANNEL",
                "CHECK_INTERVAL_MINUTES",
                "MAX_FEED_ENTRIES",
            ]

            for key in settings_keys:
                value = self.config_manager.get_value("Settings", key, None)
                if value is not None:
                    # Convert string booleans to actual booleans
                    if value.lower() in ("true", "false"):
                        value = value.lower() == "true"
                    # Convert string integers to actual integers
                    elif value.isdigit():
                        value = int(value)
                    settings[key] = value

            # Get AI prompt template
            ai_prompt = self.config_manager.get_value("AI", "PROMPT_TEMPLATE", None)
            if ai_prompt:
                settings["ai_prompt_template"] = ai_prompt

            logger.debug(f"Extracted {len(settings)} settings from config")
            return settings

        except Exception as e:
            logger.error(f"Failed to extract settings: {e}")
            raise

    def _format_csv_row(self, video: Dict[str, Any]) -> Dict[str, str]:
        """
        Format video dictionary as CSV row with calculated fields.

        Args:
            video: Video dictionary from database

        Returns:
            Dictionary with all CSV fields
        """
        # Calculate duration formatted (MM:SS or HH:MM:SS)
        duration_seconds = video.get("duration_seconds", 0)
        if duration_seconds >= 3600:
            hours = duration_seconds // 3600
            minutes = (duration_seconds % 3600) // 60
            seconds = duration_seconds % 60
            duration_formatted = f"{hours}:{minutes:02d}:{seconds:02d}"
        else:
            minutes = duration_seconds // 60
            seconds = duration_seconds % 60
            duration_formatted = f"{minutes}:{seconds:02d}"

        # Calculate hours saved (duration * 0.8 / 3600)
        hours_saved = round(duration_seconds * 0.8 / 3600, 2)

        # Generate URLs
        video_id = video.get("video_id", "")
        channel_id = video.get("channel_id", "")
        youtube_url = f"https://youtube.com/watch?v={video_id}" if video_id else ""
        channel_url = (
            f"https://youtube.com/channel/{channel_id}" if channel_id else ""
        )

        # Convert boolean to string
        email_sent = str(video.get("email_sent", False)).lower()

        return {
            "video_id": video.get("video_id", ""),
            "title": video.get("title", ""),
            "channel_id": channel_id,
            "channel_name": video.get("channel_name", ""),
            "duration_seconds": str(duration_seconds),
            "duration_formatted": duration_formatted,
            "view_count": str(video.get("view_count") or ""),
            "upload_date": video.get("upload_date") or "",
            "processing_status": video.get("processing_status", ""),
            "summary_text": video.get("summary_text") or "",
            "summary_length": str(video.get("summary_length") or ""),
            "email_sent": email_sent,
            "processed_date": video.get("processed_date") or "",
            "error_message": video.get("error_message") or "",
            "hours_saved": str(hours_saved),
            "youtube_url": youtube_url,
            "channel_url": channel_url,
            "created_at": video.get("created_at") or "",
            "updated_at": video.get("updated_at") or "",
        }

    def generate_export_filename(
        self, export_type: str, file_format: str = "json"
    ) -> str:
        """
        Generate timestamped filename for export.

        Args:
            export_type: 'feed_export', 'videos', or 'full_backup'
            file_format: 'json' or 'csv'

        Returns:
            Filename with timestamp (e.g., 'yays_feed_export_2025-10-20_14-30.json')
        """
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
        return f"yays_{export_type}_{timestamp}.{file_format}"
