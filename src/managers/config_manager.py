#!/usr/bin/env python3
"""
Shared Configuration Manager
Handles all config.txt reading/writing with file locking and validation
"""

import os
import re
import time
from typing import Dict, List, Tuple, Optional

from src.utils.file_lock import locked_file
from src.utils.validators import is_valid_channel_id


class ConfigManager:
    """Thread-safe configuration manager with file locking"""

    def __init__(self, config_path='config.txt', lock_timeout=10):
        self.config_path = config_path
        self.lock_timeout = lock_timeout

    def ensure_config_exists(self):
        """Create default config if it doesn't exist"""
        if os.path.exists(self.config_path):
            return

        default_content = """# YouTube Summarizer Configuration
# ================================

[PROMPT]
You are summarizing a YouTube video. Create a concise summary that:
1. Captures the main points in 2-3 paragraphs
2. Highlights what's valuable or interesting
3. Mentions any actionable takeaways
4. Indicates who would benefit from watching

Keep the tone conversational and focus on value.

Title: {title}
Duration: {duration}
Transcript: {transcript}

[CHANNELS]
# Add YouTube channel IDs below (one per line)
# Format: CHANNEL_ID or CHANNEL_ID|Channel Name
# Example: UCddiUEpeqJcYeBxX1IVBKvQ|The Verge
# To find channel ID: Go to channel page → View page source → Search for "channelId"

[SETTINGS]
# Maximum length of summary in tokens (affects cost)
SUMMARY_LENGTH=500

# Skip YouTube Shorts videos (true/false)
SKIP_SHORTS=true

# Maximum videos to check per channel
MAX_VIDEOS_PER_CHANNEL=5
"""
        try:
            os.makedirs(os.path.dirname(self.config_path) or '.', exist_ok=True)
            with open(self.config_path, 'w', encoding='utf-8') as f:
                f.write(default_content)
            print(f"✅ Created default config: {self.config_path}")
        except Exception as e:
            print(f"❌ Failed to create config: {e}")

    def read_config(self) -> Dict:
        """
        Read and parse config file with file locking
        Returns dict with channels, channel_names, prompt, and settings
        """
        self.ensure_config_exists()

        config = {
            'channels': [],
            'channel_names': {},
            'prompt': 'Summarize this video:\n\nTitle: {title}\nTranscript: {transcript}',
            'settings': {
                'SUMMARY_LENGTH': '500',
                'USE_SUMMARY_LENGTH': 'false',
                'SKIP_SHORTS': 'true',
                'MAX_VIDEOS_PER_CHANNEL': '5'
            }
        }

        try:
            with locked_file(self.config_path, timeout=self.lock_timeout):
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    config = self._parse_config(f.readlines())
        except TimeoutError as e:
            print(f"⚠️ {e}")
            print("   Using cached/default config")
        except Exception as e:
            print(f"⚠️ Error reading config: {e}")
            print("   Using default config")

        return config

    def _parse_config(self, lines: List[str]) -> Dict:
        """Parse config file lines into structured dict"""
        config = {
            'channels': [],
            'channel_names': {},
            'prompt': '',
            'settings': {
                'SUMMARY_LENGTH': '500',
                'USE_SUMMARY_LENGTH': 'false',
                'SKIP_SHORTS': 'true',
                'MAX_VIDEOS_PER_CHANNEL': '5'
            }
        }

        current_section = None
        prompt_lines = []

        for line in lines:
            line = line.rstrip('\n\r')  # Preserve internal whitespace
            stripped = line.strip()

            # Detect section headers
            if stripped == '[PROMPT]':
                current_section = 'PROMPT'
                prompt_lines = []
            elif stripped == '[CHANNELS]':
                current_section = 'CHANNELS'
                if prompt_lines:
                    config['prompt'] = '\n'.join(prompt_lines)
            elif stripped == '[SETTINGS]':
                current_section = 'SETTINGS'
                if prompt_lines:
                    config['prompt'] = '\n'.join(prompt_lines)
            elif stripped.startswith('['):
                current_section = None

            # Parse content based on section
            elif current_section == 'PROMPT':
                # Keep original line (without newline)
                prompt_lines.append(line)

            elif current_section == 'CHANNELS' and stripped and not stripped.startswith('#'):
                channel_id, channel_name = self._parse_channel_line(stripped)
                if channel_id:
                    config['channels'].append(channel_id)
                    config['channel_names'][channel_id] = channel_name

            elif current_section == 'SETTINGS' and '=' in stripped and not stripped.startswith('#'):
                key, value = stripped.split('=', 1)
                config['settings'][key.strip()] = value.strip()

        # Handle case where PROMPT is last section
        if current_section == 'PROMPT' and prompt_lines:
            config['prompt'] = '\n'.join(prompt_lines)

        return config

    def _parse_channel_line(self, line: str) -> Tuple[Optional[str], str]:
        """
        Parse channel line: 'CHANNEL_ID' or 'CHANNEL_ID|Channel Name'
        Returns (channel_id, channel_name)
        """
        if '|' in line:
            parts = line.split('|', 1)
            channel_id = parts[0].strip()
            channel_name = parts[1].strip() if len(parts) > 1 else channel_id
        else:
            channel_id = line.strip()
            channel_name = channel_id

        # Validate channel ID format
        if channel_id and self._is_valid_channel_id(channel_id):
            return channel_id, channel_name
        else:
            print(f"⚠️ Invalid channel ID: {channel_id}")
            return None, ""

    def _is_valid_channel_id(self, channel_id: str) -> bool:
        """Validate channel ID format (UC followed by 22 chars, or @handle)"""
        return is_valid_channel_id(channel_id)

    def write_config(self, channels: List[str], channel_names: Dict[str, str]) -> bool:
        """
        Write updated channel list to config with file locking
        Preserves PROMPT and SETTINGS sections
        Returns True on success, False on failure
        """
        self.ensure_config_exists()

        try:
            with locked_file(self.config_path, timeout=self.lock_timeout):
                # Read existing config
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    lines = f.readlines()

                # Find CHANNELS section boundaries
                channels_start = -1
                channels_end = len(lines)

                for i, line in enumerate(lines):
                    stripped = line.strip()
                    if stripped == '[CHANNELS]':
                        channels_start = i
                    elif channels_start >= 0 and stripped.startswith('['):
                        channels_end = i
                        break

                # Build new config
                new_lines = []

                # Part 1: Everything before CHANNELS section
                if channels_start >= 0:
                    new_lines.extend(lines[:channels_start + 1])
                else:
                    # No CHANNELS section found, add everything + new section
                    new_lines.extend(lines)
                    new_lines.append('\n[CHANNELS]\n')

                # Part 2: Updated channels
                for channel_id in channels:
                    # Validate before writing
                    if not self._is_valid_channel_id(channel_id):
                        print(f"⚠️ Skipping invalid channel ID: {channel_id}")
                        continue

                    channel_name = channel_names.get(channel_id, channel_id)
                    if channel_name and channel_name != channel_id:
                        new_lines.append(f"{channel_id}|{channel_name}\n")
                    else:
                        new_lines.append(f"{channel_id}\n")

                # Add blank line before next section
                if channels_end < len(lines):
                    new_lines.append('\n')

                # Part 3: Everything after CHANNELS section
                if channels_end < len(lines):
                    new_lines.extend(lines[channels_end:])

                # Write directly to config (we're already inside lock, so safe)
                # Note: Using direct write instead of temp+rename because Docker
                # bind mounts can cause "Device or resource busy" errors with os.replace()
                with open(self.config_path, 'w', encoding='utf-8') as f:
                    f.writelines(new_lines)
                    f.flush()
                    os.fsync(f.fileno())

                return True

        except TimeoutError as e:
            print(f"⚠️ {e}")
            return False
        except Exception as e:
            print(f"❌ Error writing config: {e}")
            return False

    def get_channels(self) -> Tuple[List[str], Dict[str, str]]:
        """Convenience method to get just channels and names"""
        config = self.read_config()
        return config['channels'], config['channel_names']

    def add_channel(self, channel_id: str, channel_name: str = None) -> bool:
        """Add a single channel to the config"""
        channels, names = self.get_channels()

        # Validate
        if not self._is_valid_channel_id(channel_id):
            print(f"❌ Invalid channel ID: {channel_id}")
            return False

        # Avoid duplicates
        if channel_id in channels:
            print(f"⚠️ Channel already exists: {channel_id}")
            return False

        channels.append(channel_id)
        names[channel_id] = channel_name or channel_id

        return self.write_config(channels, names)

    def remove_channel(self, channel_id: str) -> bool:
        """Remove a single channel from the config"""
        channels, names = self.get_channels()

        if channel_id not in channels:
            print(f"⚠️ Channel not found: {channel_id}")
            return False

        channels.remove(channel_id)
        names.pop(channel_id, None)

        return self.write_config(channels, names)

    def set_channels(self, channels: List[str], channel_names: Optional[Dict[str, str]] = None) -> bool:
        """Set channels list (replaces existing channels)"""
        names = channel_names or {}
        return self.write_config(channels, names)

    def get_prompt(self) -> str:
        """Get the current AI prompt template"""
        config = self.read_config()
        return config.get('prompt', '')

    def set_prompt(self, prompt: str) -> bool:
        """Update the AI prompt template"""
        try:
            with locked_file(self.config_path, timeout=self.lock_timeout):
                # Read existing config
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    lines = f.readlines()

                # Find PROMPT section boundaries
                prompt_start = -1
                prompt_end = len(lines)

                for i, line in enumerate(lines):
                    stripped = line.strip()
                    if stripped == '[PROMPT]':
                        prompt_start = i
                    elif prompt_start >= 0 and stripped.startswith('['):
                        prompt_end = i
                        break

                # Build new config
                new_lines = []

                # Part 1: Everything before PROMPT section
                if prompt_start >= 0:
                    new_lines.extend(lines[:prompt_start + 1])
                else:
                    new_lines.append('[PROMPT]\n')

                # Part 2: New prompt
                new_lines.append(prompt + '\n')
                new_lines.append('\n')

                # Part 3: Everything after PROMPT section
                if prompt_end < len(lines):
                    new_lines.extend(lines[prompt_end:])

                # Write directly (we're inside lock, safe from concurrent access)
                with open(self.config_path, 'w', encoding='utf-8') as f:
                    f.writelines(new_lines)
                    f.flush()
                    os.fsync(f.fileno())
                return True

        except Exception as e:
            print(f"❌ Error updating prompt: {e}")
            return False

    def reset_prompt_to_default(self) -> bool:
        """Reset the AI prompt template to default"""
        default_prompt = """You are summarizing a YouTube video. Create a concise summary that:
1. Captures the main points in 2-3 paragraphs
2. Highlights what's valuable or interesting
3. Mentions any actionable takeaways
4. Indicates who would benefit from watching

Keep the tone conversational and focus on value.

Title: {title}
Duration: {duration}
Transcript: {transcript}"""
        return self.set_prompt(default_prompt)

    def get_settings(self) -> Dict[str, str]:
        """Get all settings from config"""
        config = self.read_config()
        return config.get('settings', {})

    def set_setting(self, key: str, value: str) -> bool:
        """
        Update a single setting

        Args:
            key: Setting key to update
            value: New value
        """
        try:
            with locked_file(self.config_path, timeout=self.lock_timeout):
                # Read existing config
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    lines = f.readlines()

                # Find SETTINGS section
                settings_start = -1
                settings_end = len(lines)
                setting_found = False

                for i, line in enumerate(lines):
                    stripped = line.strip()
                    if stripped == '[SETTINGS]':
                        settings_start = i
                    elif settings_start >= 0 and stripped.startswith('['):
                        settings_end = i
                        break
                    elif settings_start >= 0 and stripped.startswith(f"{key}="):
                        # Update existing setting
                        lines[i] = f"{key}={value}\n"
                        setting_found = True

                # If setting not found, add it
                if not setting_found and settings_start >= 0:
                    lines.insert(settings_end, f"{key}={value}\n")

                # Write directly (we're inside lock, safe from concurrent access)
                with open(self.config_path, 'w', encoding='utf-8') as f:
                    f.writelines(lines)
                    f.flush()
                    os.fsync(f.fileno())
                return True

        except Exception as e:
            print(f"❌ Error updating setting: {e}")
            return False

    def reset_all_settings(self) -> bool:
        """Reset all settings to defaults"""
        default_settings = {
            'SUMMARY_LENGTH': '500',
            'USE_SUMMARY_LENGTH': 'false',
            'SKIP_SHORTS': 'true',
            'MAX_VIDEOS_PER_CHANNEL': '5'
        }

        try:
            with locked_file(self.config_path, timeout=self.lock_timeout):
                # Read existing config
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    lines = f.readlines()

                # Find SETTINGS section boundaries
                settings_start = -1
                settings_end = len(lines)

                for i, line in enumerate(lines):
                    stripped = line.strip()
                    if stripped == '[SETTINGS]':
                        settings_start = i
                    elif settings_start >= 0 and stripped.startswith('['):
                        settings_end = i
                        break

                # Build new config
                new_lines = []

                # Part 1: Everything before SETTINGS section
                if settings_start >= 0:
                    new_lines.extend(lines[:settings_start + 1])
                else:
                    new_lines.append('[SETTINGS]\n')

                # Part 2: Default settings with comments
                new_lines.append('# Maximum length of summary in tokens (affects cost)\n')
                new_lines.append(f"SUMMARY_LENGTH={default_settings['SUMMARY_LENGTH']}\n")
                new_lines.append('\n')
                new_lines.append('# Skip YouTube Shorts videos (true/false)\n')
                new_lines.append(f"SKIP_SHORTS={default_settings['SKIP_SHORTS']}\n")
                new_lines.append('\n')
                new_lines.append('# Maximum videos to check per channel\n')
                new_lines.append(f"MAX_VIDEOS_PER_CHANNEL={default_settings['MAX_VIDEOS_PER_CHANNEL']}\n")

                # Part 3: Everything after SETTINGS section (should be nothing)
                if settings_end < len(lines):
                    new_lines.append('\n')
                    new_lines.extend(lines[settings_end:])

                # Write directly (we're inside lock, safe from concurrent access)
                with open(self.config_path, 'w', encoding='utf-8') as f:
                    f.writelines(new_lines)
                    f.flush()
                    os.fsync(f.fileno())
                return True

        except Exception as e:
            print(f"❌ Error resetting settings: {e}")
            return False

    def get_value(self, section: str, key: str, default: any = None) -> any:
        """
        Get a specific value from config.

        Args:
            section: Section name (e.g., 'Settings', 'AI')
            key: Key name (e.g., 'SUMMARY_LENGTH', 'PROMPT_TEMPLATE')
            default: Default value if not found

        Returns:
            Value from config or default
        """
        config = self.read_config()

        if section == 'Settings':
            return config.get('settings', {}).get(key, default)
        elif section == 'AI':
            if key == 'PROMPT_TEMPLATE':
                return config.get('prompt', default)
        elif section == 'Channels':
            if key == 'CHANNELS':
                # Return channels as newline-separated string with names
                channels = config.get('channels', [])
                names = config.get('channel_names', {})
                lines = []
                for ch_id in channels:
                    ch_name = names.get(ch_id)
                    if ch_name and ch_name != ch_id:
                        lines.append(f"{ch_id}|{ch_name}")
                    else:
                        lines.append(ch_id)
                return '\n'.join(lines) if lines else default

        return default

    def export_channels(self) -> List[Dict]:
        """
        Export channels for backup/export purposes.

        Returns:
            List of channel dictionaries with channel_id and channel_name
        """
        channels, names = self.get_channels()

        return [
            {
                'channel_id': ch_id,
                'channel_name': names.get(ch_id) if names.get(ch_id) != ch_id else None,
                'added_date': None  # Not tracked currently
            }
            for ch_id in channels
        ]

    def import_channels(self, channels: List[Dict], merge: bool = True) -> int:
        """
        Import channels from backup.

        Args:
            channels: List of channel dicts with channel_id and optional channel_name
            merge: If True, add new channels and update names (preserve existing)
                   If False, replace all channels

        Returns:
            Number of channels added

        Raises:
            Exception: If write fails
        """
        existing_channels, existing_names = self.get_channels()

        if merge:
            # Merge: Add new channels, update names for existing
            added_count = 0

            for ch in channels:
                ch_id = ch.get('channel_id')
                ch_name = ch.get('channel_name')

                if not ch_id:
                    continue

                # Add if new
                if ch_id not in existing_channels:
                    existing_channels.append(ch_id)
                    added_count += 1

                # Update name (even if channel exists)
                if ch_name:
                    existing_names[ch_id] = ch_name

            success = self.write_config(existing_channels, existing_names)
            return added_count if success else 0

        else:
            # Replace: Clear all and set new channels
            new_channels = []
            new_names = {}

            for ch in channels:
                ch_id = ch.get('channel_id')
                ch_name = ch.get('channel_name')

                if ch_id:
                    new_channels.append(ch_id)
                    if ch_name:
                        new_names[ch_id] = ch_name

            success = self.write_config(new_channels, new_names)
            return len(new_channels) if success else 0

    def export_settings(self) -> Dict[str, any]:
        """
        Export non-secret settings for backup.

        Returns:
            Dictionary of settings (excludes credentials)
        """
        settings = self.get_settings()

        # Convert string booleans to actual booleans
        result = {}
        for key, value in settings.items():
            if value.lower() in ('true', 'false'):
                result[key] = value.lower() == 'true'
            elif value.isdigit():
                result[key] = int(value)
            else:
                result[key] = value

        return result

    def import_settings(self, settings: Dict[str, any]) -> int:
        """
        Import settings from backup (replaces existing settings).

        Args:
            settings: Dictionary of settings

        Returns:
            Number of settings updated

        Raises:
            Exception: If write fails
        """
        updated_count = 0

        for key, value in settings.items():
            # Convert to string for config file
            if isinstance(value, bool):
                value_str = 'true' if value else 'false'
            else:
                value_str = str(value)

            success = self.set_setting(key, value_str)
            if success:
                updated_count += 1

        return updated_count


