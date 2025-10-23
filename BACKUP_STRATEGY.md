# Backup Strategy

## Overview

All backups are managed by the centralized `BackupManager` in `src/managers/backup_manager.py`.
Backups are stored in the `.backups/` directory with automatic rotation to prevent disk bloat.

## Backup Location

```
.backups/
├── config_20251023_143022_900530_config.txt
├── env_20251023_143023_050300_.env
└── update_20251023_140000_123456_.env
```

## Naming Convention

Format: `{type}_{timestamp}_{filename}`

- **type**: Backup type (config, env, update, db, manual)
- **timestamp**: YYYYMMDD_HHMMSS_microseconds (e.g., 20251023_143022_900530)
- **filename**: Original filename (e.g., config.txt, .env)

## Backup Types

| Type | Description | Max Backups |
|------|-------------|-------------|
| `config` | config.txt changes from Web UI | 20 |
| `env` | .env changes from Web UI | 20 |
| `update` | Backups during update.sh | 10 |
| `db` | Database backups (future) | 20 |
| `manual` | User-initiated backups | 20 |

## When Backups Are Created

### 1. Settings Changes (Web UI)

**User clicks "Save All Settings":**
- 1 backup for all .env settings (batch)
- 1 backup for all config settings (batch)
- **Total: 2 backups per save operation** ✅

**Breakdown:**
```
User saves: OpenAI key, Email, LOG_LEVEL, SUMMARY_LENGTH, SKIP_SHORTS
├── .env update: 1 backup (OpenAI key, Email, LOG_LEVEL)
└── config update: 1 backup (SUMMARY_LENGTH, SKIP_SHORTS)
Total: 2 backups
```

### 2. AI Prompt Changes

**User saves AI prompt:**
- 1 backup before updating prompt
- **Total: 1 backup per prompt save** ✅

### 3. Channel Changes

**User adds/removes channels:**
- 1 backup before updating channels
- **Total: 1 backup per channel operation** ✅

### 4. Settings Reset

**User resets settings to defaults:**
- 1 backup before reset
- **Total: 1 backup per reset** ✅

### 5. System Updates

**User runs update.sh:**
- 1 backup of .env (timestamped with 'update' type)
- 1 backup of config.txt (timestamped with 'update' type)
- **Total: 2 backups per update.sh run** ✅

## Automatic Rotation

Backups are automatically rotated to prevent disk bloat:

- **Rotation trigger**: After each `create_backup()` call
- **Strategy**: Keep most recent N backups per type
- **Action**: Oldest backups automatically deleted

**Example (max 3 backups):**
```
Backup 1: config_20251023_100000_... ← Kept
Backup 2: config_20251023_110000_... ← Kept
Backup 3: config_20251023_120000_... ← Kept
Backup 4: config_20251023_130000_... ← Kept, Backup 1 deleted ✅
Backup 5: config_20251023_140000_... ← Kept, Backup 2 deleted ✅
```

## Disk Usage Estimates

**Typical backup sizes:**
- config.txt: ~2-5 KB
- .env: ~0.5-1 KB

**Maximum disk usage:**
```
Config backups: 20 × 5 KB   = 100 KB
Env backups:    20 × 1 KB   = 20 KB
Update backups: 10 × 6 KB   = 60 KB
Total maximum:              ≈ 180 KB
```

**Real-world usage:**
Most users will have 5-10 backups at any time, totaling ~30-60 KB.

## Backup Retention

### Active Backups (Automatic Rotation)
- **Config**: Last 20 backups
- **Env**: Last 20 backups
- **Update**: Last 10 backups

### Time-based Cleanup (Optional)
Can be triggered manually via `backup_manager.cleanup_old_backups(days=30)`:
- Deletes backups older than specified days
- Useful for long-term maintenance
- Not enabled by default

## Manual Backup Operations

### Create Backup
```python
from src.managers.backup_manager import BackupManager

manager = BackupManager()
manager.create_backup('config.txt', 'manual')
```

### List Backups
```python
# All backups
backups = manager.list_backups()

# Config backups only
config_backups = manager.list_backups('config')

# Specific file
file_backups = manager.list_backups('config', 'config.txt')
```

### Restore Backup
```python
# Get latest backup
latest = manager.get_latest_backup('config', 'config.txt')

# Restore it
manager.restore_backup(latest, 'config.txt')
```

### View Statistics
```python
stats = manager.get_backup_stats()
# Returns: {'total_backups': 15, 'by_type': {'config': 8, 'env': 7}, ...}
```

### Cleanup Old Backups
```python
# Delete backups older than 30 days
deleted = manager.cleanup_old_backups(days=30)
```

## Frequency Summary

**Typical usage scenarios:**

### Light User (occasional changes)
- Updates settings: Once per week → 2 backups/week
- Updates prompt: Once per month → 1 backup/month
- Runs update.sh: Once per month → 2 backups/month
- **Total**: ~10 backups/month, ~50 KB

### Medium User (regular changes)
- Updates settings: 3x per week → 6 backups/week
- Updates prompt: 2x per month → 2 backups/month
- Runs update.sh: 2x per month → 4 backups/month
- **Total**: ~30 backups/month, auto-rotated to ~20, ~100 KB

### Heavy User (daily tweaking)
- Updates settings: Daily → 14 backups/week
- Updates prompt: Weekly → 4 backups/month
- Runs update.sh: Weekly → 8 backups/month
- **Total**: Hits rotation limits, stays at ~30 backups, ~150 KB

## Best Practices

### DO ✅
- Let automatic rotation handle cleanup
- Trust the backup system before risky operations
- Use backup stats to monitor disk usage
- Keep rotation limits reasonable (current: 20)

### DON'T ❌
- Manually delete backups from `.backups/`
- Set rotation limits too high (>50)
- Disable backups to save disk space
- Store large files in config/env (keep them small)

## Troubleshooting

### "Too many backups?"
Check stats: `backup_manager.get_backup_stats()`
- If total > 100: Consider lowering rotation limits
- If size > 1 MB: Check if large files in config.txt

### "Can't find backup"
List backups: `backup_manager.list_backups('config', 'config.txt')`
- Backups auto-rotate after limit (check limits)
- Check backup type (config vs env vs update)

### "Restore failed"
Check backup exists: `os.path.exists(backup_path)`
- May have been rotated out
- Use `get_latest_backup()` to find most recent

## Monitoring

### Check Backup Status
```bash
# List all backups
ls -lh .backups/

# Count backups by type
ls .backups/ | cut -d_ -f1 | sort | uniq -c

# Check disk usage
du -sh .backups/
```

### Expected Output
```bash
$ ls -lh .backups/
total 180K
-rw-r--r-- 1 user user 3.2K Oct 23 14:30 config_20251023_143000_...
-rw-r--r-- 1 user user 3.2K Oct 23 14:31 config_20251023_143100_...
-rw-r--r-- 1 user user 0.8K Oct 23 14:30 env_20251023_143000_...
-rw-r--r-- 1 user user 0.8K Oct 23 14:31 env_20251023_143100_...

$ du -sh .backups/
180K    .backups/
```

## Emergency Recovery

If `.backups/` is corrupted or deleted:
1. Settings will still work (backups are optional safety net)
2. New backups will be created on next change
3. Can restore from update.sh backups if recent

**Prevention**: `.backups/` is in `.gitignore` and excluded from docker volumes, making it local to host machine.
