#!/usr/bin/env python3
"""
Settings Manager - Handles .env file operations with security
Manages environment variables, masking, validation, and testing
"""

import os
import re
import shutil
from typing import Dict, Optional, Tuple, Any
from contextlib import contextmanager
from datetime import datetime

# Use filelock for cross-platform file locking
try:
    from filelock import FileLock, Timeout
except ImportError:
    print("Warning: filelock not installed. File locking disabled.")
    class FileLock:
        def __init__(self, *args, **kwargs):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
    class Timeout(Exception):
        pass


class SettingsManager:
    """Secure settings manager for .env file operations"""

    def __init__(self, env_path='.env', lock_timeout=10):
        self.env_path = env_path
        self.lock_path = f"{env_path}.lock"
        self.backup_path = f"{env_path}.backup"
        self.lock_timeout = lock_timeout

        # Define all expected environment variables with their properties
        self.env_schema = {
            # Sensitive credentials (will be masked)
            'OPENAI_API_KEY': {
                'type': 'secret',
                'required': True,
                'pattern': r'^sk-[A-Za-z0-9_-]{20,}$',
                'description': 'OpenAI API Key (for ChatGPT)'
            },
            'INOREADER_EMAIL': {
                'type': 'email',
                'required': True,
                'pattern': r'^[\w\.\-+]+@[\w\.\-]+\.\w+$',
                'description': 'Email-to-tag address for receiving summaries'
            },
            'SMTP_USER': {
                'type': 'email',
                'required': True,
                'pattern': r'^[\w\.\-+]+@[\w\.\-]+\.\w+$',
                'description': 'Gmail SMTP username'
            },
            'SMTP_PASS': {
                'type': 'secret',
                'required': True,
                'min_length': 16,
                'max_length': 16,
                'description': 'Gmail app password (16 chars)'
            },
            # Application settings (safe to show)
            'LOG_LEVEL': {
                'type': 'enum',
                'required': False,
                'default': 'INFO',
                'options': ['DEBUG', 'INFO', 'WARNING', 'ERROR'],
                'description': 'Logging verbosity level'
            },
            'CHECK_INTERVAL_HOURS': {
                'type': 'integer',
                'required': False,
                'default': '4',
                'min': 1,
                'max': 24,
                'description': 'How often to check for new videos (hours)'
            },
            'MAX_PROCESSED_ENTRIES': {
                'type': 'integer',
                'required': False,
                'default': '10000',
                'min': 100,
                'max': 100000,
                'description': 'Max video IDs to track before rotation'
            },
            'SEND_EMAIL_TO_INOREADER': {
                'type': 'enum',
                'required': False,
                'default': 'true',
                'options': ['true', 'false'],
                'description': 'Send summaries via email to Inoreader'
            },
            'OPENAI_MODEL': {
                'type': 'text',
                'required': False,
                'default': 'gpt-4o-mini',
                'description': 'OpenAI model to use for summaries'
            }
        }

    @contextmanager
    def _lock(self):
        """Context manager for file locking"""
        lock = FileLock(self.lock_path, timeout=self.lock_timeout)
        try:
            with lock:
                yield
        except Timeout:
            raise TimeoutError(f"Could not acquire lock on {self.env_path}")

    def _mask_secret(self, value: str, secret_type: str = 'secret') -> str:
        """
        Mask sensitive values for display

        For API keys: Show first 7 and last 3 chars
        For passwords: Show all dots
        """
        if not value:
            return ''

        if secret_type == 'secret':
            if value.startswith('sk-'):
                # OpenAI/API key: sk-***...***xxx
                if len(value) > 15:
                    return f"{value[:7]}***...***{value[-4:]}"
                return 'sk-***'
            else:
                # Generic password: all dots
                return '•' * min(len(value), 16)

        return value

    def _parse_env_file(self) -> Dict[str, str]:
        """Parse .env file into key-value dict"""
        if not os.path.exists(self.env_path):
            return {}

        env_vars = {}

        try:
            with open(self.env_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()

                    # Skip empty lines and comments
                    if not line or line.startswith('#'):
                        continue

                    # Parse KEY=VALUE
                    if '=' in line:
                        key, value = line.split('=', 1)
                        key = key.strip()
                        value = value.strip()

                        # Remove quotes if present
                        if value.startswith('"') and value.endswith('"'):
                            value = value[1:-1]
                        elif value.startswith("'") and value.endswith("'"):
                            value = value[1:-1]

                        env_vars[key] = value

        except Exception as e:
            print(f"⚠️ Error parsing .env file: {e}")
            return {}

        return env_vars

    def get_all_settings(self, mask_secrets=True) -> Dict[str, Any]:
        """
        Get all settings from .env with optional masking
        Returns dict with structure: { key: { value, masked, type, description, ... } }
        """
        settings = {}

        try:
            with self._lock():
                env_vars = self._parse_env_file()

            # Process each defined setting
            for key, schema in self.env_schema.items():
                value = env_vars.get(key, schema.get('default', ''))

                setting_info = {
                    'value': value,
                    'type': schema['type'],
                    'description': schema.get('description', ''),
                    'required': schema.get('required', False)
                }

                # Add type-specific metadata
                if schema['type'] == 'enum':
                    setting_info['options'] = schema.get('options', [])
                    setting_info['default'] = schema.get('default', '')

                elif schema['type'] == 'integer':
                    setting_info['min'] = schema.get('min')
                    setting_info['max'] = schema.get('max')
                    setting_info['default'] = schema.get('default', '')

                # Mask secrets if requested
                if mask_secrets and schema['type'] == 'secret':
                    setting_info['masked'] = self._mask_secret(value)
                    setting_info['value'] = ''  # Don't send actual value to client
                else:
                    setting_info['masked'] = value

                settings[key] = setting_info

        except Exception as e:
            print(f"⚠️ Error reading settings: {e}")
            # Return schema defaults
            for key, schema in self.env_schema.items():
                settings[key] = {
                    'value': '',
                    'masked': '',
                    'type': schema['type'],
                    'description': schema.get('description', ''),
                    'required': schema.get('required', False)
                }

        return settings

    def validate_setting(self, key: str, value: str) -> Tuple[bool, str]:
        """
        Validate a single setting value
        Returns (is_valid, error_message)
        """
        if key not in self.env_schema:
            return False, f"Unknown setting: {key}"

        schema = self.env_schema[key]

        # Check required
        if schema.get('required', False) and not value:
            return False, f"{key} is required"

        # Type-specific validation
        if schema['type'] == 'secret':
            # Check pattern if defined
            if 'pattern' in schema:
                if not re.match(schema['pattern'], value):
                    return False, f"Invalid format for {key}"

            # Check length constraints
            if 'min_length' in schema:
                # Remove spaces for Gmail app passwords
                clean_value = value.replace(' ', '')
                if len(clean_value) < schema['min_length']:
                    return False, f"{key} must be at least {schema['min_length']} characters"

            if 'max_length' in schema:
                clean_value = value.replace(' ', '')
                if len(clean_value) > schema['max_length']:
                    return False, f"{key} must be at most {schema['max_length']} characters"

        elif schema['type'] == 'email':
            if value and 'pattern' in schema:
                if not re.match(schema['pattern'], value):
                    return False, f"Invalid email format for {key}"

        elif schema['type'] == 'enum':
            if value and value not in schema.get('options', []):
                return False, f"{key} must be one of: {', '.join(schema['options'])}"

        elif schema['type'] == 'integer':
            try:
                int_value = int(value)
                if 'min' in schema and int_value < schema['min']:
                    return False, f"{key} must be at least {schema['min']}"
                if 'max' in schema and int_value > schema['max']:
                    return False, f"{key} must be at most {schema['max']}"
            except ValueError:
                return False, f"{key} must be a valid integer"

        return True, ''

    def update_setting(self, key: str, value: str) -> Tuple[bool, str]:
        """
        Update a single setting in .env file
        Returns (success, message)
        """
        # Validate first
        is_valid, error_msg = self.validate_setting(key, value)
        if not is_valid:
            return False, error_msg

        # Clean value (remove spaces from passwords)
        if key == 'SMTP_PASS':
            value = value.replace(' ', '')

        try:
            with self._lock():
                # Create backup
                if os.path.exists(self.env_path):
                    shutil.copy2(self.env_path, self.backup_path)

                # Read existing .env
                env_vars = self._parse_env_file()

                # Update value
                env_vars[key] = value

                # Write back to .env
                self._write_env_file(env_vars)

                return True, f"Updated {key} successfully"

        except Exception as e:
            # Try to restore from backup
            if os.path.exists(self.backup_path):
                try:
                    shutil.copy2(self.backup_path, self.env_path)
                    print("✅ Restored .env from backup")
                except:
                    pass

            return False, f"Failed to update {key}: {str(e)}"

    def update_multiple_settings(self, settings: Dict[str, str]) -> Tuple[bool, str, list]:
        """
        Update multiple settings at once (more efficient)
        Returns (success, message, list of errors)
        """
        errors = []

        # Validate all first
        for key, value in settings.items():
            is_valid, error_msg = self.validate_setting(key, value)
            if not is_valid:
                errors.append(error_msg)

        if errors:
            return False, "Validation failed", errors

        try:
            with self._lock():
                # Create backup
                if os.path.exists(self.env_path):
                    shutil.copy2(self.env_path, self.backup_path)

                # Read existing .env
                env_vars = self._parse_env_file()

                # Update all values
                for key, value in settings.items():
                    # Clean value if needed
                    if key == 'SMTP_PASS':
                        value = value.replace(' ', '')
                    env_vars[key] = value

                # Write back
                self._write_env_file(env_vars)

                return True, f"Updated {len(settings)} settings successfully", []

        except Exception as e:
            # Try to restore from backup
            if os.path.exists(self.backup_path):
                try:
                    shutil.copy2(self.backup_path, self.env_path)
                    print("✅ Restored .env from backup")
                except:
                    pass

            return False, f"Failed to update settings: {str(e)}", []

    def _write_env_file(self, env_vars: Dict[str, str]):
        """Write environment variables to .env file with comments preserved"""
        # Read original file to preserve comments and structure
        original_lines = []
        if os.path.exists(self.env_path):
            with open(self.env_path, 'r', encoding='utf-8') as f:
                original_lines = f.readlines()

        # Track which keys we've written
        written_keys = set()
        new_lines = []

        # Process original file, replacing values where found
        for line in original_lines:
            stripped = line.strip()

            # Keep comments and empty lines
            if not stripped or stripped.startswith('#'):
                new_lines.append(line)
                continue

            # Parse key=value lines
            if '=' in stripped:
                key = stripped.split('=', 1)[0].strip()

                if key in env_vars:
                    # Replace with new value
                    new_lines.append(f"{key}={env_vars[key]}\n")
                    written_keys.add(key)
                else:
                    # Keep original line
                    new_lines.append(line)
            else:
                new_lines.append(line)

        # Add any new keys that weren't in the original file
        for key, value in env_vars.items():
            if key not in written_keys:
                new_lines.append(f"\n# Added by Settings Manager - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                new_lines.append(f"{key}={value}\n")

        # Write atomically (temp file + rename)
        temp_path = f"{self.env_path}.tmp"
        with open(temp_path, 'w', encoding='utf-8') as f:
            f.writelines(new_lines)

        os.replace(temp_path, self.env_path)

    def check_restart_required(self) -> bool:
        """
        Check if restart is required for changes to take effect
        .env changes always require restart
        """
        return True  # All .env changes require restart

    def create_env_from_example(self) -> bool:
        """Create .env from .env.example if .env doesn't exist"""
        if os.path.exists(self.env_path):
            return False  # Already exists

        example_path = '.env.example'
        if not os.path.exists(example_path):
            return False  # No example to copy from

        try:
            shutil.copy2(example_path, self.env_path)
            print(f"✅ Created {self.env_path} from {example_path}")
            return True
        except Exception as e:
            print(f"❌ Failed to create .env from example: {e}")
            return False


# Test functions for credentials
def test_openai_key(api_key: str) -> Tuple[bool, str]:
    """
    Test OpenAI API key by making a simple API call
    Returns (success, message)
    """
    try:
        from openai import OpenAI

        client = OpenAI(api_key=api_key)

        # Make a minimal API call to test the key
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            max_tokens=5,
            messages=[{"role": "user", "content": "Hi"}]
        )

        return True, "✅ OpenAI API key is valid"

    except Exception as e:
        error_msg = str(e)
        if "invalid" in error_msg.lower() or "authentication" in error_msg.lower() or "api_key" in error_msg.lower():
            return False, "❌ Invalid API key"
        elif "rate" in error_msg.lower() or "quota" in error_msg.lower():
            return False, "⚠️ Rate limited or quota exceeded (but key appears valid)"
        else:
            return False, f"❌ API test failed: {error_msg[:100]}"


def test_smtp_credentials(smtp_user: str, smtp_pass: str) -> Tuple[bool, str]:
    """
    Test SMTP credentials by attempting connection
    Returns (success, message)
    """
    try:
        import smtplib

        # Attempt to connect and authenticate
        server = smtplib.SMTP('smtp.gmail.com', 587, timeout=10)
        server.starttls()
        server.login(smtp_user, smtp_pass)
        server.quit()

        return True, "✅ SMTP credentials are valid"

    except smtplib.SMTPAuthenticationError:
        return False, "❌ Invalid email or password"

    except smtplib.SMTPException as e:
        return False, f"❌ SMTP error: {str(e)[:100]}"

    except Exception as e:
        return False, f"❌ Connection failed: {str(e)[:100]}"


if __name__ == '__main__':
    # Test the settings manager
    print("Testing SettingsManager...")

    manager = SettingsManager('.env.test')

    # Test getting settings
    print("\n1. Getting all settings (masked):")
    settings = manager.get_all_settings(mask_secrets=True)
    for key, info in settings.items():
        print(f"   {key}: {info['masked']} ({info['type']})")

    # Test validation
    print("\n2. Testing validation:")
    test_cases = [
        ('LOG_LEVEL', 'INFO', True),
        ('LOG_LEVEL', 'INVALID', False),
        ('CHECK_INTERVAL_HOURS', '4', True),
        ('CHECK_INTERVAL_HOURS', '0', False),
        ('CHECK_INTERVAL_HOURS', '25', False),
        ('ANTHROPIC_API_KEY', 'sk-ant-api03-' + 'x' * 95, True),
        ('ANTHROPIC_API_KEY', 'invalid', False),
    ]

    for key, value, expected_valid in test_cases:
        is_valid, msg = manager.validate_setting(key, value)
        status = "✅" if is_valid == expected_valid else "❌"
        print(f"   {status} {key}={value}: {msg if not is_valid else 'Valid'}")

    # Cleanup
    try:
        os.remove('.env.test')
        os.remove('.env.test.lock')
    except:
        pass

    print("\n✅ Tests complete")
