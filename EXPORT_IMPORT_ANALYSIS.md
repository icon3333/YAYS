# YAYS Export/Import Functionality - Complete Reference

## 🔒 SECURITY REVIEW SUMMARY (Updated: 2025-10-22)

### ✅ Security Status: VERIFIED SECURE

**Credentials Protection Status:**
- ❌ **OPENAI_API_KEY** - NEVER exported (protected)
- ❌ **SMTP_PASS** (Gmail App Password) - NEVER exported (protected)
- ✅ **TARGET_EMAIL** - Exported (safe - just email address, no password)
- ✅ **SMTP_USER** - Exported (safe - just email address, no password)

**Changes Made:**
1. **Fixed EXCLUDED_CREDENTIALS** in `export_manager.py:41-48`
   - Removed `TARGET_EMAIL` from exclusion list (now exported)
   - Removed `SMTP_USER` from exclusion list (now exported)
   - Removed unused entries (`SMTP_SERVER`, `SMTP_PORT`, `SMTP_USERNAME`)
   - Kept only actual secrets: `OPENAI_API_KEY`, `SMTP_PASS`, `SMTP_PASSWORD`

2. **Verified Export Includes:**
   - ✅ All Channels / Feeds
   - ✅ Application Settings (⚙️)
   - ✅ Video Processing settings (📹)
   - ✅ AI Prompt Template (✏️)
   - ✅ Email configuration: Target Email and Gmail SMTP User

3. **Verified Import Security:**
   - ✅ Import only processes what's in export file
   - ✅ Credentials not in export = can't be imported = existing credentials preserved
   - ✅ No credential overwrite risk

**Security Guarantee:**
> All API keys and passwords remain on the source system and are NEVER included in backup files. Email addresses (which are not sensitive) are safely exported for backup/restore convenience.

---

## QUICK REFERENCE

### Files Handling Export & Import:
1. **Export Manager**: `/home/user/YAYS/src/managers/export_manager.py` (375 lines)
2. **Import Manager**: `/home/user/YAYS/src/managers/import_manager.py` (597 lines)
3. **Web API**: `/home/user/YAYS/web.py` (lines 3295-3572)
4. **Supporting**: Settings Manager, Config Manager, Database Manager

---

## 1. EXPORT COMPLETE BACKUP FUNCTIONALITY

### Export Entry Point
**File**: `/home/user/YAYS/src/managers/export_manager.py` lines 110-143

**Method**: `export_complete_backup_json()`
- Returns: Dictionary with all exportable data
- Includes: Channels + Videos + Settings + AI Prompt
- Excludes: All credentials (see EXCLUDED_CREDENTIALS)

**Export Structure**:
```python
{
    "export_level": "complete",
    "export_timestamp": "ISO 8601 datetime",
    "schema_version": "1.0",
    "metadata": {
        "application": "YAYS",
        "application_version": "2.2.0",
        "total_channels": int,
        "total_videos": int
    },
    "channels": [
        {
            "channel_id": "UC...",
            "channel_name": "Name or null",
            "added_date": null
        }
    ],
    "videos": [...],  # All videos with metadata
    "settings": {...}  # Non-secret settings
}
```

### Data Collection Process

**Channels** (exported via ConfigManager):
```python
# From export_manager.py lines 213-233
def _get_channels(self) -> List[Dict[str, Any]]:
    channels_list = self.config_manager.export_channels()
    # Returns list of {channel_id, channel_name, added_date}
```

**Videos** (exported via VideoDatabase):
```python
# From export_manager.py lines 235-249
def _get_videos(self) -> List[Dict[str, Any]]:
    videos = self.db.export_all_videos()
    # Returns all videos with summary_text and metadata
```

**Settings** (exported with credential filtering):
```python
# From export_manager.py lines 251-301 (_get_settings method)
settings = {}

# 1. Get config.txt settings (safe)
config_keys = [
    "SUMMARY_LENGTH", "USE_SUMMARY_LENGTH", "SKIP_SHORTS",
    "MAX_VIDEOS_PER_CHANNEL", "CHECK_INTERVAL_MINUTES", "MAX_FEED_ENTRIES"
]

# 2. Get AI prompt
ai_prompt = self.config_manager.get_value("AI", "PROMPT_TEMPLATE", None)

# 3. Get .env settings with credential filtering
env_settings = self.settings_manager.get_all_settings(mask_secrets=False)
for key, value in env_settings.items():
    if key not in self.EXCLUDED_CREDENTIALS:
        settings[key] = value
```

