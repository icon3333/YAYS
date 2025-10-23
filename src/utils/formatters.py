#!/usr/bin/env python3
"""
Formatting utilities for displaying data in human-readable formats
Extracted from database.py for reusability
"""
from datetime import datetime, timedelta
from typing import Optional


def format_duration(seconds: Optional[int]) -> str:
    """
    Format duration in seconds to HH:MM:SS or MM:SS

    Args:
        seconds: Duration in seconds

    Returns:
        Formatted duration string (e.g., "12:34" or "1:23:45")
    """
    if not seconds:
        return '0:00'

    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60

    if hours > 0:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    else:
        return f"{minutes}:{secs:02d}"


def format_views(views: Optional[int]) -> str:
    """
    Format view count to human-readable string

    Args:
        views: Number of views

    Returns:
        Formatted view count (e.g., "1.2K views" or "3.4M views")
    """
    if not views:
        return 'Unknown views'

    if views < 1000:
        return f"{views:,} views"
    elif views < 1_000_000:
        return f"{views/1000:.1f}K views"
    else:
        return f"{views/1_000_000:.1f}M views"


def format_upload_date(date_str: Optional[str]) -> str:
    """
    Format upload date (YYYY-MM-DD format) to human-readable relative time

    Args:
        date_str: Date string in YYYY-MM-DD or ISO format

    Returns:
        Relative time string (e.g., "Today", "2 days ago", "3 weeks ago")
    """
    if not date_str:
        return 'Unknown date'

    try:
        # Handle both YYYY-MM-DD and full ISO datetime formats
        if 'T' in date_str or ' ' in date_str:
            dt = datetime.fromisoformat(date_str.replace(' ', 'T'))
        else:
            # Parse YYYY-MM-DD format
            dt = datetime.strptime(date_str, '%Y-%m-%d')

        now = datetime.now()
        days_ago = (now.date() - dt.date()).days

        # If today
        if days_ago == 0:
            return "Today"

        # If yesterday
        elif days_ago == 1:
            return "Yesterday"

        # If within last week
        elif days_ago < 7:
            return f"{days_ago} days ago"

        # If within last month
        elif days_ago < 30:
            weeks = days_ago // 7
            return f"{weeks} week{'s' if weeks > 1 else ''} ago"

        # If within last year
        elif days_ago < 365:
            months = days_ago // 30
            return f"{months} month{'s' if months > 1 else ''} ago"

        # Otherwise show the date
        else:
            return dt.strftime('%b %d, %Y')

    except:
        return date_str


def format_processed_date(date_str: Optional[str]) -> str:
    """
    Format ISO date to human-readable format with time

    Args:
        date_str: ISO format date string

    Returns:
        Formatted date string (e.g., "Today at 14:30", "Yesterday at 09:15")
    """
    if not date_str:
        return 'Unknown'

    try:
        dt = datetime.fromisoformat(date_str)
        now = datetime.now()

        # If today
        if dt.date() == now.date():
            return f"Today at {dt.strftime('%H:%M')}"

        # If yesterday
        elif dt.date() == (now - timedelta(days=1)).date():
            return f"Yesterday at {dt.strftime('%H:%M')}"

        # If within last week
        elif (now - dt).days < 7:
            return dt.strftime('%A at %H:%M')

        # Otherwise
        else:
            return dt.strftime('%b %d, %Y')

    except:
        return date_str
