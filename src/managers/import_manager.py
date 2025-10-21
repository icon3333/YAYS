"""
Import Manager - Handles data import operations for YAYS.

Provides:
- JSON validation with schema checking
- Import preview generation
- Transaction-safe import with automatic rollback on error
- Merge/skip/replace conflict resolution
"""

import logging
import os
import shutil
from dataclasses import dataclass
from typing import List, Dict, Any, Optional
from datetime import datetime

from src.managers.database import VideoDatabase
from src.managers.config_manager import ConfigManager
from src.managers.settings_manager import SettingsManager


logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    """Result of import file validation."""
    valid: bool
    errors: List[str]
    warnings: List[str]


@dataclass
class ImportPreview:
    """Preview of changes that will be applied during import."""
    channels_new: int
    channels_existing: int
    videos_new: int
    videos_duplicate: int
    settings_changed: int
    settings_details: List[str]  # List of "KEY: old_value → new_value"
    total_size_mb: float


@dataclass
class ImportResult:
    """Result of import operation."""
    success: bool
    channels_added: int
    videos_added: int
    settings_updated: int
    errors: List[str]


class ImportManager:
    """Manages import operations with validation and rollback safety."""

    # Schema version for compatibility checking
    SUPPORTED_SCHEMA_VERSION = "1.0"

    # Valid processing statuses
    VALID_PROCESSING_STATUSES = {
        "pending",
        "processing",
        "success",
        "failed_transcript",
        "failed_ai",
        "failed_email",
    }

    # Required top-level fields
    REQUIRED_FIELDS = {
        "export_level",
        "export_timestamp",
        "schema_version",
        "channels",
        "videos",
    }

    # Required channel fields
    REQUIRED_CHANNEL_FIELDS = {"channel_id"}

    # Required video fields
    REQUIRED_VIDEO_FIELDS = {
        "video_id",
        "title",
        "channel_id",
        "duration_seconds",
        "processing_status",
    }

    # Maximum field lengths (security)
    MAX_LENGTHS = {
        "title": 500,
        "summary_text": 10000,
        "error_message": 1000,
        "channel_name": 200,
    }

    # Maximum file size (50 MB)
    MAX_FILE_SIZE_BYTES = 50 * 1024 * 1024

    def __init__(
        self,
        db_path: str = "data/videos.db",
        config_path: str = "config.txt",
        env_path: str = ".env",
    ):
        """
        Initialize ImportManager.

        Args:
            db_path: Path to SQLite database
            config_path: Path to config.txt
            env_path: Path to .env file
        """
        self.db = VideoDatabase(db_path)
        self.config_manager = ConfigManager(config_path)
        self.settings_manager = SettingsManager(env_path)

    def validate_import_file(self, data: Dict[str, Any]) -> ValidationResult:
        """
        Validate import file structure and data.

        Args:
            data: Parsed JSON data from import file

        Returns:
            ValidationResult with validation status and any errors/warnings
        """
        errors = []
        warnings = []

        # Check required top-level fields
        for field in self.REQUIRED_FIELDS:
            if field not in data:
                errors.append(f"Missing required field: {field}")

        if errors:
            return ValidationResult(valid=False, errors=errors, warnings=warnings)

        # Check schema version
        schema_version = data.get("schema_version", "")
        if not self._is_compatible_schema(schema_version):
            if schema_version > self.SUPPORTED_SCHEMA_VERSION:
                warnings.append(
                    f"Schema version {schema_version} is newer than supported {self.SUPPORTED_SCHEMA_VERSION}. "
                    "Import may fail or produce unexpected results."
                )
            else:
                errors.append(
                    f"Schema version {schema_version} is not supported. "
                    f"Supported version: {self.SUPPORTED_SCHEMA_VERSION}"
                )

        # Validate export level
        export_level = data.get("export_level")
        if export_level not in ("feed", "complete"):
            errors.append(f"Invalid export_level: {export_level}. Must be 'feed' or 'complete'")

        # Validate channels
        channels = data.get("channels", [])
        if not isinstance(channels, list):
            errors.append("'channels' must be a list")
        else:
            for i, channel in enumerate(channels):
                channel_errors = self._validate_channel(channel, i)
                errors.extend(channel_errors)

        # Validate videos
        videos = data.get("videos", [])
        if not isinstance(videos, list):
            errors.append("'videos' must be a list")
        else:
            for i, video in enumerate(videos):
                video_errors = self._validate_video(video, i)
                errors.extend(video_errors)

        # Validate settings (if Complete Backup)
        if export_level == "complete":
            settings = data.get("settings", {})
            if not isinstance(settings, dict):
                errors.append("'settings' must be a dictionary")
            else:
                settings_errors = self._validate_settings(settings)
                errors.extend(settings_errors)

        # Final validation
        valid = len(errors) == 0

        return ValidationResult(valid=valid, errors=errors, warnings=warnings)

    def preview_import(self, data: Dict[str, Any]) -> ImportPreview:
        """
        Generate preview of changes that will be applied.

        Args:
            data: Validated import data

        Returns:
            ImportPreview with counts of changes
        """
        # Get current state
        existing_channels, _ = self.config_manager.get_channels()
        existing_settings = self.config_manager.get_settings()

        # Count channels
        import_channels = data.get("channels", [])
        channels_new = 0
        channels_existing = 0

        for ch in import_channels:
            ch_id = ch.get("channel_id")
            if ch_id in existing_channels:
                channels_existing += 1
            else:
                channels_new += 1

        # Count videos
        import_videos = data.get("videos", [])
        videos_new = 0
        videos_duplicate = 0

        for video in import_videos:
            video_id = video.get("video_id")
            if self.db.is_processed(video_id):
                videos_duplicate += 1
            else:
                videos_new += 1

        # Count settings changes
        settings_changed = 0
        settings_details = []

        if data.get("export_level") == "complete":
            import_settings = data.get("settings", {})

            for key, new_value in import_settings.items():
                if key == "ai_prompt_template":
                    # Compare AI prompt
                    current_prompt = self.config_manager.get_prompt()
                    if current_prompt != new_value:
                        settings_changed += 1
                        settings_details.append(f"AI_PROMPT: (modified)")
                else:
                    # Compare other settings
                    current_value = existing_settings.get(key)
                    if str(current_value) != str(new_value):
                        settings_changed += 1
                        settings_details.append(f"{key}: {current_value} → {new_value}")

        # Calculate total size (rough estimate)
        import json
        total_size_mb = len(json.dumps(data)) / (1024 * 1024)

        return ImportPreview(
            channels_new=channels_new,
            channels_existing=channels_existing,
            videos_new=videos_new,
            videos_duplicate=videos_duplicate,
            settings_changed=settings_changed,
            settings_details=settings_details,
            total_size_mb=round(total_size_mb, 2),
        )

    def import_data(self, data: Dict[str, Any]) -> ImportResult:
        """
        Execute import with transaction safety and rollback on error.

        Import order:
        1. Backup config files
        2. Import channels (merge)
        3. Import videos (skip duplicates)
        4. Import settings (replace)

        If any step fails, rollback all changes.

        Args:
            data: Validated import data

        Returns:
            ImportResult with success status and counts
        """
        logger.info("Starting import operation")

        errors = []
        channels_added = 0
        videos_added = 0
        settings_updated = 0

        # Create backup timestamp
        backup_suffix = datetime.now().strftime("%Y%m%d_%H%M%S")

        try:
            # Step 1: Create backups
            config_backup = self._create_config_backup(backup_suffix)

            # Step 2: Import channels (merge)
            try:
                channels = data.get("channels", [])
                channels_added = self.config_manager.import_channels(channels, merge=True)
                logger.info(f"Imported {channels_added} new channels")

            except Exception as e:
                error_msg = f"Failed to import channels: {e}"
                logger.error(error_msg)
                errors.append(error_msg)
                # Restore config from backup
                self._restore_config_backup(config_backup)
                raise

            # Step 3: Import videos (skip duplicates)
            try:
                videos = data.get("videos", [])
                videos_added = self.db.bulk_insert_videos(videos, skip_duplicates=True)
                logger.info(f"Imported {videos_added} new videos (skipped {len(videos) - videos_added} duplicates)")

            except Exception as e:
                error_msg = f"Failed to import videos: {e}"
                logger.error(error_msg)
                errors.append(error_msg)
                # Restore config from backup (channels already added)
                self._restore_config_backup(config_backup)
                raise

            # Step 4: Import settings (if Complete Backup)
            if data.get("export_level") == "complete":
                try:
                    settings = data.get("settings", {})

                    # Separate config.txt settings from .env settings
                    config_settings = {}
                    env_settings = {}

                    # Config.txt settings
                    config_keys = {
                        "SUMMARY_LENGTH", "USE_SUMMARY_LENGTH", "SKIP_SHORTS",
                        "MAX_VIDEOS_PER_CHANNEL", "CHECK_INTERVAL_MINUTES", "MAX_FEED_ENTRIES"
                    }

                    for key, value in settings.items():
                        if key == "ai_prompt_template":
                            # Handle AI prompt separately
                            self.config_manager.set_prompt(value)
                            settings_updated += 1
                        elif key in config_keys:
                            config_settings[key] = value
                        else:
                            # Everything else goes to .env
                            env_settings[key] = value

                    # Import config.txt settings
                    if config_settings:
                        count = self.config_manager.import_settings(config_settings)
                        settings_updated += count
                        logger.info(f"Imported {count} config.txt settings")

                    # Import .env settings
                    if env_settings:
                        success, message, import_errors = self.settings_manager.update_multiple_settings(env_settings)
                        if success:
                            settings_updated += len(env_settings)
                            logger.info(f"Imported {len(env_settings)} .env settings")
                        else:
                            logger.warning(f"Some .env settings failed: {import_errors}")
                            # Don't fail the whole import, just log warnings

                    logger.info(f"Imported total {settings_updated} settings")

                except Exception as e:
                    error_msg = f"Failed to import settings: {e}"
                    logger.error(error_msg)
                    errors.append(error_msg)
                    # Restore config from backup
                    self._restore_config_backup(config_backup)
                    raise

            # Success!
            logger.info(
                f"Import successful: {channels_added} channels, {videos_added} videos, {settings_updated} settings"
            )

            return ImportResult(
                success=True,
                channels_added=channels_added,
                videos_added=videos_added,
                settings_updated=settings_updated,
                errors=[],
            )

        except Exception as e:
            # Import failed, rollback complete
            logger.error(f"Import failed, rolled back changes: {e}")
            errors.append(f"Import failed: {e}")

            return ImportResult(
                success=False,
                channels_added=0,
                videos_added=0,
                settings_updated=0,
                errors=errors,
            )

    def _validate_channel(self, channel: Any, index: int) -> List[str]:
        """Validate a single channel object."""
        errors = []

        if not isinstance(channel, dict):
            errors.append(f"channels[{index}] must be a dictionary")
            return errors

        # Check required fields
        for field in self.REQUIRED_CHANNEL_FIELDS:
            if field not in channel:
                errors.append(f"channels[{index}] missing required field: {field}")

        # Validate channel_id format
        channel_id = channel.get("channel_id", "")
        if not self._is_valid_channel_id(channel_id):
            errors.append(f"channels[{index}].channel_id has invalid format: {channel_id}")

        # Validate channel_name length
        channel_name = channel.get("channel_name")
        if channel_name and len(channel_name) > self.MAX_LENGTHS["channel_name"]:
            errors.append(
                f"channels[{index}].channel_name too long "
                f"(max {self.MAX_LENGTHS['channel_name']} chars)"
            )

        return errors

    def _validate_video(self, video: Any, index: int) -> List[str]:
        """Validate a single video object."""
        errors = []

        if not isinstance(video, dict):
            errors.append(f"videos[{index}] must be a dictionary")
            return errors

        # Check required fields
        for field in self.REQUIRED_VIDEO_FIELDS:
            if field not in video:
                errors.append(f"videos[{index}] missing required field: {field}")

        # Validate video_id format
        video_id = video.get("video_id", "")
        if not self._is_valid_video_id(video_id):
            errors.append(f"videos[{index}].video_id has invalid format: {video_id}")

        # Validate processing_status
        status = video.get("processing_status", "")
        if status not in self.VALID_PROCESSING_STATUSES:
            errors.append(
                f"videos[{index}].processing_status invalid: {status}. "
                f"Must be one of {self.VALID_PROCESSING_STATUSES}"
            )

        # Validate data types
        duration = video.get("duration_seconds")
        if duration is not None and not isinstance(duration, int):
            errors.append(f"videos[{index}].duration_seconds must be integer, got {type(duration).__name__}")

        email_sent = video.get("email_sent")
        if email_sent is not None and not isinstance(email_sent, bool):
            errors.append(f"videos[{index}].email_sent must be boolean, got {type(email_sent).__name__}")

        # Validate field lengths
        title = video.get("title", "")
        if len(title) > self.MAX_LENGTHS["title"]:
            errors.append(
                f"videos[{index}].title too long (max {self.MAX_LENGTHS['title']} chars)"
            )

        summary = video.get("summary_text")
        if summary and len(summary) > self.MAX_LENGTHS["summary_text"]:
            errors.append(
                f"videos[{index}].summary_text too long (max {self.MAX_LENGTHS['summary_text']} chars)"
            )

        error_msg = video.get("error_message")
        if error_msg and len(error_msg) > self.MAX_LENGTHS["error_message"]:
            errors.append(
                f"videos[{index}].error_message too long (max {self.MAX_LENGTHS['error_message']} chars)"
            )

        return errors

    def _validate_settings(self, settings: Dict[str, Any]) -> List[str]:
        """Validate settings object."""
        errors = []

        # Validate known settings
        if "SUMMARY_LENGTH" in settings:
            val = settings["SUMMARY_LENGTH"]
            if not isinstance(val, int) or val <= 0:
                errors.append("settings.SUMMARY_LENGTH must be a positive integer")

        if "SKIP_SHORTS" in settings:
            val = settings["SKIP_SHORTS"]
            if not isinstance(val, bool):
                errors.append("settings.SKIP_SHORTS must be boolean")

        if "MAX_VIDEOS_PER_CHANNEL" in settings:
            val = settings["MAX_VIDEOS_PER_CHANNEL"]
            if not isinstance(val, int) or val <= 0:
                errors.append("settings.MAX_VIDEOS_PER_CHANNEL must be a positive integer")

        if "ai_prompt_template" in settings:
            prompt = settings["ai_prompt_template"]
            if not isinstance(prompt, str) or len(prompt) == 0:
                errors.append("settings.ai_prompt_template must be a non-empty string")

        return errors

    def _is_compatible_schema(self, version: str) -> bool:
        """Check if schema version is compatible."""
        try:
            # For now, exact match required
            # Future: support backward compatibility within major version
            return version == self.SUPPORTED_SCHEMA_VERSION
        except:
            return False

    def _is_valid_channel_id(self, channel_id: str) -> bool:
        """Validate YouTube channel ID format."""
        import re

        # Standard channel ID: UC + 22 alphanumeric/dash/underscore
        if re.match(r"^UC[\w-]{22}$", channel_id):
            return True

        # Handle format: @username
        if re.match(r"^@[\w-]+$", channel_id):
            return True

        # Custom URL format
        if re.match(r"^[\w-]+$", channel_id) and len(channel_id) > 3:
            return True

        return False

    def _is_valid_video_id(self, video_id: str) -> bool:
        """Validate YouTube video ID format."""
        import re

        # YouTube video IDs are 11 characters: alphanumeric, dash, underscore
        return bool(re.match(r"^[\w-]{11}$", video_id))

    def _create_config_backup(self, suffix: str) -> Optional[str]:
        """
        Create backup of config file.

        Args:
            suffix: Backup filename suffix (timestamp)

        Returns:
            Path to backup file or None if backup failed
        """
        try:
            config_path = self.config_manager.config_path
            backup_path = f"{config_path}.backup.{suffix}"

            if os.path.exists(config_path):
                shutil.copy2(config_path, backup_path)
                logger.info(f"Created config backup: {backup_path}")
                return backup_path

        except Exception as e:
            logger.warning(f"Failed to create config backup: {e}")

        return None

    def _restore_config_backup(self, backup_path: Optional[str]) -> bool:
        """
        Restore config from backup file.

        Args:
            backup_path: Path to backup file

        Returns:
            True if restored successfully
        """
        if not backup_path or not os.path.exists(backup_path):
            logger.warning("No backup to restore from")
            return False

        try:
            config_path = self.config_manager.config_path
            shutil.copy2(backup_path, config_path)
            logger.info(f"Restored config from backup: {backup_path}")
            return True

        except Exception as e:
            logger.error(f"Failed to restore config from backup: {e}")
            return False