### Web API for Export
**File**: `/home/user/YAYS/web.py` lines 3352-3381

```python
@app.get("/api/export/backup")
async def export_backup():
    """Export Complete Backup (channels + videos + settings + AI prompt)"""
    data = export_manager.export_complete_backup_json()
    filename = export_manager.generate_export_filename("full_backup", "json")
    json_str = json.dumps(data, indent=2, ensure_ascii=False)
    return StreamingResponse(
        io.BytesIO(json_str.encode('utf-8')),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )
```

---

## 2. IMPORT FUNCTIONALITY

### Import Entry Points
**File**: `/home/user/YAYS/src/managers/import_manager.py` lines 122-403

### Step 1: Validation
**Method**: `validate_import_file()` (lines 122-192)

Checks:
- Required fields present (export_level, export_timestamp, schema_version, channels, videos)
- Schema version compatibility
- Channel format validation
- Video format validation
- Settings validation (if complete backup)
- Field length limits

### Step 2: Preview Generation
**Method**: `preview_import()` (lines 194-265)

Returns preview with:
- channels_new: Count of new channels to add
- channels_existing: Count of existing channels
- videos_new: Count of new videos to add
- videos_duplicate: Count of duplicate videos
- settings_changed: Number of settings that will change
- settings_details: List of "KEY: old_value → new_value"
- total_size_mb: File size in MB

### Step 3: Data Import
**Method**: `import_data()` (lines 267-403)

**Import Sequence**:

1. **Create Backup** (line 297):
   ```python
   config_backup = self._create_config_backup(backup_suffix)
   # Creates: config.txt.backup.YYYYMMDD_HHMMSS
   ```

2. **Import Channels** (lines 300-311):
   ```python
   channels_added = self.config_manager.import_channels(channels, merge=True)
   # merge=True: Adds new, updates existing, preserves others
   ```

3. **Import Videos** (lines 313-325):
   ```python
   videos_added = self.db.bulk_insert_videos(videos, skip_duplicates=True)
   # Skips duplicates by video_id
   ```

4. **Import Settings** (lines 327-377):
   ```python
   # Separate settings by destination
   config_settings = {}  # SUMMARY_LENGTH, SKIP_SHORTS, etc.
   env_settings = {}     # All other non-credential settings
   
   # For each setting in import data:
   if key == "ai_prompt_template":
       self.config_manager.set_prompt(value)
   elif key in config_keys:
       config_settings[key] = value
   else:
       env_settings[key] = value
   ```

5. **Rollback on Error** (lines 309-325, 373-377):
   ```python
   if any step fails:
       self._restore_config_backup(config_backup)
       raise
   ```

### Web API for Import
**File**: `/home/user/YAYS/web.py` lines 3384-3572

**Endpoint 1**: POST `/api/import/validate` (lines 3385-3483)
```python
async def validate_import(file: UploadFile = File(...)):
    content = await file.read()
    data = json.loads(content.decode('utf-8'))
    validation_result = import_manager.validate_import_file(data)
    if validation_result.valid:
        preview = import_manager.preview_import(data)
        return {"valid": True, "errors": [], "warnings": [...], "preview": {...}}
```

**Endpoint 2**: POST `/api/import/execute` (lines 3487-3572)
```python
async def execute_import(file: UploadFile = File(...)):
    content = await file.read()
    data = json.loads(content.decode('utf-8'))
    import_result = import_manager.import_data(data)
    return {
        "success": import_result.success,
        "channels_added": import_result.channels_added,
        "videos_added": import_result.videos_added,
        "settings_updated": import_result.settings_updated,
        "errors": import_result.errors
    }
```

---

## 3. CONFIGURATION DATA EXPORT

### Where Config Data Comes From

**Source 1: config.txt** (`/home/user/YAYS/src/managers/config_manager.py`)
- **[CHANNELS]** section → Channels list and names
- **[SETTINGS]** section → Processing settings
- **[PROMPT]** section → AI prompt template

**Source 2: .env file** (`/home/user/YAYS/src/managers/settings_manager.py`)
- Non-credential settings only (see filtering below)

### Settings Exported

