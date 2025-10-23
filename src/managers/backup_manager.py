#!/usr/bin/env python3
"""
Centralized Backup Manager
Handles all backup operations with automatic rotation and clear naming
"""

import os
import shutil
import glob
from datetime import datetime
from typing import Optional, List, Tuple
from pathlib import Path


class BackupManager:
    """
    Centralized backup manager with rotation and clear naming

    Backup naming format: {backup_type}_{timestamp}_{original_filename}
    Example: config_20250123_143022_config.txt

    Backup types:
    - config: config.txt backups
    - env: .env backups
    - db: database backups
    - update: backups created during update.sh
    - manual: manual user-initiated backups
    """

    def __init__(self, backup_dir: str = '.backups', max_backups_per_type: int = 20):
        """
        Initialize backup manager

        Args:
            backup_dir: Directory to store all backups
            max_backups_per_type: Maximum backups to keep per type (default: 20)
        """
        self.backup_dir = backup_dir
        self.max_backups = max_backups_per_type

        # Create backup directory if it doesn't exist
        os.makedirs(self.backup_dir, exist_ok=True)

    def create_backup(self, source_path: str, backup_type: str = 'manual') -> Optional[str]:
        """
        Create a backup of a file with automatic rotation

        Args:
            source_path: Path to file to backup
            backup_type: Type of backup (config, env, db, update, manual)

        Returns:
            Path to created backup file, or None if failed
        """
        if not os.path.exists(source_path):
            print(f"⚠️  Source file not found: {source_path}")
            return None

        try:
            # Generate backup filename with microsecond precision
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
            original_filename = os.path.basename(source_path)
            backup_filename = f"{backup_type}_{timestamp}_{original_filename}"
            backup_path = os.path.join(self.backup_dir, backup_filename)

            # Create backup
            shutil.copy2(source_path, backup_path)

            # Rotate backups for this type
            self._rotate_backups(backup_type, original_filename)

            print(f"✅ Created backup: {backup_filename}")
            return backup_path

        except Exception as e:
            print(f"❌ Failed to create backup: {e}")
            return None

    def _rotate_backups(self, backup_type: str, original_filename: str):
        """
        Rotate backups, keeping only the most recent max_backups files

        Args:
            backup_type: Type of backup to rotate
            original_filename: Original filename (for filtering)
        """
        try:
            # Find all backups matching this type and filename
            pattern = os.path.join(self.backup_dir, f"{backup_type}_*_{original_filename}")
            backup_files = sorted(glob.glob(pattern))

            # If we have more than max_backups, delete oldest ones
            if len(backup_files) > self.max_backups:
                files_to_delete = backup_files[:-self.max_backups]
                for old_backup in files_to_delete:
                    try:
                        os.remove(old_backup)
                        print(f"🗑️  Rotated out old backup: {os.path.basename(old_backup)}")
                    except Exception as e:
                        print(f"⚠️  Failed to delete old backup {old_backup}: {e}")

        except Exception as e:
            print(f"⚠️  Error during backup rotation: {e}")

    def list_backups(self, backup_type: Optional[str] = None,
                     original_filename: Optional[str] = None) -> List[Tuple[str, str, str]]:
        """
        List all backups, optionally filtered by type and/or filename

        Args:
            backup_type: Filter by backup type (optional)
            original_filename: Filter by original filename (optional)

        Returns:
            List of tuples: (backup_path, backup_type, timestamp)
        """
        try:
            # Build search pattern
            if backup_type and original_filename:
                pattern = f"{backup_type}_*_{original_filename}"
            elif backup_type:
                pattern = f"{backup_type}_*"
            elif original_filename:
                pattern = f"*_{original_filename}"
            else:
                pattern = "*"

            full_pattern = os.path.join(self.backup_dir, pattern)
            backup_files = sorted(glob.glob(full_pattern), reverse=True)

            # Parse backup files
            backups = []
            for backup_path in backup_files:
                filename = os.path.basename(backup_path)
                parts = filename.split('_', 2)

                if len(parts) >= 3:
                    b_type = parts[0]
                    timestamp = parts[1]
                    backups.append((backup_path, b_type, timestamp))

            return backups

        except Exception as e:
            print(f"⚠️  Error listing backups: {e}")
            return []

    def get_latest_backup(self, backup_type: str, original_filename: str) -> Optional[str]:
        """
        Get the most recent backup for a specific type and filename

        Args:
            backup_type: Type of backup
            original_filename: Original filename

        Returns:
            Path to most recent backup, or None if not found
        """
        backups = self.list_backups(backup_type, original_filename)

        if backups:
            return backups[0][0]  # Return path of most recent

        return None

    def restore_backup(self, backup_path: str, restore_path: str) -> bool:
        """
        Restore a backup file to its original location

        Args:
            backup_path: Path to backup file
            restore_path: Path where to restore the file

        Returns:
            True if successful, False otherwise
        """
        if not os.path.exists(backup_path):
            print(f"❌ Backup file not found: {backup_path}")
            return False

        try:
            # Create a backup of current file before restoring
            if os.path.exists(restore_path):
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                pre_restore_backup = f"{restore_path}.pre-restore.{timestamp}"
                shutil.copy2(restore_path, pre_restore_backup)
                print(f"✅ Created pre-restore backup: {pre_restore_backup}")

            # Restore backup
            shutil.copy2(backup_path, restore_path)
            print(f"✅ Restored from backup: {os.path.basename(backup_path)}")
            return True

        except Exception as e:
            print(f"❌ Failed to restore backup: {e}")
            return False

    def cleanup_old_backups(self, days: int = 30) -> int:
        """
        Delete backups older than specified days

        Args:
            days: Delete backups older than this many days

        Returns:
            Number of backups deleted
        """
        try:
            import time

            deleted_count = 0
            cutoff_time = time.time() - (days * 86400)

            pattern = os.path.join(self.backup_dir, '*')
            backup_files = glob.glob(pattern)

            for backup_path in backup_files:
                if os.path.isfile(backup_path):
                    file_mtime = os.path.getmtime(backup_path)

                    if file_mtime < cutoff_time:
                        try:
                            os.remove(backup_path)
                            deleted_count += 1
                            print(f"🗑️  Deleted old backup: {os.path.basename(backup_path)}")
                        except Exception as e:
                            print(f"⚠️  Failed to delete {backup_path}: {e}")

            if deleted_count > 0:
                print(f"✅ Cleaned up {deleted_count} old backups")

            return deleted_count

        except Exception as e:
            print(f"❌ Error during cleanup: {e}")
            return 0

    def get_backup_stats(self) -> dict:
        """
        Get statistics about backups

        Returns:
            Dictionary with backup statistics
        """
        try:
            backups = self.list_backups()

            # Count by type
            type_counts = {}
            total_size = 0

            for backup_path, backup_type, _ in backups:
                if backup_type not in type_counts:
                    type_counts[backup_type] = 0
                type_counts[backup_type] += 1

                if os.path.exists(backup_path):
                    total_size += os.path.getsize(backup_path)

            return {
                'total_backups': len(backups),
                'by_type': type_counts,
                'total_size_mb': round(total_size / (1024 * 1024), 2),
                'backup_dir': self.backup_dir,
                'max_per_type': self.max_backups
            }

        except Exception as e:
            print(f"⚠️  Error getting backup stats: {e}")
            return {}


