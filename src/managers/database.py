#!/usr/bin/env python3
"""
SQLite Database Manager for YouTube Summarizer
Tracks processed videos with metadata for stats and feed
"""

import sqlite3
import os
from typing import List, Dict, Optional, Tuple, Any
from datetime import datetime, timedelta
from contextlib import contextmanager

from src.utils.formatters import format_duration, format_views, format_upload_date, format_processed_date
from src.utils.encryption import get_encryption


class VideoDatabase:
    """SQLite database for tracking processed videos"""

    def __init__(self, db_path='data/videos.db'):
        self.db_path = db_path

        # Ensure data directory exists
        os.makedirs(os.path.dirname(db_path) or '.', exist_ok=True)

        # Initialize database
        self._init_db()

    @contextmanager
    def _get_connection(self):
        """Context manager for database connections"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row  # Enable dict-like access
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()

    def _encrypt_value(self, value: str) -> str:
        """Encrypt a value using Fernet encryption"""
        if not value:
            return ''
        enc = get_encryption()
        return enc.encrypt(value)

    def _decrypt_value(self, value: str) -> str:
        """Decrypt a value using Fernet encryption"""
        if not value:
            return ''
        enc = get_encryption()
        return enc.decrypt(value)

    def _video_row_to_dict(self, row: sqlite3.Row, include_summary: bool = True) -> Dict[str, Any]:
        """
        Convert a SQLite row to a video dictionary with formatted fields.

        Args:
            row: SQLite row from videos table
            include_summary: Whether to include summary_text and summary_length

        Returns:
            Dict with video data and formatted fields
        """
        video = {
            'id': row['id'],
            'channel_id': row['channel_id'],
            'channel_name': row['channel_name'] or row['channel_id'],
            'title': row['title'],
            'duration_seconds': row['duration_seconds'],
            'duration_formatted': format_duration(row['duration_seconds']),
            'view_count': row['view_count'],
            'view_count_formatted': format_views(row['view_count']),
            'upload_date': row['upload_date'],
            'upload_date_formatted': format_upload_date(row['upload_date']),
            'processed_date': row['processed_date'],
            'processed_date_formatted': format_processed_date(row['processed_date']),
            'processing_status': row['processing_status'],
            'error_message': row['error_message'],
            'email_sent': bool(row['email_sent']),
            'source_type': row['source_type'] if 'source_type' in row.keys() else 'via_channel'
        }

        if include_summary:
            video['summary_text'] = row['summary_text']
            video['summary_length'] = row['summary_length']

        return video

    def _init_db(self):
        """Initialize database schema"""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # Videos table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS videos (
                    id TEXT PRIMARY KEY,
                    channel_id TEXT NOT NULL,
                    channel_name TEXT,
                    title TEXT NOT NULL,
                    duration_seconds INTEGER,
                    view_count INTEGER,
                    upload_date TEXT,
                    processed_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    summary_length INTEGER,
                    summary_text TEXT,
                    processing_status TEXT DEFAULT 'pending',
                    error_message TEXT,
                    email_sent BOOLEAN DEFAULT 0,
                    source_type TEXT DEFAULT 'via_channel',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Create indexes for faster queries
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_channel_id
                ON videos(channel_id)
            """)

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_processed_date
                ON videos(processed_date DESC)
            """)

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_processing_status
                ON videos(processing_status)
            """)

            conn.commit()

        # Run migrations to add new tables/columns to existing databases
        # Must run outside the CREATE TABLE transaction for existing databases
        self._migrate_add_source_type()
        self._ensure_settings_table()
        self._ensure_channels_table()

    def _migrate_add_source_type(self):
        """
        Migration: Add source_type column to existing databases

        This migration safely adds the source_type column to track how videos
        were added to the database:
        - 'via_channel': Videos added automatically from channel monitoring
        - 'via_manual': Videos added manually via Quick Add Video feature

        Backward compatible: Sets all existing videos to 'via_channel'
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # Check if source_type column already exists
            cursor.execute("PRAGMA table_info(videos)")
            columns = [row[1] for row in cursor.fetchall()]

            if 'source_type' not in columns:
                # Add the column with default value for backward compatibility
                cursor.execute("""
                    ALTER TABLE videos
                    ADD COLUMN source_type TEXT DEFAULT 'via_channel'
                """)

                # Explicitly set all existing videos to 'via_channel' for clarity
                cursor.execute("""
                    UPDATE videos
                    SET source_type = 'via_channel'
                    WHERE source_type IS NULL
                """)

                conn.commit()

            # Create index on source_type (safe to run multiple times)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_source_type
                ON videos(source_type)
            """)

            conn.commit()

    def _ensure_settings_table(self):
        """
        Ensure settings table exists for database-backed configuration.

        Creates a settings table to store ALL application settings
        in the database, including encrypted secrets.

        Secrets are encrypted at rest using Fernet symmetric encryption.
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # Create settings table with encrypted flag
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    type TEXT NOT NULL,
                    encrypted BOOLEAN DEFAULT 0,
                    description TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Check if we need to add encrypted column to existing table
            cursor.execute("PRAGMA table_info(settings)")
            columns = [row[1] for row in cursor.fetchall()]

            if 'encrypted' not in columns:
                cursor.execute("""
                    ALTER TABLE settings
                    ADD COLUMN encrypted BOOLEAN DEFAULT 0
                """)

            # Initialize default settings if table is empty
            cursor.execute("SELECT COUNT(*) FROM settings")
            if cursor.fetchone()[0] == 0:
                # Note: Secrets start empty, users must configure them via web UI
                default_settings = [
                    ('OPENAI_API_KEY', '', 'secret', 1, 'OpenAI API Key (encrypted)'),
                    ('SMTP_PASS', '', 'secret', 1, 'Gmail app password (encrypted)'),
                    ('TARGET_EMAIL', '', 'email', 0, 'Email address for receiving summaries'),
                    ('SMTP_USER', '', 'email', 0, 'Gmail SMTP username'),
                    ('LOG_LEVEL', 'INFO', 'enum', 0, 'Logging verbosity level'),
                    ('CHECK_INTERVAL_HOURS', '4', 'integer', 0, 'How often to check for new videos (hours)'),
                    ('MAX_PROCESSED_ENTRIES', '10000', 'integer', 0, 'Max video IDs to track before rotation'),
                    ('SEND_EMAIL_SUMMARIES', 'true', 'enum', 0, 'Send summaries via email'),
                    ('OPENAI_MODEL', 'gpt-4o-mini', 'text', 0, 'OpenAI model to use for summaries'),
                ]

                cursor.executemany(
                    "INSERT INTO settings (key, value, type, encrypted, description) VALUES (?, ?, ?, ?, ?)",
                    default_settings
                )

            conn.commit()

    def _ensure_channels_table(self):
        """
        Ensure channels table exists for database-backed channel management.

        Creates a channels table to store monitored YouTube channels.
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # Create channels table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS channels (
                    channel_id TEXT PRIMARY KEY,
                    channel_name TEXT NOT NULL,
                    enabled BOOLEAN DEFAULT 1,
                    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Add config settings to settings table
            cursor.execute("""
                INSERT OR IGNORE INTO settings (key, value, type, encrypted, description)
                VALUES
                    ('SUMMARY_LENGTH', '500', 'integer', 0, 'Maximum length of summary in tokens'),
                    ('USE_SUMMARY_LENGTH', 'false', 'enum', 0, 'Use summary length limit'),
                    ('SKIP_SHORTS', 'true', 'enum', 0, 'Skip YouTube Shorts videos'),
                    ('MAX_VIDEOS_PER_CHANNEL', '5', 'integer', 0, 'Maximum videos to check per channel'),
                    ('CHECK_INTERVAL_MINUTES', '60', 'integer', 0, 'How often to check for new videos (minutes)'),
                    ('MAX_FEED_ENTRIES', '20', 'integer', 0, 'Maximum feed entries to process')
            """)

            conn.commit()

    def is_processed(self, video_id: str) -> bool:
        """Check if video has been processed"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 1 FROM videos WHERE id = ?", (video_id,))
            return cursor.fetchone() is not None

    def add_video(
        self,
        video_id: str,
        channel_id: str,
        title: str,
        channel_name: Optional[str] = None,
        duration_seconds: Optional[int] = None,
        view_count: Optional[int] = None,
        upload_date: Optional[str] = None,
        summary_length: Optional[int] = None,
        summary_text: Optional[str] = None,
        processing_status: str = 'pending',
        error_message: Optional[str] = None,
        email_sent: bool = False,
        source_type: str = 'via_channel'
    ) -> bool:
        """
        Add a video to the database

        Args:
            video_id: YouTube video ID (11 characters)
            channel_id: YouTube channel ID
            title: Video title
            channel_name: Display name for the channel
            duration_seconds: Video duration in seconds
            view_count: Number of views
            upload_date: Upload date in YYYY-MM-DD format
            summary_length: Length of the generated summary
            summary_text: The AI-generated summary text
            processing_status: Current processing status (pending, processing, success, failed_*)
            error_message: Error message if processing failed
            email_sent: Whether summary email was sent successfully
            source_type: How video was added ('via_channel' or 'via_manual')

        Returns:
            True if video was added successfully, False if already exists
        """
        if self.is_processed(video_id):
            return False

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO videos
                (id, channel_id, channel_name, title, duration_seconds, view_count, upload_date,
                 summary_length, summary_text, processing_status, error_message, email_sent, source_type)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (video_id, channel_id, channel_name, title, duration_seconds, view_count, upload_date,
                  summary_length, summary_text, processing_status, error_message, int(email_sent), source_type))

        return True

    def get_channel_stats(self, channel_id: str) -> Dict:
        """
        Get statistics for a specific channel
        Returns: {
            'total_videos': int,
            'total_duration_seconds': int,
            'hours_saved': float,
            'last_processed': datetime
        }
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                SELECT
                    COUNT(*) as total_videos,
                    SUM(duration_seconds) as total_duration,
                    MAX(processed_date) as last_processed
                FROM videos
                WHERE channel_id = ?
            """, (channel_id,))

            row = cursor.fetchone()

            total_videos = row['total_videos'] or 0
            total_duration = row['total_duration'] or 0

            # Calculate total hours of video content
            total_hours = total_duration / 3600 if total_duration else 0

            return {
                'total_videos': total_videos,
                'total_duration_seconds': total_duration,
                'hours_saved': round(total_hours, 1),
                'last_processed': row['last_processed']
            }

    def get_all_channel_stats(self) -> Dict[str, Dict]:
        """
        Get statistics for all channels
        Returns: {channel_id: {stats}}
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                SELECT
                    channel_id,
                    COUNT(*) as total_videos,
                    SUM(duration_seconds) as total_duration,
                    MAX(processed_date) as last_processed
                FROM videos
                GROUP BY channel_id
            """)

            stats = {}
            for row in cursor.fetchall():
                channel_id = row['channel_id']
                total_duration = row['total_duration'] or 0
                total_hours = total_duration / 3600 if total_duration else 0

                stats[channel_id] = {
                    'total_videos': row['total_videos'],
                    'total_duration_seconds': total_duration,
                    'hours_saved': round(total_hours, 1),
                    'last_processed': row['last_processed']
                }

            return stats

    def get_processed_videos(
        self,
        channel_id: Optional[str] = None,
        limit: int = 25,
        offset: int = 0,
        order_by: str = 'recent'  # 'recent', 'oldest', 'channel'
    ) -> List[Dict]:
        """
        Get list of processed videos with pagination
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # Build query
            query = """
                SELECT
                    id,
                    channel_id,
                    channel_name,
                    title,
                    duration_seconds,
                    view_count,
                    upload_date,
                    processed_date,
                    processing_status,
                    error_message,
                    email_sent,
                    source_type
                FROM videos
            """

            params = []

            # Filter by channel if specified
            if channel_id:
                query += " WHERE channel_id = ?"
                params.append(channel_id)

            # Order by
            if order_by == 'recent':
                # Sort by upload_date (newest first), with NULL values last
                # SQLite: use CASE to put NULLs at the end
                query += " ORDER BY CASE WHEN upload_date IS NULL THEN 1 ELSE 0 END, upload_date DESC, processed_date DESC"
            elif order_by == 'oldest':
                # Sort by upload_date (oldest first), with NULL values last
                query += " ORDER BY CASE WHEN upload_date IS NULL THEN 1 ELSE 0 END, upload_date ASC, processed_date ASC"
            elif order_by == 'channel':
                query += " ORDER BY channel_name, CASE WHEN upload_date IS NULL THEN 1 ELSE 0 END, upload_date DESC"

            # Pagination
            query += " LIMIT ? OFFSET ?"
            params.extend([limit, offset])

            cursor.execute(query, params)

            videos = []
            for row in cursor.fetchall():
                videos.append(self._video_row_to_dict(row, include_summary=False))

            return videos

    def get_total_count(self, channel_id: Optional[str] = None) -> int:
        """Get total count of processed videos (for pagination)"""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            if channel_id:
                cursor.execute("SELECT COUNT(*) as count FROM videos WHERE channel_id = ?", (channel_id,))
            else:
                cursor.execute("SELECT COUNT(*) as count FROM videos")

            row = cursor.fetchone()
            return row['count'] if row else 0

    def get_global_stats(self) -> Dict:
        """Get overall statistics across all channels"""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                SELECT
                    COUNT(*) as total_videos,
                    COUNT(DISTINCT channel_id) as total_channels,
                    SUM(duration_seconds) as total_duration
                FROM videos
            """)

            row = cursor.fetchone()

            total_duration = row['total_duration'] or 0
            total_hours = total_duration / 3600 if total_duration else 0

            return {
                'total_videos': row['total_videos'] or 0,
                'total_channels': row['total_channels'] or 0,
                'total_duration_seconds': total_duration,
                'hours_saved': round(total_hours, 1)
            }

    def migrate_from_processed_txt(self, txt_file_path: str) -> int:
        """
        Migrate video IDs from old processed.txt file
        Returns number of IDs migrated
        """
        if not os.path.exists(txt_file_path):
            return 0

        migrated = 0

        with open(txt_file_path, 'r', encoding='utf-8') as f:
            for line in f:
                video_id = line.strip()
                if video_id:
                    # Add with minimal data (no title/duration available)
                    success = self.add_video(
                        video_id=video_id,
                        channel_id='unknown',
                        title=f'Video {video_id}',
                        channel_name='Unknown Channel'
                    )
                    if success:
                        migrated += 1

        return migrated

    def update_video_processing(
        self,
        video_id: str,
        status: str,
        summary_text: Optional[str] = None,
        error_message: Optional[str] = None,
        email_sent: Optional[bool] = None,
        summary_length: Optional[int] = None
    ):
        """
        Update video processing status and summary
        Used during processing to update video state
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # Build update query dynamically based on provided fields
            updates = ['processing_status = ?']
            params = [status]

            if summary_text is not None:
                updates.append('summary_text = ?')
                params.append(summary_text)

            if summary_length is not None:
                updates.append('summary_length = ?')
                params.append(summary_length)

            if error_message is not None:
                updates.append('error_message = ?')
                params.append(error_message)

            if email_sent is not None:
                updates.append('email_sent = ?')
                params.append(int(email_sent))

            params.append(video_id)

            cursor.execute(f"""
                UPDATE videos
                SET {', '.join(updates)}
                WHERE id = ?
            """, params)

    def get_video_by_id(self, video_id: str) -> Optional[Dict]:
        """Get full video details by ID including summary"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM videos WHERE id = ?
            """, (video_id,))

            row = cursor.fetchone()
            if not row:
                return None

            return self._video_row_to_dict(row, include_summary=True)

    def reset_video_status(self, video_id: str):
        """Reset video processing status to pending for retry"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE videos
                SET processing_status = 'pending',
                    error_message = NULL
                WHERE id = ?
            """, (video_id,))

    def reset_all_data(self):
        """
        Delete all videos from the database
        Returns number of videos deleted
        """
        # Get count first
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) as count FROM videos")
            count = cursor.fetchone()['count']

        # Delete all videos
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM videos")

        # Vacuum in a separate connection (cannot be in a transaction)
        conn = sqlite3.connect(self.db_path)
        conn.execute("VACUUM")
        conn.close()

        return count

    def export_all_videos(self) -> List[Dict]:
        """
        Export all videos from database for backup/export purposes.

        Returns:
            List of video dictionaries with all fields including summary_text
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT
                    id as video_id,
                    title,
                    channel_id,
                    channel_name,
                    duration_seconds,
                    view_count,
                    upload_date,
                    processing_status,
                    summary_text,
                    summary_length,
                    email_sent,
                    processed_date,
                    error_message,
                    created_at,
                    created_at as updated_at
                FROM videos
                ORDER BY processed_date DESC
            """)

            videos = []
            for row in cursor.fetchall():
                videos.append({
                    'video_id': row['video_id'],
                    'title': row['title'],
                    'channel_id': row['channel_id'],
                    'channel_name': row['channel_name'] or row['channel_id'],
                    'duration_seconds': row['duration_seconds'],
                    'view_count': row['view_count'],
                    'upload_date': row['upload_date'],
                    'processing_status': row['processing_status'],
                    'summary_text': row['summary_text'],
                    'summary_length': row['summary_length'],
                    'email_sent': bool(row['email_sent']),
                    'processed_date': row['processed_date'],
                    'error_message': row['error_message'],
                    'created_at': row['created_at'],
                    'updated_at': row['updated_at']
                })

            return videos

    def bulk_insert_videos(self, videos: List[Dict], skip_duplicates: bool = True) -> int:
        """
        Bulk insert videos from import operation.

        Args:
            videos: List of video dictionaries with all fields
            skip_duplicates: If True, skip videos that already exist (by video_id)

        Returns:
            Number of videos inserted

        Raises:
            Exception: If database error occurs (transaction will be rolled back)
        """
        inserted_count = 0

        with self._get_connection() as conn:
            cursor = conn.cursor()

            for video in videos:
                video_id = video.get('video_id')

                if not video_id:
                    continue  # Skip videos without ID

                # Check if exists (if skip_duplicates enabled)
                if skip_duplicates:
                    cursor.execute("SELECT 1 FROM videos WHERE id = ?", (video_id,))
                    if cursor.fetchone():
                        continue  # Skip duplicate

                try:
                    cursor.execute("""
                        INSERT INTO videos
                        (id, channel_id, channel_name, title, duration_seconds, view_count,
                         upload_date, summary_length, summary_text, processing_status,
                         error_message, email_sent, source_type, processed_date, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        video_id,
                        video.get('channel_id', ''),
                        video.get('channel_name'),
                        video.get('title', ''),
                        video.get('duration_seconds'),
                        video.get('view_count'),
                        video.get('upload_date'),
                        video.get('summary_length'),
                        video.get('summary_text'),
                        video.get('processing_status', 'pending'),
                        video.get('error_message'),
                        int(video.get('email_sent', False)),
                        video.get('source_type', 'via_channel'),
                        video.get('processed_date'),
                        video.get('created_at', datetime.now().isoformat())
                    ))
                    inserted_count += 1

                except sqlite3.IntegrityError as e:
                    if skip_duplicates:
                        continue  # Skip on constraint violation
                    else:
                        raise  # Re-raise if not skipping

            conn.commit()

        return inserted_count

    # ========================
    # Settings Management
    # ========================

    def get_setting(self, key: str) -> Optional[str]:
        """
        Get a single setting value from database.
        Automatically decrypts if value is encrypted.

        Args:
            key: Setting key

        Returns:
            Decrypted setting value or None if not found
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT value, encrypted FROM settings WHERE key = ?", (key,))
            row = cursor.fetchone()

            if not row:
                return None

            value, encrypted = row[0], row[1]

            # Decrypt if needed using helper method
            return self._decrypt_value(value) if encrypted else value

    def get_all_settings(self) -> Dict[str, Dict[str, str]]:
        """
        Get all settings from database.
        Automatically decrypts encrypted values.

        Returns:
            Dict mapping setting key to {value, type, description, encrypted}
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT key, value, type, encrypted, description
                FROM settings
                ORDER BY key
            """)

            settings = {}
            for row in cursor.fetchall():
                key, value, type_, encrypted, description = row

                # Decrypt if needed using helper method
                decrypted_value = self._decrypt_value(value) if encrypted else value

                settings[key] = {
                    'value': decrypted_value,
                    'type': type_,
                    'description': description or '',
                    'encrypted': bool(encrypted)
                }

            return settings

    def set_setting(self, key: str, value: str, encrypt: Optional[bool] = None) -> bool:
        """
        Set a single setting value in database.
        Automatically encrypts if setting is marked as secret.

        Args:
            key: Setting key
            value: Setting value (plaintext)
            encrypt: Force encryption (None = auto-detect based on existing setting)

        Returns:
            True if successful
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # Check if setting exists and should be encrypted
            cursor.execute("SELECT encrypted FROM settings WHERE key = ?", (key,))
            row = cursor.fetchone()

            should_encrypt = encrypt if encrypt is not None else (row[0] if row else False)

            # Encrypt if needed using helper method
            final_value = self._encrypt_value(value) if should_encrypt else value

            cursor.execute("""
                INSERT INTO settings (key, value, type, encrypted, description, updated_at)
                VALUES (?, ?, 'text', ?, '', CURRENT_TIMESTAMP)
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    encrypted = excluded.encrypted,
                    updated_at = CURRENT_TIMESTAMP
            """, (key, final_value, int(should_encrypt)))

            conn.commit()
            return True

    def set_multiple_settings(self, settings: Dict[str, str], encrypt_keys: Optional[set] = None) -> int:
        """
        Set multiple settings at once.
        Automatically encrypts values marked as secrets.

        Args:
            settings: Dict mapping setting key to value (plaintext)
            encrypt_keys: Set of keys to encrypt (None = auto-detect)

        Returns:
            Number of settings updated
        """
        updated_count = 0

        with self._get_connection() as conn:
            cursor = conn.cursor()

            # Get existing encryption flags
            cursor.execute("SELECT key, encrypted FROM settings")
            existing_encryption = {row[0]: bool(row[1]) for row in cursor.fetchall()}

            for key, value in settings.items():
                # Determine if should encrypt
                should_encrypt = False
                if encrypt_keys and key in encrypt_keys:
                    should_encrypt = True
                elif key in existing_encryption:
                    should_encrypt = existing_encryption[key]

                # Encrypt if needed using helper method
                final_value = self._encrypt_value(value) if should_encrypt else value

                cursor.execute("""
                    INSERT INTO settings (key, value, type, encrypted, description, updated_at)
                    VALUES (?, ?, 'text', ?, '', CURRENT_TIMESTAMP)
                    ON CONFLICT(key) DO UPDATE SET
                        value = excluded.value,
                        encrypted = excluded.encrypted,
                        updated_at = CURRENT_TIMESTAMP
                """, (key, final_value, int(should_encrypt)))
                updated_count += 1

            conn.commit()

        return updated_count

    def delete_setting(self, key: str) -> bool:
        """
        Delete a setting from database.

        Args:
            key: Setting key

        Returns:
            True if deleted, False if not found
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM settings WHERE key = ?", (key,))
            conn.commit()
            return cursor.rowcount > 0

    # ========================
    # Channels Management
    # ========================

    def get_all_channels(self) -> List[Dict[str, Any]]:
        """
        Get all channels from database.

        Returns:
            List of channel dicts with {channel_id, channel_name, enabled}
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT channel_id, channel_name, enabled, added_at, updated_at
                FROM channels
                ORDER BY channel_name
            """)

            channels = []
            for row in cursor.fetchall():
                channels.append({
                    'channel_id': row[0],
                    'channel_name': row[1],
                    'enabled': bool(row[2]),
                    'added_at': row[3],
                    'updated_at': row[4]
                })

            return channels

    def get_enabled_channels(self) -> Tuple[List[str], Dict[str, str]]:
        """
        Get enabled channels in format compatible with ConfigManager.

        Returns:
            Tuple of (channel_ids list, channel_names dict)
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT channel_id, channel_name
                FROM channels
                WHERE enabled = 1
                ORDER BY channel_name
            """)

            channel_ids = []
            channel_names = {}

            for row in cursor.fetchall():
                channel_id = row[0]
                channel_name = row[1]
                channel_ids.append(channel_id)
                channel_names[channel_id] = channel_name

            return channel_ids, channel_names

    def add_channel(self, channel_id: str, channel_name: str = None) -> bool:
        """
        Add a channel to database.

        Args:
            channel_id: YouTube channel ID
            channel_name: Optional display name

        Returns:
            True if added, False if already exists
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()

            try:
                cursor.execute("""
                    INSERT INTO channels (channel_id, channel_name, enabled)
                    VALUES (?, ?, 1)
                """, (channel_id, channel_name or channel_id))
                conn.commit()
                return True

            except sqlite3.IntegrityError:
                # Already exists
                return False

    def remove_channel(self, channel_id: str) -> bool:
        """
        Remove a channel from database.

        Args:
            channel_id: YouTube channel ID

        Returns:
            True if removed, False if not found
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM channels WHERE channel_id = ?", (channel_id,))
            conn.commit()
            return cursor.rowcount > 0

    def update_channel(self, channel_id: str, channel_name: str = None, enabled: bool = None) -> bool:
        """
        Update channel properties.

        Args:
            channel_id: YouTube channel ID
            channel_name: Optional new name
            enabled: Optional enabled status

        Returns:
            True if updated, False if not found
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()

            updates = []
            params = []

            if channel_name is not None:
                updates.append("channel_name = ?")
                params.append(channel_name)

            if enabled is not None:
                updates.append("enabled = ?")
                params.append(int(enabled))

            if not updates:
                return False

            updates.append("updated_at = CURRENT_TIMESTAMP")
            params.append(channel_id)

            query = f"UPDATE channels SET {', '.join(updates)} WHERE channel_id = ?"
            cursor.execute(query, params)
            conn.commit()

            return cursor.rowcount > 0

    def set_channels(self, channels: List[str], channel_names: Dict[str, str] = None) -> bool:
        """
        Replace all channels with new list.

        Args:
            channels: List of channel IDs
            channel_names: Optional dict mapping channel_id to name

        Returns:
            True if successful
        """
        names = channel_names or {}

        with self._get_connection() as conn:
            cursor = conn.cursor()

            # Clear existing channels
            cursor.execute("DELETE FROM channels")

            # Insert new channels
            for channel_id in channels:
                channel_name = names.get(channel_id, channel_id)
                cursor.execute("""
                    INSERT INTO channels (channel_id, channel_name, enabled)
                    VALUES (?, ?, 1)
                """, (channel_id, channel_name))

            conn.commit()
            return True


if __name__ == '__main__':
    # Test the database
    print("Testing VideoDatabase...")

    db = VideoDatabase('test_videos.db')

    # Test adding videos
    print("\n1. Adding test videos...")
    db.add_video('video1', 'channel1', 'How AI Works', 'Tech Channel', 600, 150)
    db.add_video('video2', 'channel1', 'Future of AI', 'Tech Channel', 900, 200)
    db.add_video('video3', 'channel2', 'Cooking Basics', 'Food Channel', 1200, 300)

    # Test stats
    print("\n2. Channel stats:")
    stats = db.get_channel_stats('channel1')
    print(f"   Channel 1: {stats}")

    print("\n3. All channel stats:")
    all_stats = db.get_all_channel_stats()
    for channel_id, stats in all_stats.items():
        print(f"   {channel_id}: {stats}")

    print("\n4. Global stats:")
    global_stats = db.get_global_stats()
    print(f"   {global_stats}")

    print("\n5. Processed videos feed:")
    videos = db.get_processed_videos(limit=10)
    for video in videos:
        print(f"   • {video['title']} ({video['duration_formatted']})")
        print(f"     {video['channel_name']} • {video['processed_date_formatted']}")

    print("\n6. Total count:")
    print(f"   {db.get_total_count()} videos")

    # Cleanup
    import os
    os.remove('test_videos.db')

    print("\n✅ Tests complete")