**From config.txt** (always exported):
```python
SUMMARY_LENGTH          # Max summary tokens
USE_SUMMARY_LENGTH      # Boolean flag
SKIP_SHORTS             # Boolean flag
MAX_VIDEOS_PER_CHANNEL  # Integer
CHECK_INTERVAL_MINUTES  # Integer
MAX_FEED_ENTRIES        # Integer
ai_prompt_template      # AI prompt text
```

**From .env** (filtered, only actual secrets excluded):
```python
# These ARE exported:
LOG_LEVEL               # DEBUG|INFO|WARNING|ERROR
CHECK_INTERVAL_HOURS    # Integer
MAX_PROCESSED_ENTRIES   # Integer
SEND_EMAIL              # true|false
OPENAI_MODEL            # Model name
TARGET_EMAIL            # ✅ Target email address (exported)
SMTP_USER               # ✅ Gmail SMTP user email (exported)

# These are NOT exported (EXCLUDED_CREDENTIALS - actual secrets only):
OPENAI_API_KEY          # ❌ API key - EXCLUDED
SMTP_PASS               # ❌ Gmail App Password - EXCLUDED
SMTP_PASSWORD           # ❌ Alias for SMTP_PASS - EXCLUDED
```

### Code Reference
**File**: `/home/user/YAYS/src/managers/export_manager.py` lines 41-48

```python
# Only actual secrets are excluded - API keys and passwords
# Email addresses (TARGET_EMAIL, SMTP_USER) ARE exported for backup purposes
EXCLUDED_CREDENTIALS = {
    "OPENAI_API_KEY",   # OpenAI API key - never export
    "SMTP_PASS",        # Gmail App Password - never export
    "SMTP_PASSWORD",    # Alias for SMTP_PASS - never export
}
```

---

## 4. CREDENTIAL HANDLING

### Where Credentials Are Stored
All credentials in `.env` file

### OpenAI API Key
**Variable**: `OPENAI_API_KEY`
**Format**: `sk-[A-Za-z0-9_-]{20,}`
**Validation Pattern**: `^sk-[A-Za-z0-9_-]{20,}$`
**Export**: ❌ NEVER (in EXCLUDED_CREDENTIALS)
**Testing**: `test_openai_key(api_key)` function (line 447-473)

### Gmail App Password
**Variable**: `SMTP_PASS`
**Format**: 16-character app password
**Export**: ❌ NEVER (in EXCLUDED_CREDENTIALS)
**Testing**: `test_smtp_credentials(smtp_user, smtp_pass)` (line 476-499)

### Gmail SMTP User (Email Address)
**Variable**: `SMTP_USER`
**Format**: Email address (e.g., your.email@gmail.com)
**Export**: ✅ YES (exported for backup/restore purposes)
**Security**: Not sensitive - just an email address, no password

### Target Email
**Variable**: `TARGET_EMAIL`
**Format**: Email address (e.g., your.email@example.com)
**Export**: ✅ YES (exported for backup/restore purposes)
**Security**: Not sensitive - just an email address, no password

### How Credentials Are Filtered During Export

**File**: `/home/user/YAYS/src/managers/export_manager.py` lines 41-48

```python
# Credentials to exclude from export (security - these should NOT be exported)
# Only actual secrets are excluded - API keys and passwords
# Email addresses (TARGET_EMAIL, SMTP_USER) ARE exported for backup purposes
EXCLUDED_CREDENTIALS = {
    "OPENAI_API_KEY",   # OpenAI API key - never export
    "SMTP_PASS",        # Gmail App Password - never export
    "SMTP_PASSWORD",    # Alias for SMTP_PASS - never export
}
```

**Filtering Code** (lines 286-290):
```python
# Get all .env settings (unmasked for processing)
env_settings = self.settings_manager.get_all_settings(mask_secrets=False)

# Filter out credentials
for key, value in env_settings.items():
    if key not in self.EXCLUDED_CREDENTIALS:
        settings[key] = value
```

### Credential Security When Displaying to Users

**File**: `/home/user/YAYS/src/managers/settings_manager.py` lines 116-136

```python
def _mask_secret(self, value: str, secret_type: str = 'secret') -> str:
    if not value:
        return ''
    
    if secret_type == 'secret':
        if value.startswith('sk-'):
            # OpenAI key: sk-***...***xxx
            if len(value) > 15:
                return f"{value[:7]}***...***{value[-4:]}"
            return 'sk-***'
        else:
            # Password: all dots
            return '•' * min(len(value), 16)
    
    return value
```

