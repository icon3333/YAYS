#!/usr/bin/env python3
"""
One-time script to fix channel timestamps after the bug fix.
This sets each channel's added_at to today, so only future videos are processed.
"""

from src.managers.database import VideoDatabase
from datetime import datetime

def fix_timestamps():
    db = VideoDatabase('data/videos.db')

    print("Current channel timestamps:")
    channels = db.get_all_channels()
    for ch in channels:
        print(f"  {ch['channel_name']:30} added: {ch['added_at']}")

    print("\nSetting all channels to today's date...")
    print("This means only videos uploaded from TODAY onwards will be processed.")

    # Get current timestamp
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    # Update each channel
    with db._get_connection() as conn:
        cursor = conn.cursor()
        for ch in channels:
            cursor.execute("""
                UPDATE channels
                SET added_at = ?
                WHERE channel_id = ?
            """, (now, ch['channel_id']))
        conn.commit()

    print("\n✅ Fixed! New timestamps:")
    channels = db.get_all_channels()
    for ch in channels:
        print(f"  {ch['channel_name']:30} added: {ch['added_at']}")

    print("\n📝 From now on, only videos uploaded after today will be processed.")

if __name__ == '__main__':
    fix_timestamps()
