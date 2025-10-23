#!/usr/bin/env python3
"""
Simple validation functions for common data types
Centralizes validation logic to avoid duplication
"""
import re


def is_valid_email(email: str) -> bool:
    """
    Check if email format is valid

    Args:
        email: Email address to validate

    Returns:
        True if valid email format, False otherwise
    """
    if not email:
        return False
    return bool(re.match(r'^[\w\.\-+]+@[\w\.\-]+\.\w+$', email))


def is_valid_channel_id(channel_id: str) -> bool:
    """
    Check if YouTube channel ID is valid

    Supports:
    - Standard format: UC followed by 22 characters (UC...)
    - Handle format: @username
    - Custom URL format: alphanumeric string

    Args:
        channel_id: YouTube channel identifier

    Returns:
        True if valid channel ID format, False otherwise
    """
    if not channel_id:
        return False

    # Standard channel ID: UC + 22 alphanumeric/dash/underscore
    if re.match(r'^UC[\w-]{22}$', channel_id):
        return True

    # Handle format: @username
    if re.match(r'^@[\w-]+$', channel_id):
        return True

    # Custom URL format
    if re.match(r'^[\w-]+$', channel_id) and len(channel_id) > 3:
        return True

    return False


def is_valid_openai_key(api_key: str) -> bool:
    """
    Check if OpenAI API key format is valid

    Args:
        api_key: API key to validate

    Returns:
        True if valid format (starts with sk-), False otherwise
    """
    if not api_key:
        return False
    return bool(re.match(r'^sk-[A-Za-z0-9_-]{20,}$', api_key))