**Usage in API**: `/home/user/YAYS/web.py` around line 3200

```python
@app.get("/api/settings")
async def get_settings():
    """Get all settings (with masked credentials)"""
    settings = settings_manager.get_all_settings(mask_secrets=True)
    # Returns masked values like:
    # OPENAI_API_KEY: "sk-***...***xxxx"
    # SMTP_PASS: "••••••••••••••••"
```

### Credential Testing (Non-Exporting)

**OpenAI Test**:
```python
def test_openai_key(api_key: str) -> Tuple[bool, str]:
    from openai import OpenAI
    client = OpenAI(api_key=api_key)
    # Make minimal API call to test
    response = client.chat.completions.create(
        model="gpt-3.5-turbo",
        max_tokens=5,
        messages=[{"role": "user", "content": "Hi"}]
    )
    return True, "✅ OpenAI API key is valid"
```

**SMTP Test**:
```python
def test_smtp_credentials(smtp_user: str, smtp_pass: str) -> Tuple[bool, str]:
    import smtplib
    server = smtplib.SMTP('smtp.gmail.com', 587, timeout=10)
    server.starttls()
    server.login(smtp_user, smtp_pass)
    server.quit()
    return True, "✅ SMTP credentials are valid"
```

---

## 5. SECURITY FEATURES

### What Is EXPORTED
- Channels and channel names
- Video metadata (title, duration, views)
- Video summaries and processing status
- Application settings (non-sensitive)
- AI prompt templates
- Email sent status and history

### What is PROTECTED (NOT Exported)
1. **OpenAI API Keys** (OPENAI_API_KEY): ❌ NEVER exported - in EXCLUDED_CREDENTIALS
2. **Gmail App Password** (SMTP_PASS): ❌ NEVER exported - in EXCLUDED_CREDENTIALS
3. **Password Aliases** (SMTP_PASSWORD): ❌ NEVER exported - in EXCLUDED_CREDENTIALS

### What is SAFELY EXPORTED (Non-Sensitive Configuration)
1. **Email Addresses** (TARGET_EMAIL, SMTP_USER): ✅ Exported - not sensitive, no passwords
2. **Application Settings**: ✅ Exported - LOG_LEVEL, CHECK_INTERVAL_HOURS, etc.
3. **Video Processing Settings**: ✅ Exported - SUMMARY_LENGTH, SKIP_SHORTS, etc.
4. **AI Configuration**: ✅ Exported - OPENAI_MODEL (model name only, not API key)
5. **Channels and Videos**: ✅ Exported - all channel and video data

### Validation & Safety
- **File Size Limit**: 50 MB maximum
- **JSON Validation**: Full syntax checking
- **Schema Validation**: Version compatibility checking
- **Field Length Limits**:
  - title: max 500 chars
  - summary_text: max 10000 chars
  - error_message: max 1000 chars
  - channel_name: max 200 chars
- **Type Checking**: Data type validation
- **Transaction Safety**: Automatic rollback on error
- **Backup Creation**: Auto-backup before import

---

## 6. KEY FUNCTIONS REFERENCE

### Export Manager
- `export_feed_json()` - Feed level export (channels + videos)
- `export_complete_backup_json()` - Complete backup (+ settings)
- `export_videos_csv()` - CSV export for videos only
- `_get_channels()` - Extract channels from config
- `_get_videos()` - Extract videos from database
- `_get_settings()` - Extract non-secret settings
- `generate_export_filename()` - Create timestamped filename

### Import Manager
- `validate_import_file()` - Full validation with error collection
- `preview_import()` - Generate preview of changes
- `import_data()` - Execute import with rollback
- `_validate_channel()` - Channel-level validation
- `_validate_video()` - Video-level validation
- `_validate_settings()` - Settings validation
- `_create_config_backup()` - Create backup before import
- `_restore_config_backup()` - Restore if import fails

---

## 7. RECENT IMPROVEMENTS (From git)

Latest commits show focus on:
1. **File Locking**: Fixed config.txt lock while importing JSON
2. **Import Scope**: Fixed import export scope handling
3. **Web API Stability**: Fixed import process in web.py
4. **Legacy Support**: Fixed legacy inoreader mentions

---