class ProcessedVideos:
    """Manage processed videos list with rotation"""

    def __init__(self, file_path='data/processed.txt', max_entries=10000, keep_entries=5000):
        self.file_path = file_path
        self.max_entries = max_entries
        self.keep_entries = keep_entries
        self.lock_timeout = 10

        # Ensure data directory exists
        os.makedirs(os.path.dirname(file_path) or '.', exist_ok=True)

        # Load initial set
        self._processed = self._load()

    def _load(self) -> set:
        """Load processed video IDs from file"""
        if not os.path.exists(self.file_path):
            return set()

        try:
            with locked_file(self.file_path, timeout=self.lock_timeout):
                with open(self.file_path, 'r', encoding='utf-8') as f:
                    return set(line.strip() for line in f if line.strip())
        except Exception as e:
            print(f"⚠️ Error loading processed videos: {e}")
            return set()

    def is_processed(self, video_id: str) -> bool:
        """Check if video has been processed"""
        return video_id in self._processed

    def mark_processed(self, video_id: str):
        """Mark video as processed and append to file"""
        if video_id in self._processed:
            return  # Already processed

        self._processed.add(video_id)

        try:
            with locked_file(self.file_path, timeout=self.lock_timeout):
                # Append to file
                with open(self.file_path, 'a', encoding='utf-8') as f:
                    f.write(f"{video_id}\n")

                # Check if rotation needed
                if len(self._processed) >= self.max_entries:
                    self._rotate()
        except Exception as e:
            print(f"⚠️ Error marking video as processed: {e}")

    def _rotate(self):
        """Rotate processed file to prevent unbounded growth"""
        try:
            print(f"🔄 Rotating processed videos file (current: {len(self._processed)} entries)")

            # Keep only the most recent entries (last N lines)
            with open(self.file_path, 'r', encoding='utf-8') as f:
                all_lines = f.readlines()

            # Keep last N entries
            kept_lines = all_lines[-self.keep_entries:]

            # Write back
            with open(self.file_path, 'w', encoding='utf-8') as f:
                f.writelines(kept_lines)

            # Update in-memory set
            self._processed = set(line.strip() for line in kept_lines if line.strip())

            print(f"✅ Rotation complete (kept: {len(self._processed)} entries)")

        except Exception as e:
            print(f"❌ Error rotating processed file: {e}")

    def get_stats(self) -> Dict:
        """Get statistics about processed videos"""
        return {
            'total': len(self._processed),
            'max': self.max_entries,
            'will_rotate_at': self.max_entries
        }