# Convenience function for backward compatibility
def create_backup(source_path: str, backup_type: str = 'manual') -> Optional[str]:
    """Create a backup using the default backup manager"""
    manager = BackupManager()
    return manager.create_backup(source_path, backup_type)


if __name__ == '__main__':
    # Test the backup manager
    print("Testing BackupManager...")

    manager = BackupManager('.backups_test', max_backups_per_type=3)

    # Create test file
    test_file = 'test_config.txt'
    with open(test_file, 'w') as f:
        f.write("Test configuration\n")

    # Test creating backups
    print("\n1. Creating 5 backups (should keep only 3):")
    for i in range(5):
        manager.create_backup(test_file, 'config')
        import time
        time.sleep(0.1)  # Small delay to ensure different timestamps

    # Test listing backups
    print("\n2. Listing backups:")
    backups = manager.list_backups('config', 'test_config.txt')
    print(f"   Found {len(backups)} backups")
    for path, btype, timestamp in backups:
        print(f"   - {os.path.basename(path)}")

    # Test getting latest backup
    print("\n3. Getting latest backup:")
    latest = manager.get_latest_backup('config', 'test_config.txt')
    print(f"   Latest: {os.path.basename(latest)}")

    # Test backup stats
    print("\n4. Backup statistics:")
    stats = manager.get_backup_stats()
    print(f"   {stats}")

    # Cleanup
    import shutil
    shutil.rmtree('.backups_test')
    os.remove(test_file)

    print("\n✅ Tests complete")
