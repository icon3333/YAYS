#!/usr/bin/env python3
"""
SQLite Database Manager for YouTube Summarizer
Tracks processed videos with metadata for stats and feed
"""

import sqlite3
import os
from typing import List, Dict, Optional, Tuple
from datetime import datetime, timedelta
from contextlib import contextmanager

from src.utils.formatters import format_duration, format_views, format_upload_date, format_processed_date


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

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_source_type
                ON videos(source_type)
            """)

            conn.commit()

            # Run migration to add source_type column to existing databases
            self._migrate_add_source_type()

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
                videos.append({
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
                })

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

            return {
                'id': row['id'],
                'channel_id': row['channel_id'],
                'channel_name': row['channel_name'],
                'title': row['title'],
                'duration_seconds': row['duration_seconds'],
                'duration_formatted': format_duration(row['duration_seconds']),
                'view_count': row['view_count'],
                'view_count_formatted': format_views(row['view_count']),
                'upload_date': row['upload_date'],
                'upload_date_formatted': format_upload_date(row['upload_date']),
                'processed_date': row['processed_date'],
                'processed_date_formatted': format_processed_date(row['processed_date']),
                'summary_text': row['summary_text'],
                'processing_status': row['processing_status'],
                'error_message': row['error_message'],
                'email_sent': bool(row['email_sent']),
                'summary_length': row['summary_length'],
                'source_type': row['source_type'] if 'source_type' in row.keys() else 'via_channel'
            }

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