# Utility functions for backward compatibility
def read_channels_from_config(config_path='config.txt') -> Tuple[List[str], Dict[str, str]]:
    """Backward compatible function to read channels"""
    manager = ConfigManager(config_path)
    return manager.get_channels()


def load_config(config_path='config.txt') -> Dict:
    """Backward compatible function to load full config"""
    manager = ConfigManager(config_path)
    return manager.read_config()


if __name__ == '__main__':
    # Test the config manager
    print("Testing ConfigManager...")

    manager = ConfigManager('test_config.txt')
    manager.ensure_config_exists()

    # Test reading
    config = manager.read_config()
    print(f"\nChannels: {config['channels']}")
    print(f"Settings: {config['settings']}")

    # Test adding channel
    print("\n Adding test channel...")
    manager.add_channel('UCddiUEpeqJcYeBxX1IVBKvQ', 'The Verge')

    # Test reading again
    channels, names = manager.get_channels()
    print(f"Updated channels: {channels}")
    print(f"Channel names: {names}")

    # Test ProcessedVideos
    print("\nTesting ProcessedVideos...")
    processed = ProcessedVideos('test_processed.txt', max_entries=5, keep_entries=3)

    for i in range(10):
        video_id = f"video_{i}"
        processed.mark_processed(video_id)
        print(f"Marked: {video_id}, Total: {processed.get_stats()['total']}")

    print(f"\nFinal stats: {processed.get_stats()}")
    print(f"Is video_0 still processed? {processed.is_processed('video_0')}")
    print(f"Is video_9 processed? {processed.is_processed('video_9')}")

    # Cleanup
    import os
    try:
        os.remove('test_config.txt')
        os.remove('test_config.txt.lock')
        os.remove('test_processed.txt')
        os.remove('test_processed.txt.lock')
    except:
        pass

    print("\n✅ Tests complete")
