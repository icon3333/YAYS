#!/usr/bin/env python3
"""
YouTube Summarizer - Web Interface (Modern Minimalist)
Black, white, grey only - Two column layout
With auto-fetch channel names from YouTube
"""

import os
import sys
import logging
import subprocess
import signal
import json
import io
from pathlib import Path
from fastapi import FastAPI, HTTPException, File, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi import Request
from pydantic import BaseModel, field_validator
from typing import Dict, List, Optional
import re
from dotenv import load_dotenv
from apscheduler.schedulers.background import BackgroundScheduler

# Load environment variables from .env file
# Create .env from .env.example if it doesn't exist
if not os.path.exists('.env') and os.path.exists('.env.example'):
    import shutil
    shutil.copy2('.env.example', '.env')
    print("✅ Created .env from .env.example")

load_dotenv()

# Setup logging with dynamic log level from environment
log_level = os.getenv('LOG_LEVEL', 'INFO').upper()
logging.basicConfig(
    level=getattr(logging, log_level, logging.INFO),
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger('web')
logger.info(f"Web app starting with log level: {log_level}")

# Import shared modules
from src.managers.config_manager import ConfigManager
from src.managers.settings_manager import SettingsManager, test_openai_key, test_smtp_credentials
from src.managers.database import VideoDatabase
from src.managers.restart_manager import detect_runtime_environment, restart_application
from src.managers.export_manager import ExportManager
from src.managers.import_manager import ImportManager
from src.core.ytdlp_client import YTDLPClient
from src.core.youtube import YouTubeClient

app = FastAPI(
    title="YAYS - Yet Another Youtube Summarizer",
    version="2.0.0",
    description="Modern minimalist design"
)

# Mount static files with custom StaticFiles class to disable caching
from starlette.staticfiles import StaticFiles as StarletteStaticFiles
from starlette.responses import Response

class NoCacheStaticFiles(StarletteStaticFiles):
    """StaticFiles with cache-control headers to prevent caching"""
    def file_response(self, *args, **kwargs) -> Response:
        response = super().file_response(*args, **kwargs)
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response

app.mount("/static", NoCacheStaticFiles(directory="src/static", html=False), name="static")

# Setup templates
templates = Jinja2Templates(directory="src/templates")

# Initialize config manager
config_manager = ConfigManager('config.txt')
settings_manager = SettingsManager('.env')
video_db = VideoDatabase('data/videos.db')
export_manager = ExportManager('data/videos.db', 'config.txt', '.env')
import_manager = ImportManager('data/videos.db', 'config.txt')
ytdlp_client = YTDLPClient()
youtube_client = YouTubeClient(use_ytdlp=True)

# Initialize background scheduler
scheduler = BackgroundScheduler()


def scheduled_video_check():
    """Run process_videos.py as background task (triggered by scheduler)"""
    logger.info("Scheduled video check started")
    try:
        # Use sys.executable to ensure we use the same Python interpreter (venv)
        subprocess.Popen([sys.executable, 'process_videos.py'])
        logger.info("Background processing started successfully")
    except Exception as e:
        logger.error(f"Failed to start scheduled processing: {e}")


@app.on_event("startup")
def start_scheduler():
    """Start the background scheduler when the app starts"""
    try:
        interval_hours = int(os.getenv('CHECK_INTERVAL_HOURS', '6'))

        scheduler.add_job(
            scheduled_video_check,
            'interval',
            hours=interval_hours,
            id='video_check',
            replace_existing=True
        )
        scheduler.start()

        logger.info(f"✅ Background scheduler started (every {interval_hours}h)")

    except Exception as e:
        logger.error(f"Failed to start scheduler: {e}")


@app.on_event("shutdown")
def shutdown_scheduler():
    """Shutdown the scheduler gracefully when the app stops"""
    try:
        scheduler.shutdown()
        logger.info("Background scheduler stopped")
    except Exception as e:
        logger.error(f"Error stopping scheduler: {e}")


# Pydantic models with validation (V2)
class ChannelUpdate(BaseModel):
    channels: List[str]
    names: Dict[str, str]

    @field_validator('channels')
    @classmethod
    def validate_channels(cls, channels):
        """Validate channel ID format"""
        for channel_id in channels:
            if not re.match(r'^(UC[\w-]{22}|@[\w-]+|[\w-]{10,})$', channel_id):
                raise ValueError(f'Invalid channel ID format: {channel_id}')
        return channels

    @field_validator('names')
    @classmethod
    def validate_names(cls, names):
        """Validate channel names"""
        for channel_id, name in names.items():
            if len(name) > 100:
                raise ValueError(f'Channel name too long: {name}')
            if '<' in name or '>' in name or '"' in name:
                raise ValueError(f'Invalid characters in channel name: {name}')
        return names


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """Serve the main web interface"""
    return templates.TemplateResponse("index.html", {"request": request})



@app.get("/api/channels")
async def get_channels():
    """API endpoint to retrieve current channels"""
    try:
        channels, names = config_manager.get_channels()
        logger.info(f"Loaded {len(channels)} channels")
        return {"channels": channels, "names": names}
    except Exception as e:
        logger.error(f"Error loading channels: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/channels")
async def save_channels(data: ChannelUpdate):
    """API endpoint to save updated channel list"""
    try:
        success = config_manager.write_config(data.channels, data.names)
        if not success:
            raise HTTPException(status_code=500, detail="Failed to save config")
        logger.info(f"Saved {len(data.channels)} channels")
        return {"status": "success", "message": f"Saved {len(data.channels)} channels"}
    except ValueError as e:
        logger.warning(f"Validation error: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error saving channels: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/channels/{channel_id}/fetch-initial-videos")
async def fetch_initial_videos(channel_id: str):
    """
    Fetch and PROCESS the last X videos for a newly added channel
    Adds videos to database as 'pending' and triggers background processing
    """
    try:
        # Get settings
        config = config_manager.read_config()
        max_videos = int(config.get('settings', {}).get('MAX_VIDEOS_PER_CHANNEL', '5'))
        skip_shorts = config.get('settings', {}).get('SKIP_SHORTS', 'true').lower() == 'true'

        logger.info(f"Fetching and processing last {max_videos} videos for new channel: {channel_id}")

        # Fetch videos using YouTubeClient (yt-dlp with RSS fallback)
        videos = youtube_client.get_channel_videos(channel_id, max_videos, skip_shorts)

        if not videos:
            logger.warning(f"Could not fetch videos for channel: {channel_id}")
            return {
                "status": "error",
                "message": "Could not fetch videos from channel",
                "videos_fetched": 0
            }

        # Add videos to database as 'pending' for processing
        channel_name = config.get('channel_names', {}).get(channel_id, channel_id)

        for video in videos:
            # Fetch metadata using ytdlp_client
            metadata = ytdlp_client.get_video_metadata(video['id'])

            if metadata:
                duration_seconds = metadata.get('duration')
                view_count = metadata.get('view_count')
                upload_date = metadata.get('upload_date_string') or metadata.get('upload_date')
                # Convert YYYYMMDD to YYYY-MM-DD if needed
                if upload_date and len(upload_date) == 8 and '-' not in upload_date:
                    upload_date = f"{upload_date[:4]}-{upload_date[4:6]}-{upload_date[6:]}"
            else:
                duration_seconds = None
                view_count = None
                upload_date = None

            # Add video with status='pending' (will be processed by process_videos.py)
            video_db.add_video(
                video_id=video['id'],
                channel_id=channel_id,
                title=video['title'],
                channel_name=channel_name,
                duration_seconds=duration_seconds,
                view_count=view_count,
                upload_date=upload_date,
                processing_status='pending',  # Mark as pending for processing
                summary_length=None,
                summary_text=None
            )

        logger.info(f"Added {len(videos)} videos as pending for channel {channel_id}")

        # Trigger immediate processing in background
        try:
            subprocess.Popen(['python3', 'process_videos.py'])
            logger.info("Started background processing")
        except Exception as e:
            logger.error(f"Failed to start background processing: {e}")

        return {
            "status": "success",
            "message": f"Fetched {len(videos)} videos. Processing started in background.",
            "videos_fetched": len(videos)
        }

    except Exception as e:
        logger.error(f"Error fetching initial videos for {channel_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    try:
        config_manager.ensure_config_exists()
        return {"status": "healthy", "version": "2.0.0"}
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return JSONResponse(
            status_code=503,
            content={"status": "unhealthy", "error": str(e)}
        )


@app.get("/api/fetch-channel-name/{channel_input:path}")
async def fetch_channel_name(channel_input: str):
    """
    Fetch channel name and ID from YouTube using yt-dlp
    Accepts: channel ID (UCxxxx), @handle, or YouTube URLs
    """
    try:
        # Use yt-dlp for robust channel ID extraction
        channel_info = ytdlp_client.extract_channel_info(channel_input)

        if not channel_info:
            raise HTTPException(status_code=404, detail="Channel not found or could not be resolved")

        channel_id = channel_info['channel_id']
        channel_name = channel_info['channel_name']

        logger.info(f"Fetched channel name: {channel_name} for {channel_id}")

        return {
            "channel_id": channel_id,
            "channel_name": channel_name
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching channel name: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch channel name: {str(e)}")


# ============================================================================
# SETTINGS API ENDPOINTS
# ============================================================================

class SettingUpdate(BaseModel):
    """Model for updating a single setting"""
    key: str
    value: str


class MultipleSettingsUpdate(BaseModel):
    """Model for updating multiple settings at once"""
    settings: Dict[str, str]


class PromptUpdate(BaseModel):
    """Model for updating the prompt template"""
    prompt: str

    @field_validator('prompt')
    @classmethod
    def validate_prompt(cls, prompt):
        """Validate prompt has required placeholders"""
        if len(prompt.strip()) < 10:
            raise ValueError('Prompt is too short')
        if len(prompt) > 5000:
            raise ValueError('Prompt is too long (max 5000 chars)')
        return prompt


class CredentialTest(BaseModel):
    """Model for testing credentials"""
    credential_type: str  # 'openai' or 'smtp'
    test_value: Optional[str] = None  # For OpenAI API key
    test_user: Optional[str] = None   # For SMTP user
    test_pass: Optional[str] = None   # For SMTP password


@app.get("/api/settings")
async def get_settings():
    """Get all settings (with masked credentials)"""
    try:
        # Get .env settings (masked)
        env_settings = settings_manager.get_all_settings(mask_secrets=True)

        # Get config.txt settings
        config = config_manager.read_config()
        config_settings = config.get('settings', {})

        logger.info("Retrieved all settings")

        return {
            "env": env_settings,
            "config": config_settings,
            "restart_required": False
        }

    except Exception as e:
        logger.error(f"Error getting settings: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/settings")
async def update_settings(data: MultipleSettingsUpdate):
    """Update multiple settings at once"""
    try:
        # Debug logging
        logger.info(f"Received settings update request with {len(data.settings)} settings")
        logger.debug(f"Settings keys: {list(data.settings.keys())}")

        env_updates = {}
        config_updates = {}

        # Separate env vs config settings
        for key, value in data.settings.items():
            if key in settings_manager.env_schema:
                env_updates[key] = value
            elif key in ['SUMMARY_LENGTH', 'USE_SUMMARY_LENGTH', 'SKIP_SHORTS', 'MAX_VIDEOS_PER_CHANNEL']:
                config_updates[key] = value

        results = {"env": None, "config": None, "restart_required": False}

        # Update .env settings
        if env_updates:
            logger.info(f"Updating {len(env_updates)} env settings: {list(env_updates.keys())}")
            success, message, errors = settings_manager.update_multiple_settings(env_updates)
            if not success:
                logger.error(f"Validation failed: {errors}")
                raise HTTPException(status_code=400, detail={"message": message, "errors": errors})

            # Reload environment variables so changes take effect immediately
            load_dotenv(override=True)
            logger.info("Reloaded environment variables from .env")

            results["env"] = message
            results["restart_required"] = True
            logger.info(f"Updated .env settings: {list(env_updates.keys())}")

        # Update config.txt settings
        if config_updates:
            # Validate config settings before writing
            validation_errors = []

            for key, value in config_updates.items():
                if key == 'SUMMARY_LENGTH':
                    if value and not value.isdigit():
                        validation_errors.append(f"SUMMARY_LENGTH must be a number")
                    elif value and (int(value) < 100 or int(value) > 10000):
                        validation_errors.append(f"SUMMARY_LENGTH must be between 100 and 10000")

                elif key == 'MAX_VIDEOS_PER_CHANNEL':
                    if value and not value.isdigit():
                        validation_errors.append(f"MAX_VIDEOS_PER_CHANNEL must be a number")
                    elif value and (int(value) < 1 or int(value) > 50):
                        validation_errors.append(f"MAX_VIDEOS_PER_CHANNEL must be between 1 and 50")

                elif key in ['USE_SUMMARY_LENGTH', 'SKIP_SHORTS']:
                    if value and value not in ['true', 'false']:
                        validation_errors.append(f"{key} must be 'true' or 'false'")

            if validation_errors:
                logger.error(f"Config validation failed: {validation_errors}")
                raise HTTPException(status_code=400, detail={"message": "Validation failed", "errors": validation_errors})

            # Use config_manager.set_setting() for thread-safe updates with locking
            try:
                updated_count = 0
                for key, value in config_updates.items():
                    # Skip empty values (partial update support)
                    if not value:
                        continue

                    success = config_manager.set_setting(key, value)
                    if success:
                        updated_count += 1
                    else:
                        logger.warning(f"Failed to update config setting: {key}")

                results["config"] = f"Updated {updated_count} config settings"
                logger.info(f"Updated config.txt settings: {list(config_updates.keys())}")

            except Exception as e:
                logger.error(f"Error updating config.txt: {e}")
                raise HTTPException(status_code=500, detail=f"Failed to update config: {str(e)}")

        return results

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating settings: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/settings/prompt")
async def get_prompt():
    """Get the current prompt template"""
    try:
        config = config_manager.read_config()
        prompt = config.get('prompt', '')

        logger.info("Retrieved prompt template")

        return {
            "prompt": prompt,
            "length": len(prompt)
        }

    except Exception as e:
        logger.error(f"Error getting prompt: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/settings/prompt")
async def update_prompt(data: PromptUpdate):
    """Update the prompt template"""
    try:
        # Validate prompt
        if not data.prompt or len(data.prompt.strip()) < 10:
            raise HTTPException(status_code=400, detail="Prompt must be at least 10 characters")

        # Use config_manager for thread-safe update with locking and backup
        success = config_manager.set_prompt(data.prompt)

        if not success:
            raise HTTPException(status_code=500, detail="Failed to update prompt")

        logger.info("Updated prompt template")

        return {
            "status": "success",
            "message": "Prompt updated successfully",
            "restart_required": False
        }

    except HTTPException:
        raise
    except ValueError as e:
        logger.warning(f"Validation error: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error updating prompt: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/settings/restart")
async def restart_app():
    """Restart the application (Docker containers or Python processes)"""
    try:
        # Detect environment and get restart instructions
        env_type, command = detect_runtime_environment()

        # Attempt restart
        result = restart_application()

        logger.info(f"Restart requested - Type: {result['restart_type']}, Success: {result['success']}")

        # For Python mode, schedule the restart after response is sent
        if result['restart_type'] == 'python' and result['success'] and 'restart_command' in result:
            import asyncio
            async def delayed_restart():
                await asyncio.sleep(1)  # Give time for response to be sent
                logger.info("Executing Python restart...")
                os.execv(result['restart_command'][0], result['restart_command'])

            asyncio.create_task(delayed_restart())

        return result

    except Exception as e:
        logger.error(f"Error during restart: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/settings/environment")
async def get_environment():
    """Get the detected runtime environment info"""
    try:
        env_type, command = detect_runtime_environment()

        return {
            "environment": env_type,
            "restart_command": command,
            "in_docker": env_type == 'docker'
        }

    except Exception as e:
        logger.error(f"Error detecting environment: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/openai/models")
async def get_openai_models():
    """Fetch available OpenAI models from API"""
    try:
        import openai

        # Reload environment to get latest saved API key
        load_dotenv(override=True)

        api_key = os.getenv('OPENAI_API_KEY', '')
        if not api_key:
            # Return a default list if no API key is configured
            return {
                "models": [
                    {"id": "gpt-4o", "name": "GPT-4o (Latest, Most Capable)"},
                    {"id": "gpt-4o-mini", "name": "GPT-4o Mini (Fast & Affordable)"},
                    {"id": "gpt-4-turbo", "name": "GPT-4 Turbo"},
                    {"id": "gpt-4", "name": "GPT-4"},
                    {"id": "gpt-3.5-turbo", "name": "GPT-3.5 Turbo"}
                ],
                "source": "default"
            }

        # Fetch models from OpenAI API
        client = openai.OpenAI(api_key=api_key)
        models_response = client.models.list()

        # Filter for chat models (GPT models)
        chat_models = []
        model_priorities = {
            "gpt-4o": 1,
            "gpt-4o-mini": 2,
            "gpt-4-turbo": 3,
            "gpt-4": 4,
            "gpt-3.5-turbo": 5
        }

        for model in models_response.data:
            model_id = model.id
            # Include only GPT chat models
            if model_id.startswith("gpt-") and not model_id.endswith("-instruct"):
                # Use base model name for priority
                base_name = model_id.split("-")[0] + "-" + model_id.split("-")[1]
                if "turbo" in model_id:
                    base_name += "-turbo"
                elif "mini" in model_id:
                    base_name += "-mini"

                priority = model_priorities.get(base_name, 999)
                chat_models.append({
                    "id": model_id,
                    "name": model_id,
                    "priority": priority
                })

        # Sort by priority
        chat_models.sort(key=lambda x: (x["priority"], x["id"]))

        # Remove priority from response
        for model in chat_models:
            del model["priority"]

        logger.info(f"Fetched {len(chat_models)} OpenAI models from API")

        return {
            "models": chat_models if chat_models else [
                {"id": "gpt-4o", "name": "GPT-4o (Latest, Most Capable)"},
                {"id": "gpt-4o-mini", "name": "GPT-4o Mini (Fast & Affordable)"},
                {"id": "gpt-4-turbo", "name": "GPT-4 Turbo"},
                {"id": "gpt-4", "name": "GPT-4"},
                {"id": "gpt-3.5-turbo", "name": "GPT-3.5 Turbo"}
            ],
            "source": "api" if chat_models else "default"
        }

    except Exception as e:
        logger.warning(f"Error fetching OpenAI models: {e}, using defaults")
        # Return default list on error
        return {
            "models": [
                {"id": "gpt-4o", "name": "GPT-4o (Latest, Most Capable)"},
                {"id": "gpt-4o-mini", "name": "GPT-4o Mini (Fast & Affordable)"},
                {"id": "gpt-4-turbo", "name": "GPT-4 Turbo"},
                {"id": "gpt-4", "name": "GPT-4"},
                {"id": "gpt-3.5-turbo", "name": "GPT-3.5 Turbo"}
            ],
            "source": "default"
        }


@app.post("/api/settings/test")
async def test_credentials(data: CredentialTest):
    """Test API credentials using provided values or saved values from .env"""
    try:
        if data.credential_type == 'openai':
            # Reload environment to get latest saved values
            load_dotenv(override=True)

            # Use provided value or fall back to .env
            # Handle None and empty string
            api_key = data.test_value if data.test_value else os.getenv('OPENAI_API_KEY', '')
            api_key = api_key.strip() if api_key else ''

            if not api_key:
                return {
                    "success": False,
                    "message": "❌ No OpenAI API key provided. Please enter your API key or save it first."
                }

            success, message = test_openai_key(api_key)
            logger.info(f"OpenAI API test: {message}")

            return {
                "success": success,
                "message": message
            }

        elif data.credential_type == 'smtp':
            # Reload environment to get latest saved values
            load_dotenv(override=True)

            # Use provided values or fall back to .env
            # Handle None and empty string
            logger.debug(f"SMTP test request - test_user: {data.test_user}, test_pass: {'[present]' if data.test_pass else '[empty]'}")

            smtp_user = data.test_user if data.test_user else os.getenv('SMTP_USER', '')
            smtp_pass = data.test_pass if data.test_pass else os.getenv('SMTP_PASS', '')
            smtp_user = smtp_user.strip() if smtp_user else ''
            smtp_pass = smtp_pass.strip() if smtp_pass else ''

            logger.debug(f"SMTP test - Using user: {smtp_user}, pass: {'[present]' if smtp_pass else '[empty]'}")

            if not smtp_user or not smtp_pass:
                missing = []
                if not smtp_user:
                    missing.append("SMTP User")
                if not smtp_pass:
                    missing.append("Gmail App Password")

                return {
                    "success": False,
                    "message": f"❌ Missing credentials: {', '.join(missing)}. Please fill in the fields or save them first."
                }

            success, message = test_smtp_credentials(smtp_user, smtp_pass)
            logger.info(f"SMTP test: {message}")

            return {
                "success": success,
                "message": message
            }

        else:
            raise HTTPException(status_code=400, detail="Invalid credential type")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error testing credentials: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# RESET API ENDPOINTS
# ============================================================================

@app.post("/api/reset/settings")
async def reset_settings():
    """
    Reset Settings: Reset all settings and AI prompt to defaults.
    Channels and feed history are preserved.
    """
    try:
        logger.info("Resetting settings and prompt to defaults")

        # Reset prompt to default
        config_manager.reset_prompt_to_default()

        # Reset all settings in config.txt to defaults
        config_manager.reset_all_settings()

        logger.info("Settings and prompt reset complete")

        return {
            "success": True,
            "message": "✅ Successfully reset all settings and AI prompt to defaults"
        }
    except Exception as e:
        logger.error(f"Error resetting settings: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/reset/youtube-data")
async def reset_youtube_data():
    """
    Reset YouTube Data: Delete all channels and feed history.
    Settings and prompts are preserved.
    """
    try:
        logger.info("Resetting YouTube data (channels + feed)")

        # Get current counts before deletion
        channels, _ = config_manager.get_channels()
        channel_count = len(channels)

        # Delete all videos from database
        video_count = video_db.reset_all_data()

        # Clear channels from config
        config_manager.set_channels([])

        logger.info(f"Reset complete: Deleted {video_count} videos and {channel_count} channels")

        return {
            "success": True,
            "message": f"✅ Successfully deleted {video_count} videos and {channel_count} channels",
            "videos_deleted": video_count,
            "channels_deleted": channel_count
        }
    except Exception as e:
        logger.error(f"Error resetting YouTube data: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/reset/feed-history")
async def reset_feed_history():
    """
    Reset Feed History: Delete all processed videos.
    Channels and settings are preserved.
    """
    try:
        logger.info("Resetting feed history")

        # Delete all videos from database
        video_count = video_db.reset_all_data()

        logger.info(f"Reset complete: Deleted {video_count} videos")

        return {
            "success": True,
            "message": f"✅ Successfully deleted {video_count} videos from feed history",
            "videos_deleted": video_count
        }
    except Exception as e:
        logger.error(f"Error resetting feed history: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/reset/complete")
async def reset_complete_app():
    """
    Reset Complete App: Delete all data and reset settings.
    This includes channels, feed history, and resets all settings and prompts to defaults.
    """
    try:
        logger.info("Resetting complete application")

        # Get current counts before deletion
        channels, _ = config_manager.get_channels()
        channel_count = len(channels)

        # Delete all videos from database
        video_count = video_db.reset_all_data()

        # Clear channels from config
        config_manager.set_channels([])

        # Reset prompt to default
        config_manager.reset_prompt_to_default()

        # Reset all settings in config.txt to defaults
        config_manager.reset_all_settings()

        logger.info(f"Complete reset: Deleted {video_count} videos, {channel_count} channels, reset settings and prompt")

        return {
            "success": True,
            "message": f"✅ Successfully reset application: {video_count} videos deleted, {channel_count} channels deleted, settings and prompt reset to defaults",
            "videos_deleted": video_count,
            "channels_deleted": channel_count
        }
    except Exception as e:
        logger.error(f"Error resetting application: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# CHANNEL STATS & FEED API ENDPOINTS
# ============================================================================

@app.get("/api/stats/channels")
async def get_channel_stats():
    """Get statistics for all channels"""
    try:
        # Get all channel stats from database
        stats = video_db.get_all_channel_stats()

        # Get global stats
        global_stats = video_db.get_global_stats()

        logger.info(f"Retrieved stats for {len(stats)} channels")

        return {
            "channels": stats,
            "global": global_stats
        }

    except Exception as e:
        logger.error(f"Error getting channel stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/stats/channel/{channel_id}")
async def get_single_channel_stats(channel_id: str):
    """Get statistics for a specific channel"""
    try:
        stats = video_db.get_channel_stats(channel_id)

        logger.info(f"Retrieved stats for channel {channel_id}")

        return stats

    except Exception as e:
        logger.error(f"Error getting channel stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/videos/feed")
async def get_videos_feed(
    channel_id: Optional[str] = None,
    limit: int = 25,
    offset: int = 0,
    order_by: str = 'recent'
):
    """
    Get processed videos feed with pagination

    Parameters:
    - channel_id: Filter by channel (optional)
    - limit: Number of videos per page (default 25)
    - offset: Pagination offset (default 0)
    - order_by: Sort order - 'recent', 'oldest', 'channel' (default 'recent')
    """
    try:
        # Validate limit
        if limit < 1 or limit > 100:
            raise HTTPException(status_code=400, detail="Limit must be between 1 and 100")

        # Get videos
        videos = video_db.get_processed_videos(
            channel_id=channel_id,
            limit=limit,
            offset=offset,
            order_by=order_by
        )

        # Get total count for pagination
        total_count = video_db.get_total_count(channel_id=channel_id)

        logger.info(f"Retrieved {len(videos)} videos (offset {offset}, total {total_count})")

        return {
            "videos": videos,
            "total": total_count,
            "limit": limit,
            "offset": offset,
            "has_more": (offset + limit) < total_count
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting videos feed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/videos/{video_id}")
async def get_video_details(video_id: str):
    """Get full details for a single video including summary"""
    try:
        video = video_db.get_video_by_id(video_id)

        if not video:
            raise HTTPException(status_code=404, detail="Video not found")

        return video

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting video details: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/videos/{video_id}/retry")
async def retry_video_processing(video_id: str):
    """
    Retry processing for a failed video
    Resets status to 'pending' and triggers reprocessing
    """
    try:
        # Check if video exists
        video = video_db.get_video_by_id(video_id)
        if not video:
            raise HTTPException(status_code=404, detail="Video not found")

        # Reset video status to pending
        video_db.reset_video_status(video_id)
        logger.info(f"Reset video {video_id} to pending status")

        # Trigger immediate processing in background
        try:
            subprocess.Popen(['python3', 'process_videos.py'])
            logger.info("Started background processing for retry")
        except Exception as e:
            logger.error(f"Failed to start background processing: {e}")

        return {
            "status": "success",
            "message": "Video queued for reprocessing"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrying video {video_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/videos/process-now")
async def process_videos_now():
    """
    Manually trigger video processing for all channels
    Runs process_videos.py in background
    """
    try:
        # Run process_videos.py as subprocess (non-blocking)
        # Use sys.executable to ensure we use the same Python interpreter (venv)
        subprocess.Popen([sys.executable, 'process_videos.py'])
        logger.info("Manual processing triggered")

        return {
            "status": "success",
            "message": "Video processing started in background"
        }

    except Exception as e:
        logger.error(f"Error starting manual processing: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# EXPORT API ENDPOINTS
# ============================================================================

@app.get("/api/export/feed")
async def export_feed(format: str = "json"):
    """
    Export Feed level data (channels + videos).

    Parameters:
    - format: 'json' or 'csv' (default: 'json')

    Returns:
    - StreamingResponse with downloadable export file
    """
    try:
        if format not in ("json", "csv"):
            raise HTTPException(
                status_code=400,
                detail="Invalid format parameter. Must be 'json' or 'csv'"
            )

        if format == "json":
            # Export Feed as JSON
            data = export_manager.export_feed_json()
            filename = export_manager.generate_export_filename("feed_export", "json")

            # Convert to JSON string (pretty-printed)
            json_str = json.dumps(data, indent=2, ensure_ascii=False)

            # Return as downloadable file
            return StreamingResponse(
                io.BytesIO(json_str.encode('utf-8')),
                media_type="application/json",
                headers={
                    "Content-Disposition": f'attachment; filename="{filename}"'
                }
            )

        else:  # format == "csv"
            # Export videos as CSV
            csv_content = export_manager.export_videos_csv()
            filename = export_manager.generate_export_filename("videos", "csv")

            # Return as downloadable file
            return StreamingResponse(
                io.BytesIO(csv_content.encode('utf-8-sig')),
                media_type="text/csv",
                headers={
                    "Content-Disposition": f'attachment; filename="{filename}"'
                }
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Export feed failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Export failed: {str(e)}"
        )


@app.get("/api/export/backup")
async def export_backup():
    """
    Export Complete Backup (channels + videos + settings + AI prompt).

    Returns:
    - StreamingResponse with downloadable JSON backup file
    """
    try:
        # Export Complete Backup
        data = export_manager.export_complete_backup_json()
        filename = export_manager.generate_export_filename("full_backup", "json")

        # Convert to JSON string (pretty-printed)
        json_str = json.dumps(data, indent=2, ensure_ascii=False)

        # Return as downloadable file
        return StreamingResponse(
            io.BytesIO(json_str.encode('utf-8')),
            media_type="application/json",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"'
            }
        )

    except Exception as e:
        logger.error(f"Export backup failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Export failed: {str(e)}"
        )


# ============================================================================
# IMPORT API ENDPOINTS
# ============================================================================

@app.post("/api/import/validate")
async def validate_import(file: UploadFile = File(...)):
    """
    Validate import file and generate preview of changes.

    Parameters:
    - file: Uploaded JSON file

    Returns:
    - Validation result with preview
    """
    try:
        # Check file type
        if not file.filename.endswith('.json'):
            return JSONResponse(
                status_code=400,
                content={
                    "valid": False,
                    "errors": ["File must be a JSON file"],
                    "warnings": [],
                    "preview": None
                }
            )

        # Read file content
        content = await file.read()

        # Check file size (50 MB limit)
        if len(content) > import_manager.MAX_FILE_SIZE_BYTES:
            size_mb = len(content) / (1024 * 1024)
            return JSONResponse(
                status_code=413,
                content={
                    "valid": False,
                    "errors": [f"File too large ({size_mb:.1f} MB). Maximum size is 50 MB."],
                    "warnings": [],
                    "preview": None
                }
            )

        # Parse JSON
        try:
            data = json.loads(content.decode('utf-8'))
        except json.JSONDecodeError as e:
            return JSONResponse(
                status_code=200,
                content={
                    "valid": False,
                    "errors": [f"Invalid JSON syntax: {str(e)}"],
                    "warnings": [],
                    "preview": None
                }
            )

        # Validate file structure
        validation_result = import_manager.validate_import_file(data)

        if not validation_result.valid:
            return JSONResponse(
                status_code=200,
                content={
                    "valid": False,
                    "errors": validation_result.errors,
                    "warnings": validation_result.warnings,
                    "preview": None
                }
            )

        # Generate preview
        preview = import_manager.preview_import(data)

        return JSONResponse(
            status_code=200,
            content={
                "valid": True,
                "errors": [],
                "warnings": validation_result.warnings,
                "preview": {
                    "channels_new": preview.channels_new,
                    "channels_existing": preview.channels_existing,
                    "videos_new": preview.videos_new,
                    "videos_duplicate": preview.videos_duplicate,
                    "settings_changed": preview.settings_changed,
                    "settings_details": preview.settings_details,
                    "total_size_mb": preview.total_size_mb
                }
            }
        )

    except Exception as e:
        logger.error(f"Import validation failed: {e}")
        return JSONResponse(
            status_code=500,
            content={
                "valid": False,
                "errors": [f"Validation error: {str(e)}"],
                "warnings": [],
                "preview": None
            }
        )


@app.post("/api/import/execute")
async def execute_import(file: UploadFile = File(...)):
    """
    Execute import operation with rollback safety.

    Parameters:
    - file: Uploaded JSON file (must be validated first)

    Returns:
    - Import result with counts
    """
    try:
        # Check file type
        if not file.filename.endswith('.json'):
            raise HTTPException(
                status_code=400,
                detail="File must be a JSON file"
            )

        # Read file content
        content = await file.read()

        # Check file size
        if len(content) > import_manager.MAX_FILE_SIZE_BYTES:
            raise HTTPException(
                status_code=413,
                detail="File too large (max 50 MB)"
            )

        # Parse JSON
        try:
            data = json.loads(content.decode('utf-8'))
        except json.JSONDecodeError as e:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid JSON syntax: {str(e)}"
            )

        # Validate before import
        validation_result = import_manager.validate_import_file(data)
        if not validation_result.valid:
            raise HTTPException(
                status_code=400,
                detail=f"Validation failed: {'; '.join(validation_result.errors)}"
            )

        # Execute import
        import_result = import_manager.import_data(data)

        if not import_result.success:
            raise HTTPException(
                status_code=500,
                detail=f"Import failed: {'; '.join(import_result.errors)}"
            )

        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "message": f"Import successful: {import_result.channels_added} channels, {import_result.videos_added} videos, {import_result.settings_updated} settings",
                "channels_added": import_result.channels_added,
                "videos_added": import_result.videos_added,
                "settings_updated": import_result.settings_updated
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Import execution failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Import failed: {str(e)}"
        )


if __name__ == "__main__":
    import uvicorn
    logger.info("Starting YouTube Summarizer Web UI (Modern Minimalist)")
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
