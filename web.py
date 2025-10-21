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
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse, StreamingResponse
from pydantic import BaseModel, field_validator
from typing import Dict, List, Optional
import re
import feedparser
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Import shared managers
from src.managers.config_manager import ConfigManager
from src.managers.settings_manager import SettingsManager, test_openai_key, test_smtp_credentials
from src.managers.database import VideoDatabase
from src.managers.restart_manager import detect_runtime_environment, restart_application

# Import export/import managers
from src.managers.export_manager import ExportManager
from src.managers.import_manager import ImportManager

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger('web')

app = FastAPI(
    title="YAYS - Yet Another Youtube Summarizer",
    version="2.0.0",
    description="Modern minimalist design"
)

# Initialize config manager
config_manager = ConfigManager('config.txt')
settings_manager = SettingsManager('.env')
video_db = VideoDatabase('data/videos.db')

# Initialize export/import managers
export_manager = ExportManager(
    db_path='data/videos.db',
    config_path='config.txt',
    env_path='.env'
)
import_manager = ImportManager(
    db_path='data/videos.db',
    config_path='config.txt',
    env_path='.env'
)


# Helper function to extract channel ID from various YouTube URL formats
def extract_channel_id_from_url(input_str: str) -> str:
    """
    Extract channel ID from various YouTube URL formats:
    - https://www.youtube.com/@handle
    - https://www.youtube.com/channel/UCxxxx
    - @handle
    - UCxxxx (already a channel ID)

    Returns the channel ID (UCxxxx format)
    """
    import urllib.request

    input_str = input_str.strip()

    # Already a valid channel ID (UC + 22 chars)
    if re.match(r'^UC[\w-]{22}$', input_str):
        return input_str

    # Extract handle from @handle or URL with @handle
    handle_match = re.search(r'@([\w-]+)', input_str)
    if handle_match:
        handle = handle_match.group(1)
        # Fetch the page and extract channel ID
        try:
            url = f"https://www.youtube.com/@{handle}"
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=10) as response:
                html = response.read().decode('utf-8')
                # Extract channel ID from HTML
                channel_id_match = re.search(r'"channelId":"(UC[\w-]{22})"', html)
                if channel_id_match:
                    return channel_id_match.group(1)
        except Exception as e:
            logger.error(f"Error fetching channel ID for @{handle}: {e}")
            raise ValueError(f"Could not extract channel ID from @{handle}")

    # Extract from /channel/UCxxxx URL
    channel_match = re.search(r'/channel/(UC[\w-]{22})', input_str)
    if channel_match:
        return channel_match.group(1)

    # If nothing matched, raise error
    raise ValueError(f"Invalid YouTube channel format: {input_str}")


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
async def home():
    """Serve modern minimalist three-tab design with settings"""
    return r"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no">
    <meta name="apple-mobile-web-app-capable" content="yes">
    <title>YAYS - Yet Another Youtube Summarizer</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Newsreader:ital,opsz,wght@0,6..72,300;0,6..72,400;0,6..72,600;0,6..72,700;1,6..72,400&family=JetBrains+Mono:wght@300;400;500;600&display=swap" rel="stylesheet">
    <style>
        * {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }

        :root {
            /* Monochrome palette */
            --black: #000000;
            --grey-900: #1a1a1a;
            --grey-800: #262626;
            --grey-700: #404040;
            --grey-500: #737373;
            --grey-300: #d4d4d4;
            --grey-200: #e5e5e5;
            --grey-100: #f5f5f5;
            --white: #ffffff;

            /* Spacing (8px system) */
            --space-1: 8px;
            --space-2: 16px;
            --space-3: 24px;
            --space-4: 32px;
            --space-5: 40px;
            --space-6: 48px;
            --space-8: 64px;

            /* Typography - Technical Editorial Style */
            --font-primary: 'Newsreader', Georgia, serif;
            --font-mono: 'JetBrains Mono', 'SF Mono', monospace;
            --font-system: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
        }

        body {
            font-family: var(--font-mono);
            background: var(--white);
            color: var(--black);
            line-height: 1.5;
            -webkit-font-smoothing: antialiased;
            min-height: 100vh;
        }

        /* Header */
        header {
            background: var(--black);
            color: var(--white);
            padding: var(--space-3) var(--space-4);
            border-bottom: 1px solid var(--black);
        }

        h1 {
            font-family: var(--font-mono);
            font-size: 18px;
            font-weight: 600;
            letter-spacing: 0.02em;
        }

        /* Main Layout - Two Columns */
        .container {
            display: grid;
            grid-template-columns: 400px 1fr;
            min-height: calc(100vh - 65px);
        }

        /* Left Column - Add Channel */
        .left-column {
            background: var(--grey-100);
            padding: var(--space-4);
            border-right: 1px solid var(--grey-200);
        }

        /* Right Column - Channel List */
        .right-column {
            background: var(--white);
            padding: var(--space-4);
            overflow-y: auto;
        }

        /* Section titles - JetBrains Mono for technical precision */
        h2 {
            font-family: var(--font-mono);
            font-size: 12px;
            font-weight: 300;
            letter-spacing: 0.05em;
            text-transform: uppercase;
            color: var(--grey-500);
            margin-bottom: var(--space-3);
        }

        /* Status message - JetBrains Mono for technical feedback */
        .status {
            font-family: var(--font-mono);
            font-weight: 500;
            background: var(--black);
            color: var(--white);
            padding: var(--space-2);
            margin-bottom: var(--space-3);
            font-size: 14px;
            text-align: center;
            opacity: 0;
            transition: opacity 0.2s;
        }

        .status.show {
            opacity: 1;
        }

        .status.error {
            background: var(--grey-900);
        }

        /* Restart notification box */
        .restart-notification {
            font-family: var(--font-mono);
            font-weight: 500;
            background: #fff3cd;
            color: #856404;
            border: 1px solid #ffc107;
            padding: var(--space-3);
            margin-bottom: var(--space-3);
            font-size: 14px;
            text-align: center;
            border-radius: 4px;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: var(--space-3);
        }

        .btn-restart-inline {
            font-family: var(--font-mono);
            font-size: 13px;
            font-weight: 600;
            padding: var(--space-2) var(--space-3);
            background: var(--black);
            color: var(--white);
            border: 1px solid var(--black);
            cursor: pointer;
            transition: all 0.2s;
            border-radius: 4px;
        }

        .btn-restart-inline:hover {
            background: var(--grey-900);
            border-color: var(--grey-900);
        }

        /* Form styling */
        .form-group {
            margin-bottom: var(--space-3);
        }

        label {
            display: block;
            font-family: var(--font-mono);
            font-size: 13px;
            font-weight: 600;
            letter-spacing: 0.01em;
            text-transform: uppercase;
            color: #666;
            margin-bottom: var(--space-1);
        }

        input[type="text"] {
            width: 100%;
            padding: var(--space-2);
            background: var(--white);
            border: 1px solid var(--grey-300);
            font-family: var(--font-mono);
            font-size: 14px;
            font-weight: 400;
            color: var(--black);
            transition: all 0.2s;
        }

        input[type="text"]:focus {
            outline: none;
            border-color: var(--black);
        }

        input[type="text"]::placeholder {
            color: var(--grey-500);
        }

        /* Button - JetBrains Mono for technical actions */
        button {
            width: 100%;
            padding: var(--space-2);
            background: var(--black);
            border: 1px solid var(--black);
            color: var(--white);
            font-family: var(--font-mono);
            font-size: 15px;
            font-weight: 500;
            letter-spacing: 0.02em;
            cursor: pointer;
            transition: all 0.2s;
        }

        button:hover {
            background: var(--grey-900);
        }

        button:active {
            transform: scale(0.98);
        }

        button:disabled {
            opacity: 0.5;
            cursor: not-allowed;
        }

        /* Channel list */
        .channels {
            display: grid;
            gap: var(--space-1);
        }

        .channel {
            display: grid;
            grid-template-columns: 1fr auto;
            gap: var(--space-2);
            padding: var(--space-2);
            background: var(--white);
            border: 1px solid var(--grey-200);
            align-items: center;
            transition: all 0.2s;
        }

        .channel:hover {
            background: var(--grey-100);
            border-color: var(--grey-300);
        }

        .channel-info {
            min-width: 0;
        }

        .channel-name {
            font-family: var(--font-mono);
            font-size: 15px;
            font-weight: 600;
            color: #1a1a1a;
            margin-bottom: 4px;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }

        .channel-id {
            font-family: var(--font-mono);
            font-size: 11px;
            font-weight: 400;
            letter-spacing: 0.02em;
            color: #6c757d;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }

        /* Remove button */
        .btn-remove {
            width: auto;
            padding: 6px 12px;
            background: transparent;
            border: 1px solid var(--grey-300);
            color: var(--grey-700);
            font-family: var(--font-mono);
            font-size: 12px;
            font-weight: 500;
            transition: all 0.2s;
        }

        .btn-remove:hover {
            background: var(--black);
            border-color: var(--black);
            color: var(--white);
        }

        /* Empty state */
        .empty {
            text-align: center;
            padding: var(--space-8) var(--space-2);
            color: var(--grey-500);
        }

        .empty-icon {
            width: 48px;
            height: 48px;
            margin: 0 auto var(--space-2);
            border: 2px solid var(--grey-300);
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 24px;
        }

        .empty-text {
            font-size: 14px;
        }

        /* Stats footer - JetBrains Mono */
        .stats {
            position: fixed;
            bottom: 0;
            right: 0;
            padding: var(--space-2) var(--space-3);
            background: var(--grey-100);
            border-top: 1px solid var(--grey-200);
            border-left: 1px solid var(--grey-200);
            font-family: var(--font-mono);
            font-size: 13px;
            font-weight: 400;
            letter-spacing: 0.03em;
            color: var(--grey-500);
        }

        /* Modal */
        .modal {
            display: none;
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(0, 0, 0, 0.8);
            align-items: center;
            justify-content: center;
            z-index: 1000;
        }

        .modal.show {
            display: flex;
        }

        .modal-content {
            background: var(--white);
            border: 1px solid var(--black);
            max-width: 400px;
            width: 90%;
            padding: var(--space-4);
        }

        .modal-title {
            font-family: var(--font-mono);
            font-size: 16px;
            font-weight: 600;
            margin-bottom: var(--space-2);
            color: var(--black);
        }

        .modal-message {
            font-family: var(--font-mono);
            margin-bottom: var(--space-3);
            color: var(--grey-700);
            font-size: 14px;
            line-height: 1.6;
        }

        .modal-buttons {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: var(--space-1);
        }

        .modal-btn {
            padding: var(--space-2);
            border: 1px solid var(--grey-300);
            font-family: var(--font-mono);
            font-size: 13px;
            font-weight: 500;
            cursor: pointer;
            transition: all 0.2s;
        }

        .modal-btn-cancel {
            background: var(--white);
            color: var(--black);
        }

        .modal-btn-cancel:hover {
            background: var(--grey-100);
        }

        .modal-btn-confirm {
            background: var(--black);
            color: var(--white);
            border-color: var(--black);
        }

        .modal-btn-confirm:hover {
            background: var(--grey-900);
        }

        /* Loading */
        .loading {
            text-align: center;
            padding: var(--space-6) 0;
            font-size: 14px;
            color: var(--grey-500);
        }

        /* Responsive */
        @media (max-width: 900px) {
            .container {
                grid-template-columns: 1fr;
            }

            .left-column {
                border-right: none;
                border-bottom: 1px solid var(--grey-200);
            }

            .stats {
                position: static;
                border-left: none;
            }
        }

        /* Mobile font optimizations */
        @media (max-width: 380px) {
            h1 {
                font-size: 16px;
            }

            .channel-name {
                font-size: 14px;
            }

            button {
                font-size: 14px;
            }
        }

        /* ========================================
           NEW STYLES FOR TABS AND SETTINGS
           ======================================== */

        /* Tab navigation */
        .tabs {
            display: flex;
            gap: var(--space-1);
            margin-top: var(--space-2);
        }

        .tab-btn {
            padding: 8px 16px;
            background: transparent;
            border: 1px solid var(--grey-700);
            color: var(--grey-300);
            font-size: 13px;
            font-weight: 500;
            cursor: pointer;
            transition: all 0.2s;
            width: auto;
        }

        .tab-btn:hover {
            background: var(--grey-900);
            color: var(--white);
            border-color: var(--grey-500);
        }

        .tab-btn.active {
            background: var(--white);
            color: var(--black);
            border-color: var(--white);
        }

        /* Tab content containers */
        .tab-content {
            display: none;
        }

        .tab-content.active {
            display: block;
        }

        /* Restart warning banner */
        .restart-banner {
            background: var(--grey-900);
            color: var(--white);
            padding: var(--space-2);
            border-bottom: 2px solid var(--grey-700);
        }

        .restart-content {
            display: flex;
            align-items: center;
            gap: var(--space-2);
            max-width: 1200px;
            margin: 0 auto;
            font-family: var(--font-mono);
            font-size: 13px;
        }

        .restart-icon {
            font-size: 20px;
        }

        .restart-text code {
            background: var(--black);
            padding: 2px 8px;
            border-radius: 3px;
            font-family: var(--font-mono);
            font-size: 12px;
        }

        .restart-btn {
            background: var(--white);
            color: var(--black);
            border: none;
            padding: 8px 16px;
            border-radius: 4px;
            font-family: var(--font-mono);
            font-size: 13px;
            font-weight: 500;
            cursor: pointer;
            transition: all 0.2s ease;
            white-space: nowrap;
        }

        .restart-btn:hover:not(:disabled) {
            background: var(--grey-200);
            transform: translateY(-1px);
        }

        .restart-btn:active:not(:disabled) {
            transform: translateY(0);
        }

        .restart-btn:disabled {
            cursor: not-allowed;
            opacity: 0.6;
        }

        .restart-close {
            margin-left: auto;
            background: transparent;
            border: none;
            color: var(--white);
            font-size: 24px;
            cursor: pointer;
            padding: 0;
            width: auto;
            line-height: 1;
        }

        .restart-close:hover {
            color: var(--grey-300);
        }

        /* Settings page layout */
        .settings-container {
            max-width: 800px;
            margin: 0 auto;
            padding: var(--space-4);
        }

        .settings-section {
            background: var(--white);
            border: 1px solid var(--grey-200);
            padding: var(--space-4);
            margin-bottom: var(--space-3);
        }

        .settings-section h3 {
            font-family: var(--font-mono);
            font-size: 14px;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            margin-bottom: var(--space-3);
            padding-bottom: var(--space-2);
            border-bottom: 1px solid var(--grey-200);
        }

        .setting-row {
            margin-bottom: var(--space-3);
        }

        .setting-row:last-child {
            margin-bottom: 0;
        }

        .setting-label {
            display: block;
            font-family: var(--font-mono);
            font-size: 12px;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.02em;
            color: var(--grey-700);
            margin-bottom: var(--space-1);
        }

        .setting-description {
            font-family: var(--font-mono);
            font-size: 11px;
            color: var(--grey-500);
            margin-top: 4px;
        }

        .setting-input {
            width: 100%;
            padding: var(--space-2);
            background: var(--white);
            border: 1px solid var(--grey-300);
            font-family: var(--font-mono);
            font-size: 14px;
            color: var(--black);
            transition: all 0.2s;
        }

        .setting-input:focus {
            outline: none;
            border-color: var(--black);
        }

        .setting-input:disabled {
            background: var(--grey-100);
            color: var(--grey-500);
            cursor: not-allowed;
        }

        .setting-input.masked {
            letter-spacing: 2px;
        }

        .unsaved-indicator {
            font-size: 12px;
            color: #ff6b6b;
            font-weight: 500;
            margin-left: var(--space-2);
            animation: pulse 2s ease-in-out infinite;
        }

        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.6; }
        }

        .btn-test {
            width: 100%;
            margin-top: var(--space-2);
            padding: var(--space-2);
            background: var(--grey-800);
            border: 1px solid var(--grey-800);
            color: var(--white);
            font-family: var(--font-mono);
            font-size: 13px;
            font-weight: 500;
            cursor: pointer;
            transition: all 0.2s;
        }

        .btn-test:hover {
            background: var(--grey-700);
            border-color: var(--grey-700);
        }

        /* Select dropdown */
        select.setting-input {
            cursor: pointer;
        }

        /* Checkbox */
        .checkbox-row {
            display: flex;
            align-items: center;
            gap: var(--space-1);
        }

        .checkbox-row input[type="checkbox"] {
            width: 20px;
            height: 20px;
            cursor: pointer;
        }

        .checkbox-row label {
            cursor: pointer;
            margin: 0;
            font-size: 14px;
        }

        /* Textarea for prompt editor */
        .prompt-editor {
            width: 100%;
            min-height: 400px;
            padding: var(--space-2);
            background: var(--white);
            border: 1px solid var(--grey-300);
            font-family: var(--font-mono);
            font-size: 13px;
            line-height: 1.6;
            color: var(--black);
            resize: vertical;
            transition: all 0.2s;
        }

        .prompt-editor:focus {
            outline: none;
            border-color: var(--black);
        }

        /* Button groups */
        .button-group {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: var(--space-1);
            margin-top: var(--space-3);
        }

        .btn-secondary {
            padding: var(--space-2);
            background: var(--white);
            border: 1px solid var(--grey-300);
            color: var(--black);
            font-family: var(--font-mono);
            font-size: 14px;
            font-weight: 500;
            cursor: pointer;
            transition: all 0.2s;
        }

        .btn-secondary:hover {
            background: var(--grey-100);
            border-color: var(--grey-700);
        }

        .btn-danger {
            padding: var(--space-2);
            background: var(--white);
            border: 2px solid #ff4444;
            color: #ff4444;
            font-family: var(--font-mono);
            font-size: 14px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.2s;
        }

        .btn-danger:hover {
            background: #ff4444;
            color: var(--white);
        }

        /* Update modal specific styles */
        .modal-input {
            width: 100%;
            padding: var(--space-2);
            background: var(--white);
            border: 1px solid var(--grey-300);
            font-family: var(--font-mono);
            font-size: 14px;
            margin-top: var(--space-1);
        }

        .modal-input:focus {
            outline: none;
            border-color: var(--black);
        }

        /* Test result message */
        .test-result {
            margin-top: var(--space-2);
            padding: var(--space-2);
            font-family: var(--font-mono);
            font-size: 13px;
            border-left: 3px solid;
        }

        .test-result.success {
            background: var(--grey-100);
            border-color: var(--black);
            color: var(--black);
        }

        .test-result.error {
            background: var(--grey-900);
            border-color: var(--grey-700);
            color: var(--white);
        }

        /* Single column layout for settings pages */
        .settings-container .container {
            grid-template-columns: 1fr;
        }

        /* ========================================
           CHANNELS PAGE SPECIFIC STYLES
           ======================================== */

        /* Channel list container */
        .channels-list {
            display: grid;
            gap: var(--space-2);
        }

        /* Enhanced channel card */
        .channel-card {
            padding: var(--space-3);
            background: var(--white);
            border: 1px solid var(--grey-200);
            transition: all 0.2s;
        }

        .channel-card:hover {
            border-color: var(--grey-300);
            background: var(--grey-100);
        }

        .channel-card-header {
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-bottom: var(--space-2);
            gap: var(--space-2);
        }

        .channel-name-section {
            min-width: 0;
            flex: 1;
        }

        .channel-name {
            font-family: var(--font-mono);
            font-size: 16px;
            font-weight: 600;
            color: var(--black);
            margin-bottom: 4px;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }

        .channel-id {
            font-family: var(--font-mono);
            font-size: 11px;
            color: var(--grey-500);
            letter-spacing: 0.02em;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }

        /* Channel stats row */
        .channel-stats {
            font-family: var(--font-mono);
            font-size: 12px;
            color: var(--grey-500);
            display: flex;
            align-items: center;
            gap: var(--space-2);
            flex-wrap: nowrap;
            white-space: nowrap;
        }

        .channel-stat {
            display: inline-flex;
            align-items: center;
            gap: 4px;
        }

        .stat-value {
            font-weight: 600;
            color: var(--black);
        }

        .stat-separator {
            color: var(--grey-300);
        }

        /* Channel actions */
        .channel-actions {
            display: grid;
            grid-template-columns: 1fr auto;
            gap: var(--space-1);
            margin-top: var(--space-2);
        }

        /* Feed controls */
        .feed-controls {
            display: flex;
            gap: var(--space-1);
            margin-bottom: var(--space-3);
            flex-wrap: wrap;
        }

        /* Video feed */
        .video-feed {
            margin-top: var(--space-2);
        }

        .video-item {
            padding: var(--space-2);
            border-bottom: 1px solid var(--grey-200);
            transition: background 0.2s;
            cursor: pointer;
        }

        .video-item:last-child {
            border-bottom: none;
        }

        .video-item:hover {
            background: var(--grey-100);
        }

        .video-title {
            font-family: var(--font-mono);
            font-size: 14px;
            font-weight: 500;
            color: var(--black);
            margin-bottom: 6px;
            line-height: 1.4;
        }

        .video-meta {
            font-family: var(--font-mono);
            font-size: 11px;
            color: var(--grey-500);
            display: flex;
            align-items: center;
            gap: var(--space-1);
            flex-wrap: wrap;
        }

        .video-channel {
            color: var(--grey-700);
            font-weight: 500;
        }

        .video-date,
        .video-duration {
            color: var(--grey-500);
        }

        .meta-separator {
            color: var(--grey-300);
        }

        /* Mobile adjustments for channel cards */
        @media (max-width: 600px) {
            .channel-actions {
                grid-template-columns: 1fr;
            }

            .feed-controls {
                flex-direction: column;
            }

            .feed-controls select {
                width: 100% !important;
            }

            .channel-card-header {
                flex-direction: column;
                align-items: flex-start;
            }

            .channel-stats {
                flex-wrap: wrap;
            }
        }
    </style>
</head>
<body>
    <!-- Header with Tabs -->
    <header>
        <h1>YAYS - Yet Another Youtube Summarizer</h1>
        <nav class="tabs">
            <button class="tab-btn active" onclick="showTab('channels')">Channels</button>
            <button class="tab-btn" onclick="showTab('feed')">Feed</button>
            <button class="tab-btn" onclick="showTab('settings')">Settings</button>
            <button class="tab-btn" onclick="showTab('advanced')">Advanced</button>
        </nav>
    </header>

    <!-- TAB 1: CHANNELS -->
    <div id="tab-channels" class="tab-content active">
        <div class="settings-container">
            <div id="status" class="status"></div>

            <!-- Add Channel Section -->
            <div class="settings-section">
                <h3>➕ Add Channel</h3>

                <div class="setting-row">
                    <label class="setting-label">Channel ID or URL</label>
                    <input
                        type="text"
                        id="channelId"
                        class="setting-input"
                        placeholder="UCddiUEpeqJcYeBxX1IVBKvQ"
                        autocomplete="off"
                        autocapitalize="off"
                        autocorrect="off"
                    />
                    <div class="setting-description">
                        Paste YouTube channel URL or ID (name will be auto-fetched)
                    </div>
                </div>

                <div class="setting-row">
                    <label class="setting-label">Display Name (Optional)</label>
                    <input
                        type="text"
                        id="channelName"
                        class="setting-input"
                        placeholder="The Verge"
                        autocomplete="off"
                        maxlength="100"
                    />
                    <div class="setting-description">
                        Leave blank to automatically fetch from YouTube
                    </div>
                </div>

                <button id="addBtn" onclick="addChannel()" style="width: 100%; padding: 16px; font-size: 15px;">
                    Add Channel
                </button>
            </div>

            <!-- Active Channels Section -->
            <div class="settings-section" id="channelsSection">
                <h3>📺 Active Channels (<span id="count">0</span>)</h3>

                <div id="loading" class="loading">Loading channels...</div>

                <div id="empty" class="empty" style="display: none;">
                    <div class="empty-icon">—</div>
                    <p class="empty-text">No channels configured</p>
                </div>

                <div id="channels" class="channels-list"></div>
            </div>
        </div>
    </div>

    <!-- TAB 2: FEED -->
    <div id="tab-feed" class="tab-content">
        <div class="settings-container">
            <!-- Processed Videos Feed Section -->
            <div class="settings-section" id="feedSection">
                <h3>🎬 Processed Videos (<span id="feedCount">0</span>)</h3>

                <!-- Feed Controls -->
                <div class="feed-controls">
                    <select id="feedChannelFilter" class="setting-input" style="width: 200px;" onchange="filterFeed()">
                        <option value="">All Channels</option>
                    </select>

                    <select id="feedSortOrder" class="setting-input" style="width: 150px;" onchange="filterFeed()">
                        <option value="recent">Most Recent</option>
                        <option value="oldest">Oldest First</option>
                        <option value="channel">By Channel</option>
                    </select>
                </div>

                <div id="feedEmpty" class="empty" style="display: none;">
                    <div class="empty-icon">—</div>
                    <p class="empty-text">No videos processed yet</p>
                </div>

                <div id="videoFeed" class="video-feed"></div>

                <button id="loadMoreBtn" class="btn-secondary" style="width: 100%; display: none;" onclick="loadMoreVideos()">
                    Load More (<span id="remainingCount">0</span> remaining)
                </button>
            </div>
        </div>
    </div>

    <!-- TAB 3: SETTINGS -->
    <div id="tab-settings" class="tab-content">
        <div class="settings-container">
            <!-- Credentials Section -->
            <div class="settings-section">
                <h3>🔒 Credentials <span id="unsaved-credentials" class="unsaved-indicator" style="display: none;">● Unsaved changes</span></h3>

                <div class="setting-row">
                    <label class="setting-label">OpenAI API Key</label>
                    <input type="password" id="OPENAI_API_KEY" class="setting-input trackable-input" data-section="credentials" placeholder="sk-...">
                    <div class="setting-description">Get from: https://platform.openai.com/api-keys</div>
                    <button class="btn-test" onclick="testOpenAIKey()">Test OpenAI API</button>
                    <div id="openai-test-result"></div>
                </div>

                <div class="setting-row">
                    <label class="setting-label">Target Email</label>
                    <input type="email" id="TARGET_EMAIL" class="setting-input trackable-input" data-section="credentials">
                    <div class="setting-description">Email address for receiving summaries</div>
                </div>

                <div class="setting-row">
                    <label class="setting-label">Gmail SMTP User</label>
                    <input type="email" id="SMTP_USER" class="setting-input trackable-input" data-section="credentials">
                    <div class="setting-description">Your Gmail address</div>
                </div>

                <div class="setting-row">
                    <label class="setting-label">Gmail App Password</label>
                    <input type="password" id="SMTP_PASS" class="setting-input trackable-input" data-section="credentials" placeholder="16-character app password">
                    <div class="setting-description">16-character app password - <a href="https://myaccount.google.com/apppasswords" target="_blank" style="color: var(--black); text-decoration: underline;">Create Gmail App Password</a></div>
                    <button class="btn-test" onclick="testSmtpCredentials()">Test SMTP Connection</button>
                    <div id="smtp-test-result"></div>
                </div>
            </div>

            <!-- Application Settings -->
            <div class="settings-section">
                <h3>⚙️ Application Settings <span id="unsaved-app" class="unsaved-indicator" style="display: none;">● Unsaved changes</span></h3>

                <div class="setting-row">
                    <label class="setting-label">Log Level</label>
                    <select id="LOG_LEVEL" class="setting-input trackable-input" data-section="app">
                        <option value="DEBUG">DEBUG</option>
                        <option value="INFO">INFO</option>
                        <option value="WARNING">WARNING</option>
                        <option value="ERROR">ERROR</option>
                    </select>
                    <div class="setting-description">Logging verbosity (requires restart)</div>
                </div>

                <div class="setting-row">
                    <label class="setting-label">Check Interval (hours)</label>
                    <input type="number" id="CHECK_INTERVAL_HOURS" class="setting-input trackable-input" data-section="app" min="1" max="24">
                    <div class="setting-description">How often to check for new videos (requires restart)</div>
                </div>

                <div class="setting-row">
                    <label class="setting-label">Max Processed Videos</label>
                    <input type="number" id="MAX_PROCESSED_ENTRIES" class="setting-input trackable-input" data-section="app" min="100" max="100000">
                    <div class="setting-description">Video history limit before rotation (requires restart)</div>
                </div>
            </div>

            <!-- Video Processing Settings -->
            <div class="settings-section">
                <h3>📹 Video Processing <span id="unsaved-video" class="unsaved-indicator" style="display: none;">● Unsaved changes</span></h3>

                <div class="setting-row">
                    <label class="setting-label">Summary Length (tokens)</label>
                    <input type="number" id="SUMMARY_LENGTH" class="setting-input trackable-input" data-section="video" min="100" max="2000">
                    <div class="setting-description">Maximum summary length (affects cost)</div>
                </div>

                <div class="setting-row">
                    <div class="checkbox-row">
                        <input type="checkbox" id="SKIP_SHORTS" class="trackable-input" data-section="video">
                        <label for="SKIP_SHORTS" class="setting-label">Skip YouTube Shorts</label>
                    </div>
                    <div class="setting-description">Ignore videos shorter than 60 seconds</div>
                </div>

                <div class="setting-row">
                    <label class="setting-label">Max Videos Per Channel</label>
                    <input type="number" id="MAX_VIDEOS_PER_CHANNEL" class="setting-input trackable-input" data-section="video" min="1" max="20">
                    <div class="setting-description">Maximum videos to check per channel per cycle</div>
                </div>
            </div>

            <!-- Status Message -->
            <div id="settingsStatus" class="status"></div>

            <!-- Restart Notification -->
            <div id="restartNotification" class="restart-notification" style="display: none;">
                Settings updated. Restart Docker containers to apply changes.
                <button onclick="restartApplication()" class="btn-restart-inline">Restart Now</button>
            </div>

            <!-- Save Button -->
            <button onclick="saveAllSettings()" style="width: 100%; padding: 16px; font-size: 15px;">
                Save Settings
            </button>

            <!-- Backup & Restore Section -->
            <div class="settings-section" style="margin-top: 40px;">
                <h3>💾 Backup & Restore</h3>

                <div class="setting-row">
                    <button onclick="downloadBackup()" style="width: 100%;">
                        Download Complete Backup
                    </button>
                    <div class="setting-description">
                        Export all data: channels, videos, settings, and AI prompt
                    </div>
                </div>

                <div class="setting-row">
                    <label class="setting-label">Import Backup</label>
                    <input type="file" id="backupFile" accept=".json" style="display: none;" onchange="handleBackupImport(event)">
                    <button onclick="document.getElementById('backupFile').click()" class="btn-secondary" style="width: 100%;">
                        Choose Backup File
                    </button>
                    <div class="setting-description">
                        Restore from a previously exported backup file
                    </div>
                </div>
            </div>

            <!-- Risky Deletion Commands -->
            <div class="settings-section" style="margin-top: 40px; border: 2px solid #ff4444; padding: 20px;">
                <h3 style="color: #ff4444; cursor: pointer; user-select: none;" onclick="toggleDangerZone()">
                    <span id="dangerZoneToggle">▶</span> ⚠️ Danger Zone
                </h3>

                <div id="dangerZoneContent" style="display: none;">
                    <div class="setting-row">
                        <button onclick="promptResetSettings()" class="btn-danger" style="width: 100%;">
                            Reset Settings
                        </button>
                        <div class="setting-description" style="color: #888;">
                            Resets all settings and AI prompt to defaults. Channels and feed history will be preserved.
                        </div>
                    </div>

                    <div class="setting-row">
                        <button onclick="promptResetFeedHistory()" class="btn-danger" style="width: 100%;">
                            Reset Feed History
                        </button>
                        <div class="setting-description" style="color: #888;">
                            Deletes all processed videos from the feed. Channels and settings will be preserved.
                        </div>
                    </div>

                    <div class="setting-row">
                        <button onclick="promptResetYoutubeData()" class="btn-danger" style="width: 100%;">
                            Reset YouTube Data
                        </button>
                        <div class="setting-description" style="color: #888;">
                            Deletes all channels and feed history. Settings and prompts will be preserved.
                        </div>
                    </div>

                    <div class="setting-row">
                        <button onclick="promptResetCompleteApp()" class="btn-danger" style="width: 100%;">
                            Reset Complete App
                        </button>
                        <div class="setting-description" style="color: #888;">
                            Deletes all data: channels, feed history, and resets all settings and prompts to defaults.
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <!-- TAB 4: ADVANCED (Prompt Editor) -->
    <div id="tab-advanced" class="tab-content">
        <div class="settings-container">
            <div id="advancedStatus" class="status"></div>

            <div class="settings-section">
                <h3>✏️ AI Prompt Template</h3>

                <div class="setting-row">
                    <label class="setting-label">Prompt</label>
                    <textarea id="promptEditor" class="prompt-editor"></textarea>
                    <div class="setting-description">
                        Available variables: {title}, {duration}, {transcript}
                    </div>
                </div>

                <div class="button-group">
                    <button class="btn-secondary" onclick="resetPrompt()">Reset to Default</button>
                    <button onclick="savePrompt()">Save Prompt</button>
                </div>
            </div>
        </div>
    </div>

    <!-- Modal for confirmations -->
    <div id="modal" class="modal">
        <div class="modal-content">
            <h3 class="modal-title" id="modalTitle">Remove Channel</h3>
            <p class="modal-message" id="modalMessage"></p>
            <div class="modal-buttons">
                <button class="modal-btn modal-btn-cancel" onclick="closeModal()">Cancel</button>
                <button class="modal-btn modal-btn-confirm" id="modalConfirmBtn" onclick="confirmRemove()">Remove</button>
            </div>
        </div>
    </div>

    <script>
        // Global state
        let channels = [];
        let channelNames = {};
        let channelStats = {};
        let isLoading = false;
        let pendingRemoval = null;
        let pendingAction = null;  // For storing the action to be confirmed
        let feedOffset = 0;
        let feedLimit = 25;

        // Load channels
        async function loadChannels() {
            try {
                // Load channels
                const response = await fetch('/api/channels');
                if (!response.ok) throw new Error('Failed to load');

                const data = await response.json();
                channels = data.channels || [];
                channelNames = data.names || {};

                // Load stats
                await loadChannelStats();

                renderChannels();

                // Load video feed
                await loadVideoFeed();

                // Populate channel filter
                populateChannelFilter();

            } catch (error) {
                showStatus('Failed to load channels', true);
            } finally {
                document.getElementById('loading').style.display = 'none';
            }
        }

        // Load channel statistics
        async function loadChannelStats() {
            try {
                const response = await fetch('/api/stats/channels');
                if (!response.ok) return;

                const data = await response.json();
                channelStats = data.channels || {};

            } catch (error) {
                console.error('Failed to load stats:', error);
            }
        }

        // Render channels with enhanced cards
        function renderChannels() {
            const container = document.getElementById('channels');
            const empty = document.getElementById('empty');
            const count = document.getElementById('count');

            count.textContent = channels.length;

            if (channels.length === 0) {
                empty.style.display = 'block';
                container.innerHTML = '';
                return;
            }

            empty.style.display = 'none';
            container.innerHTML = '';

            channels.forEach(id => {
                const name = channelNames[id] || id;
                const showId = name !== id;
                const stats = channelStats[id] || { total_videos: 0, hours_saved: 0 };

                const div = document.createElement('div');
                div.className = 'channel-card';
                div.innerHTML = `
                    <div class="channel-card-header">
                        <div class="channel-name-section">
                            <div class="channel-name">${escapeHtml(name)}</div>
                            ${showId ? `<div class="channel-id">${escapeHtml(id)}</div>` : ''}
                        </div>
                        <div class="channel-stats">
                            <span class="channel-stat">
                                <span class="stat-icon">📊</span>
                                <span class="stat-value">${stats.total_videos || 0}</span>
                                <span class="stat-label">summaries</span>
                            </span>
                            <span class="stat-separator">•</span>
                            <span class="channel-stat">
                                <span class="stat-icon">⏱️</span>
                                <span class="stat-value">${stats.hours_saved || 0}</span>
                                <span class="stat-label">hours processed</span>
                            </span>
                        </div>
                    </div>

                    <div class="channel-actions">
                        <button class="btn-secondary" onclick="viewChannelFeed('${escapeAttr(id)}')">
                            View Feed
                        </button>
                        <button class="btn-remove" onclick="promptRemove('${escapeAttr(id)}')">
                            Remove
                        </button>
                    </div>
                `;
                container.appendChild(div);
            });
        }

        // HTML escape
        function escapeHtml(text) {
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }

        // Attribute escape
        function escapeAttr(text) {
            return text.replace(/'/g, "\\\\'").replace(/"/g, '&quot;');
        }

        // Prompt removal
        function promptRemove(id) {
            pendingRemoval = id;
            const name = channelNames[id] || id;
            document.getElementById('modalMessage').textContent =
                `Are you sure you want to remove "${name}"?`;
            document.getElementById('modal').classList.add('show');
        }

        // Close modal
        function closeModal() {
            document.getElementById('modal').classList.remove('show');
            pendingRemoval = null;
            pendingAction = null;
        }

        // Confirm removal
        async function confirmRemove() {
            if (!pendingRemoval) return;

            channels = channels.filter(id => id !== pendingRemoval);
            delete channelNames[pendingRemoval];

            closeModal();
            await saveChannels();
            renderChannels();
        }



        // Generic modal prompt
        function showConfirmModal(title, message, confirmText, confirmCallback) {
            document.getElementById('modalTitle').textContent = title;
            document.getElementById('modalMessage').textContent = message;
            document.getElementById('modalConfirmBtn').textContent = confirmText;
            pendingAction = confirmCallback;

            // Update the confirm button onclick
            const confirmBtn = document.getElementById('modalConfirmBtn');
            confirmBtn.onclick = async function() {
                if (pendingAction) {
                    await pendingAction();
                    closeModal();
                }
            };

            document.getElementById('modal').classList.add('show');
        }

        // Risky deletion functions
        async function promptResetSettings() {
            showConfirmModal(
                '⚠️ Reset Settings',
                'This will reset all settings and AI prompt to defaults. Your channels and feed history will be preserved. This action cannot be undone. Are you sure?',
                'Reset Settings',
                confirmResetSettings
            );
        }

        async function confirmResetSettings() {
            try {
                const response = await fetch('/api/reset/settings', {
                    method: 'POST'
                });

                if (!response.ok) {
                    const error = await response.json();
                    throw new Error(error.detail || 'Failed to reset settings');
                }

                const result = await response.json();

                // Show success message from API
                alert(result.message);
                showSettingsStatus(result.message);

                // Reload the page to reflect changes
                setTimeout(() => location.reload(), 1000);
            } catch (error) {
                alert('❌ Error: ' + error.message);
                showSettingsStatus('Failed to reset settings: ' + error.message, true);
            }
        }

        async function promptResetYoutubeData() {
            showConfirmModal(
                '⚠️ Reset YouTube Data',
                'This will permanently delete all channels and feed history. Your settings and AI prompt will be preserved. This action cannot be undone. Are you sure?',
                'Reset YouTube Data',
                confirmResetYoutubeData
            );
        }

        async function confirmResetYoutubeData() {
            try {
                const response = await fetch('/api/reset/youtube-data', {
                    method: 'POST'
                });

                if (!response.ok) {
                    const error = await response.json();
                    throw new Error(error.detail || 'Failed to reset YouTube data');
                }

                const result = await response.json();

                // Show success message from API
                alert(result.message);
                showSettingsStatus(result.message);

                // Reload the page to reflect changes
                setTimeout(() => location.reload(), 1000);
            } catch (error) {
                alert('❌ Error: ' + error.message);
                showSettingsStatus('Failed to reset YouTube data: ' + error.message, true);
            }
        }

        async function promptResetFeedHistory() {
            showConfirmModal(
                '⚠️ Reset Feed History',
                'This will permanently delete all processed videos from your feed. Your channels and settings will be preserved. This action cannot be undone. Are you sure?',
                'Reset Feed History',
                confirmResetFeedHistory
            );
        }

        async function confirmResetFeedHistory() {
            try {
                const response = await fetch('/api/reset/feed-history', {
                    method: 'POST'
                });

                if (!response.ok) {
                    const error = await response.json();
                    throw new Error(error.detail || 'Failed to reset feed history');
                }

                const result = await response.json();

                // Show success message from API
                alert(result.message);
                showSettingsStatus(result.message);

                // Reload the feed
                feedOffset = 0;
                await loadVideoFeed();
            } catch (error) {
                alert('❌ Error: ' + error.message);
                showSettingsStatus('Failed to reset feed history: ' + error.message, true);
            }
        }

        async function promptResetCompleteApp() {
            showConfirmModal(
                '⚠️ Reset Complete App',
                'This will permanently delete ALL data including channels, feed history, and reset all settings and prompts to defaults. This action cannot be undone. Are you absolutely sure?',
                'Reset Everything',
                confirmResetCompleteApp
            );
        }

        async function confirmResetCompleteApp() {
            try {
                const response = await fetch('/api/reset/complete', {
                    method: 'POST'
                });

                if (!response.ok) {
                    const error = await response.json();
                    throw new Error(error.detail || 'Failed to reset app');
                }

                const result = await response.json();

                // Show success message from API
                alert(result.message);
                showSettingsStatus(result.message);

                // Reload the page to reflect changes
                setTimeout(() => location.reload(), 1000);
            } catch (error) {
                alert('❌ Error: ' + error.message);
                showSettingsStatus('Failed to reset app: ' + error.message, true);
            }
        }

        // Toggle Danger Zone visibility
        function toggleDangerZone() {
            const content = document.getElementById('dangerZoneContent');
            const toggle = document.getElementById('dangerZoneToggle');

            if (content.style.display === 'none') {
                content.style.display = 'block';
                toggle.textContent = '▼';
            } else {
                content.style.display = 'none';
                toggle.textContent = '▶';
            }
        }

        // Download complete backup
        async function downloadBackup() {
            try {
                showSettingsStatus('Preparing backup...', false);

                const response = await fetch('/api/export/backup');

                if (!response.ok) {
                    const error = await response.json();
                    throw new Error(error.detail || 'Backup export failed');
                }

                // Get the filename from Content-Disposition header or use default
                const contentDisposition = response.headers.get('Content-Disposition');
                let filename = 'youtube-summarizer-backup.json';
                if (contentDisposition) {
                    const filenameMatch = contentDisposition.match(/filename="?(.+)"?/);
                    if (filenameMatch) {
                        filename = filenameMatch[1];
                    }
                }

                // Download the file
                const blob = await response.blob();
                const url = window.URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = filename;
                document.body.appendChild(a);
                a.click();
                window.URL.revokeObjectURL(url);
                document.body.removeChild(a);

                showSettingsStatus('Backup downloaded successfully', false);
            } catch (error) {
                console.error('Backup failed:', error);
                showSettingsStatus('Failed to download backup: ' + error.message, true);
            }
        }

        // Handle backup file import
        async function handleBackupImport(event) {
            const file = event.target.files[0];
            if (!file) return;

            try {
                showSettingsStatus('Reading backup file...', false);

                const formData = new FormData();
                formData.append('file', file);

                // First validate the backup
                const validateResponse = await fetch('/api/import/validate', {
                    method: 'POST',
                    body: formData
                });

                if (!validateResponse.ok) {
                    const error = await validateResponse.json();
                    throw new Error(error.detail || 'Invalid backup file');
                }

                const validation = await validateResponse.json();

                // Show confirmation dialog
                const preview = validation.preview || {};
                const totalChannels = (preview.channels_new || 0) + (preview.channels_existing || 0);
                const totalVideos = (preview.videos_new || 0) + (preview.videos_duplicate || 0);

                const message = `This will import:\n\n` +
                    `- ${totalChannels} channels (${preview.channels_new || 0} new, ${preview.channels_existing || 0} existing)\n` +
                    `- ${totalVideos} videos (${preview.videos_new || 0} new, ${preview.videos_duplicate || 0} duplicates)\n` +
                    `- ${preview.settings_changed || 0} settings will be updated\n\n` +
                    `Continue?`;

                if (!confirm(message)) {
                    showSettingsStatus('Import cancelled', false);
                    event.target.value = ''; // Reset file input
                    return;
                }

                // Perform the import
                showSettingsStatus('Restoring backup...', false);

                const importFormData = new FormData();
                importFormData.append('file', file);

                const importResponse = await fetch('/api/import/execute', {
                    method: 'POST',
                    body: importFormData
                });

                if (!importResponse.ok) {
                    const error = await importResponse.json();
                    throw new Error(error.detail || 'Import failed');
                }

                const result = await importResponse.json();

                showSettingsStatus(
                    `Backup restored successfully! ` +
                    `${result.channels_added || 0} channels, ` +
                    `${result.videos_added || 0} videos, ` +
                    `${result.settings_updated || 0} settings imported.`,
                    false
                );

                // Reload the page after a short delay to reflect the changes
                setTimeout(() => {
                    window.location.reload();
                }, 2000);

            } catch (error) {
                console.error('Import failed:', error);
                showSettingsStatus('Failed to import backup: ' + error.message, true);
            } finally {
                // Reset file input
                event.target.value = '';
            }
        }

        // Add channel
        async function addChannel() {
            if (isLoading) return;

            const idInput = document.getElementById('channelId');
            const nameInput = document.getElementById('channelName');
            const addBtn = document.getElementById('addBtn');

            const input = idInput.value.trim();
            const name = nameInput.value.trim();

            if (!input) {
                showStatus('Please enter a channel ID or URL', true);
                return;
            }

            // Get the actual channel ID by calling the fetch endpoint
            // This will handle URLs, @handles, and channel IDs
            isLoading = true;
            addBtn.disabled = true;
            addBtn.textContent = 'Resolving...';

            let channelId;
            let channelName;

            try {
                const response = await fetch(`/api/fetch-channel-name/${encodeURIComponent(input)}`);

                if (!response.ok) {
                    const error = await response.json();
                    showStatus(error.detail || 'Invalid channel', true);
                    isLoading = false;
                    addBtn.disabled = false;
                    addBtn.textContent = 'Add Channel';
                    return;
                }

                const data = await response.json();
                channelId = data.channel_id;
                channelName = name || data.channel_name;

                // Auto-fill the display name field if it was left empty
                if (!name && data.channel_name) {
                    nameInput.value = data.channel_name;
                }

            } catch (error) {
                showStatus('Failed to resolve channel: ' + error.message, true);
                isLoading = false;
                addBtn.disabled = false;
                addBtn.textContent = 'Add Channel';
                return;
            }

            // Check if already exists
            if (channels.includes(channelId)) {
                showStatus('Channel already exists', true);
                isLoading = false;
                addBtn.disabled = false;
                addBtn.textContent = 'Add Channel';
                return;
            }

            // Add
            addBtn.textContent = 'Adding...';

            channels.push(channelId);
            channelNames[channelId] = channelName;

            const saved = await saveChannels();

            // If save was successful, fetch initial videos
            if (saved) {
                addBtn.textContent = 'Fetching videos...';
                try {
                    const response = await fetch(`/api/channels/${encodeURIComponent(channelId)}/fetch-initial-videos`, {
                        method: 'POST'
                    });

                    if (response.ok) {
                        const result = await response.json();
                        showStatus(`Channel added! Fetched ${result.videos_fetched} recent videos.`, false);
                    } else {
                        showStatus('Channel added, but could not fetch initial videos', false);
                    }
                } catch (error) {
                    console.error('Error fetching initial videos:', error);
                    showStatus('Channel added, but could not fetch initial videos', false);
                }
            }

            idInput.value = '';
            nameInput.value = '';
            renderChannels();

            isLoading = false;
            addBtn.disabled = false;
            addBtn.textContent = 'Add Channel';
        }

        // Save channels
        async function saveChannels() {
            try {
                const response = await fetch('/api/channels', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ channels, names: channelNames })
                });

                if (!response.ok) {
                    const errorData = await response.json().catch(() => ({}));
                    console.error('Save failed:', response.status, errorData);
                    throw new Error(`Save failed: ${response.status}`);
                }

                const result = await response.json();
                console.log('Save successful:', result);
                showStatus('Saved successfully', false);
                return true;
            } catch (error) {
                console.error('Save error:', error);
                showStatus('Failed to save: ' + error.message, true);
                return false;
            }
        }

        // Show status
        function showStatus(msg, isError) {
            const status = document.getElementById('status');
            status.textContent = msg;
            status.className = isError ? 'status error show' : 'status show';
            setTimeout(() => status.classList.remove('show'), 3000);
        }

        // Video feed functions
        async function loadVideoFeed(reset = false) {
            if (reset) {
                feedOffset = 0;
                document.getElementById('videoFeed').innerHTML = '';
            }

            try {
                const channelFilter = document.getElementById('feedChannelFilter').value;
                const sortOrder = document.getElementById('feedSortOrder').value;

                const params = new URLSearchParams({
                    limit: feedLimit,
                    offset: feedOffset,
                    order_by: sortOrder
                });

                if (channelFilter) {
                    params.append('channel_id', channelFilter);
                }

                const response = await fetch(`/api/videos/feed?${params}`);
                if (!response.ok) return;

                const data = await response.json();

                // Update count
                document.getElementById('feedCount').textContent = data.total;

                // Show/hide empty state
                if (data.total === 0) {
                    document.getElementById('feedEmpty').style.display = 'block';
                    document.getElementById('videoFeed').style.display = 'none';
                    document.getElementById('loadMoreBtn').style.display = 'none';
                    return;
                } else {
                    document.getElementById('feedEmpty').style.display = 'none';
                    document.getElementById('videoFeed').style.display = 'block';
                }

                // Render videos
                const feedContainer = document.getElementById('videoFeed');
                data.videos.forEach(video => {
                    const div = document.createElement('div');
                    div.className = 'video-item';
                    div.innerHTML = `
                        <div class="video-title">${escapeHtml(video.title)}</div>
                        <div class="video-meta">
                            <span class="video-channel">${escapeHtml(video.channel_name)}</span>
                            <span class="meta-separator">•</span>
                            <span class="video-date">${escapeHtml(video.processed_date_formatted)}</span>
                            <span class="meta-separator">•</span>
                            <span class="video-duration">${escapeHtml(video.duration_formatted)}</span>
                        </div>
                    `;
                    feedContainer.appendChild(div);
                });

                // Show/hide load more button
                if (data.has_more) {
                    const remaining = data.total - (feedOffset + feedLimit);
                    document.getElementById('remainingCount').textContent = remaining;
                    document.getElementById('loadMoreBtn').style.display = 'block';
                } else {
                    document.getElementById('loadMoreBtn').style.display = 'none';
                }

            } catch (error) {
                console.error('Failed to load video feed:', error);
            }
        }

        function loadMoreVideos() {
            feedOffset += feedLimit;
            loadVideoFeed(false);
        }

        function filterFeed() {
            loadVideoFeed(true);
        }

        function viewChannelFeed(channelId) {
            // Set filter to channel
            document.getElementById('feedChannelFilter').value = channelId;

            // Switch to feed tab
            showTab('feed');

            // Reload feed with filter
            filterFeed();
        }

        function populateChannelFilter() {
            const select = document.getElementById('feedChannelFilter');

            // Keep "All Channels" option
            select.innerHTML = '<option value="">All Channels</option>';

            // Add each channel
            channels.forEach(id => {
                const name = channelNames[id] || id;
                const option = document.createElement('option');
                option.value = id;
                option.textContent = name;
                select.appendChild(option);
            });
        }

        // Auto-fetch channel name
        let fetchTimeout = null;
        document.getElementById('channelId').addEventListener('input', async e => {
            const input = e.target.value.trim();

            // Clear previous timeout
            if (fetchTimeout) clearTimeout(fetchTimeout);

            // Check if input is empty or too short
            if (!input || input.length < 3) return;

            // Check if it looks like a valid channel ID, URL, or @handle
            const isChannelId = /UC[\w-]{22}/.test(input);
            const isUrl = /youtube\.com/.test(input);
            const isHandle = /^@[\w-]+$/.test(input);

            if (!isChannelId && !isUrl && !isHandle) return;

            const nameInput = document.getElementById('channelName');

            // Debounce: wait 500ms after user stops typing
            fetchTimeout = setTimeout(async () => {
                try {
                    nameInput.value = 'Fetching...';
                    nameInput.disabled = true;

                    const response = await fetch(`/api/fetch-channel-name/${encodeURIComponent(input)}`);

                    if (response.ok) {
                        const data = await response.json();
                        nameInput.value = data.channel_name;
                        showStatus(`Found: ${data.channel_name}`, false);
                    } else {
                        nameInput.value = '';
                        console.log('Could not fetch channel name');
                    }
                } catch (error) {
                    nameInput.value = '';
                    console.log('Error fetching channel name:', error);
                } finally {
                    nameInput.disabled = false;
                }
            }, 500);
        });

        // Keyboard shortcuts
        document.getElementById('channelId').addEventListener('keypress', e => {
            if (e.key === 'Enter') {
                e.preventDefault();
                document.getElementById('channelName').focus();
            }
        });

        document.getElementById('channelName').addEventListener('keypress', e => {
            if (e.key === 'Enter') {
                e.preventDefault();
                addChannel();
            }
        });

        document.addEventListener('keydown', e => {
            if (e.key === 'Escape') closeModal();
        });

        document.getElementById('modal').addEventListener('click', e => {
            if (e.target.id === 'modal') closeModal();
        });

        // Load on start
        loadChannels();

        // ============================================================================
        // TAB NAVIGATION
        // ============================================================================

        function showTab(tabName) {
            // Hide all tabs
            document.querySelectorAll('.tab-content').forEach(tab => {
                tab.classList.remove('active');
            });

            // Remove active class from all buttons
            document.querySelectorAll('.tab-btn').forEach(btn => {
                btn.classList.remove('active');
            });

            // Show selected tab
            document.getElementById(`tab-${tabName}`).classList.add('active');

            // Activate button (find the button by tab name if event not available)
            if (event && event.target) {
                event.target.classList.add('active');
            } else {
                // Find the button by searching for matching onclick
                const buttons = document.querySelectorAll('.tab-btn');
                buttons.forEach(btn => {
                    if (btn.getAttribute('onclick') === `showTab('${tabName}')`) {
                        btn.classList.add('active');
                    }
                });
            }

            // Load data for the tab
            if (tabName === 'feed') {
                loadVideoFeed(true);
            } else if (tabName === 'settings') {
                loadSettings();
            } else if (tabName === 'advanced') {
                loadPrompt();
            }
        }

        // ============================================================================
        // SETTINGS TAB
        // ============================================================================

        let allSettings = {};

        async function loadSettings() {
            try {
                const response = await fetch('/api/settings');
                if (!response.ok) throw new Error('Failed to load settings');

                const data = await response.json();
                allSettings = data;

                // Populate .env settings
                for (const [key, info] of Object.entries(data.env)) {
                    const element = document.getElementById(key);

                    if (key === 'OPENAI_API_KEY' || key === 'SMTP_PASS') {
                        // For password fields, show placeholder if empty, otherwise show masked value
                        if (element) {
                            element.placeholder = info.masked || (key === 'OPENAI_API_KEY' ? 'sk-...' : '16-character app password');
                        }
                    } else if (element) {
                        if (info.type === 'enum') {
                            element.value = info.value || info.default;
                        } else {
                            element.value = info.value || info.default;
                        }
                    }
                }

                // Populate config settings
                const config = data.config;
                document.getElementById('SUMMARY_LENGTH').value = config.SUMMARY_LENGTH || '500';
                document.getElementById('SKIP_SHORTS').checked = config.SKIP_SHORTS === 'true';
                document.getElementById('MAX_VIDEOS_PER_CHANNEL').value = config.MAX_VIDEOS_PER_CHANNEL || '5';

            } catch (error) {
                showSettingsStatus('Failed to load settings', true);
                console.error(error);
            }
        }

        function showSettingsStatus(msg, isError, autoHide = true) {
            const status = document.getElementById('settingsStatus');
            status.textContent = msg;
            status.className = isError ? 'status error show' : 'status show';
            if (autoHide) {
                setTimeout(() => status.classList.remove('show'), isError ? 5000 : 2000);
            }
        }

        function showAdvancedStatus(msg, isError) {
            const status = document.getElementById('advancedStatus');
            status.textContent = msg;
            status.className = isError ? 'status error show' : 'status show';
            setTimeout(() => status.classList.remove('show'), 5000);
        }

        async function saveAllSettings() {
            try {
                const settingsToSave = {};

                // Get all .env settings
                settingsToSave['TARGET_EMAIL'] = document.getElementById('TARGET_EMAIL').value;
                settingsToSave['SMTP_USER'] = document.getElementById('SMTP_USER').value;
                settingsToSave['LOG_LEVEL'] = document.getElementById('LOG_LEVEL').value;
                settingsToSave['CHECK_INTERVAL_HOURS'] = document.getElementById('CHECK_INTERVAL_HOURS').value;
                settingsToSave['MAX_PROCESSED_ENTRIES'] = document.getElementById('MAX_PROCESSED_ENTRIES').value;

                // Get password fields (only save if they have values)
                const openaiKey = document.getElementById('OPENAI_API_KEY').value;
                if (openaiKey) {
                    settingsToSave['OPENAI_API_KEY'] = openaiKey;
                }

                const smtpPass = document.getElementById('SMTP_PASS').value;
                if (smtpPass) {
                    settingsToSave['SMTP_PASS'] = smtpPass;
                }

                // Get config settings
                settingsToSave['SUMMARY_LENGTH'] = document.getElementById('SUMMARY_LENGTH').value;
                settingsToSave['SKIP_SHORTS'] = document.getElementById('SKIP_SHORTS').checked ? 'true' : 'false';
                settingsToSave['MAX_VIDEOS_PER_CHANNEL'] = document.getElementById('MAX_VIDEOS_PER_CHANNEL').value;

                const response = await fetch('/api/settings', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ settings: settingsToSave })
                });

                if (!response.ok) {
                    const error = await response.json();
                    throw new Error(error.detail?.message || 'Failed to save');
                }

                const result = await response.json();

                showSettingsStatus('✅ Settings saved successfully', false);

                // Show restart notification after success message disappears
                if (result.restart_required) {
                    setTimeout(() => {
                        showRestartNotification();
                    }, 2000);
                }

            } catch (error) {
                showSettingsStatus(`❌ ${error.message}`, true);
                console.error(error);
            }
        }

        function showRestartNotification() {
            // Hide status message
            const status = document.getElementById('settingsStatus');
            status.classList.remove('show');

            // Show restart notification
            document.getElementById('restartNotification').style.display = 'flex';
        }

        // ============================================================================
        // CREDENTIAL TESTING
        // ============================================================================

        async function testOpenAIKey() {
            const resultDiv = document.getElementById('openai-test-result');
            resultDiv.innerHTML = '<div class="test-result">Testing...</div>';

            try {
                const apiKey = document.getElementById('OPENAI_API_KEY').value.trim();

                const response = await fetch('/api/settings/test', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        credential_type: 'openai',
                        test_value: apiKey || undefined
                    })
                });

                const result = await response.json();

                if (result.success) {
                    resultDiv.innerHTML = `<div class="test-result success">${result.message}</div>`;
                } else {
                    resultDiv.innerHTML = `<div class="test-result error">${result.message}</div>`;
                }

            } catch (error) {
                resultDiv.innerHTML = `<div class="test-result error">❌ Test failed: ${error.message}</div>`;
            }
        }

        async function testSmtpCredentials() {
            const resultDiv = document.getElementById('smtp-test-result');
            resultDiv.innerHTML = '<div class="test-result">Testing...</div>';

            try {
                const smtpUser = document.getElementById('SMTP_USER').value.trim();
                const smtpPass = document.getElementById('SMTP_PASS').value.trim();

                const response = await fetch('/api/settings/test', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        credential_type: 'smtp',
                        test_user: smtpUser || undefined,
                        test_pass: smtpPass || undefined
                    })
                });

                const result = await response.json();

                if (result.success) {
                    resultDiv.innerHTML = `<div class="test-result success">${result.message}</div>`;
                } else {
                    resultDiv.innerHTML = `<div class="test-result error">${result.message}</div>`;
                }

            } catch (error) {
                resultDiv.innerHTML = `<div class="test-result error">❌ Test failed: ${error.message}</div>`;
            }
        }

        // ============================================================================
        // RESTART APPLICATION
        // ============================================================================

        async function restartApplication() {
            const notification = document.getElementById('restartNotification');

            // Update notification text
            notification.innerHTML = 'Restarting... <button class="btn-restart-inline" disabled style="opacity: 0.6;">Restarting...</button>';

            // Schedule page reload regardless of response (since server will restart)
            // The fetch might fail because server restarts, but we still want to reload
            const reloadTimer = setTimeout(() => {
                window.location.reload();
            }, 4000);

            try {
                const response = await fetch('/api/settings/restart', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    }
                });

                const result = await response.json();

                if (result.success) {
                    notification.innerHTML = `✅ ${result.message} - Reloading page in 4 seconds...`;
                    // Keep the auto-reload scheduled
                } else {
                    // Cancel auto-reload if restart failed
                    clearTimeout(reloadTimer);
                    notification.innerHTML = `❌ ${result.message} <button onclick="restartApplication()" class="btn-restart-inline">Try Again</button>`;
                }
            } catch (error) {
                // Server likely already restarted - this is expected
                console.log('Restart triggered, server restarting...');
                notification.innerHTML = `✅ Server restarting... Reloading page in 4 seconds...`;
                // Keep the auto-reload scheduled
            }
        }

        // ============================================================================
        // ADVANCED TAB (PROMPT EDITOR)
        // ============================================================================

        let defaultPrompt = `You are summarizing a YouTube video. Create a concise summary that:
1. Captures the main points in 2-3 paragraphs
2. Highlights what's valuable or interesting
3. Mentions any actionable takeaways
4. Indicates who would benefit from watching

Keep the tone conversational and focus on value.

Title: {title}
Duration: {duration}
Transcript: {transcript}`;

        async function loadPrompt() {
            try {
                const response = await fetch('/api/settings/prompt');
                if (!response.ok) throw new Error('Failed to load prompt');

                const data = await response.json();
                document.getElementById('promptEditor').value = data.prompt || defaultPrompt;

            } catch (error) {
                showAdvancedStatus('Failed to load prompt', true);
                console.error(error);
            }
        }

        async function savePrompt() {
            const prompt = document.getElementById('promptEditor').value.trim();

            if (!prompt) {
                showAdvancedStatus('Prompt cannot be empty', true);
                return;
            }

            if (prompt.length < 10) {
                showAdvancedStatus('Prompt is too short', true);
                return;
            }

            try {
                const response = await fetch('/api/settings/prompt', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ prompt })
                });

                if (!response.ok) {
                    const error = await response.json();
                    throw new Error(error.detail || 'Failed to save');
                }

                showAdvancedStatus('✅ Prompt saved successfully', false);

            } catch (error) {
                showAdvancedStatus(`❌ ${error.message}`, true);
                console.error(error);
            }
        }

        function resetPrompt() {
            if (confirm('Are you sure you want to reset the prompt to default?')) {
                document.getElementById('promptEditor').value = defaultPrompt;
                showAdvancedStatus('Prompt reset to default. Click Save to apply.', false);
            }
        }

        // Track all settings changes by section
        const trackableInputs = document.querySelectorAll('.trackable-input');
        trackableInputs.forEach(input => {
            const showIndicator = () => {
                const section = input.getAttribute('data-section');
                if (section === 'credentials') {
                    document.getElementById('unsaved-credentials').style.display = 'inline';
                } else if (section === 'app') {
                    document.getElementById('unsaved-app').style.display = 'inline';
                } else if (section === 'video') {
                    document.getElementById('unsaved-video').style.display = 'inline';
                }
            };

            // Track both input and change events (input for text fields, change for select/checkbox)
            input.addEventListener('input', showIndicator);
            input.addEventListener('change', showIndicator);
        });

        // Hide all unsaved indicators when settings are saved
        const originalSaveAllSettings = saveAllSettings;
        saveAllSettings = async function() {
            await originalSaveAllSettings();
            document.getElementById('unsaved-credentials').style.display = 'none';
            document.getElementById('unsaved-app').style.display = 'none';
            document.getElementById('unsaved-video').style.display = 'none';
        };

        // Keyboard shortcuts
        document.addEventListener('keydown', e => {
            if (e.key === 'Escape') {
                closeModal();
            }
        });

    </script>
</body>
</html>
    """


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
    Fetch and process the last X videos for a newly added channel
    X is defined by MAX_VIDEOS_PER_CHANNEL setting
    """
    try:
        # Get the MAX_VIDEOS_PER_CHANNEL setting
        config = config_manager.read_config()
        max_videos = int(config.get('settings', {}).get('MAX_VIDEOS_PER_CHANNEL', '5'))

        logger.info(f"Fetching last {max_videos} videos for new channel: {channel_id}")

        # Fetch videos from RSS feed
        feed_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
        feed = feedparser.parse(feed_url)

        if feed.bozo or not feed.entries:
            logger.warning(f"Could not fetch videos for channel: {channel_id}")
            return {
                "status": "error",
                "message": "Could not fetch videos from channel",
                "videos_fetched": 0
            }

        # Get video IDs from the feed (up to max_videos)
        video_ids = []
        skip_shorts = config.get('settings', {}).get('SKIP_SHORTS', 'true').lower() == 'true'

        for entry in feed.entries[:max_videos * 2]:  # Check extra to account for shorts
            # Skip YouTube Shorts if configured
            if skip_shorts and '/shorts/' in entry.link:
                continue

            video_ids.append({
                'id': entry.yt_videoid,
                'title': entry.title,
                'channel_name': config.get('channel_names', {}).get(channel_id, channel_id)
            })

            if len(video_ids) >= max_videos:
                break

        # Add videos to database as processed (so they won't be processed again by summarizer)
        # This just marks them as "seen" without actually processing them
        for video in video_ids:
            video_db.add_video(
                video_id=video['id'],
                channel_id=channel_id,
                title=video['title'],
                channel_name=video.get('channel_name'),
                duration_seconds=None,  # Unknown from RSS
                summary_length=None  # Not processed yet
            )

        logger.info(f"Marked {len(video_ids)} videos as processed for channel {channel_id}")

        return {
            "status": "success",
            "message": f"Fetched {len(video_ids)} videos",
            "videos_fetched": len(video_ids)
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
    Fetch channel name from YouTube RSS feed
    Accepts: channel ID (UCxxxx), @handle, or YouTube URLs
    """
    try:
        # Extract channel ID from various formats
        try:
            channel_id = extract_channel_id_from_url(channel_input)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

        # Fetch RSS feed
        feed_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
        feed = feedparser.parse(feed_url)

        # Check if feed is valid
        if feed.bozo or not feed.feed:
            raise HTTPException(status_code=404, detail="Channel not found")

        # Extract channel name from feed
        channel_name = feed.feed.get('title', '').replace(' - YouTube', '').strip()

        if not channel_name:
            raise HTTPException(status_code=404, detail="Could not extract channel name")

        logger.info(f"Fetched channel name: {channel_name} for {channel_id}")

        return {
            "channel_id": channel_id,
            "channel_name": channel_name
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching channel name: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch channel name")


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
        env_updates = {}
        config_updates = {}

        # Separate env vs config settings
        for key, value in data.settings.items():
            if key in settings_manager.env_schema:
                env_updates[key] = value
            elif key in ['SUMMARY_LENGTH', 'SKIP_SHORTS', 'MAX_VIDEOS_PER_CHANNEL']:
                config_updates[key] = value

        results = {"env": None, "config": None, "restart_required": False}

        # Update .env settings
        if env_updates:
            success, message, errors = settings_manager.update_multiple_settings(env_updates)
            if not success:
                raise HTTPException(status_code=400, detail={"message": message, "errors": errors})
            results["env"] = message
            results["restart_required"] = True
            logger.info(f"Updated .env settings: {list(env_updates.keys())}")

        # Update config.txt settings
        if config_updates:
            config = config_manager.read_config()
            current_settings = config.get('settings', {})
            current_settings.update(config_updates)

            # Write back to config (preserving channels and prompt)
            config_manager.config = config
            config_manager.config['settings'] = current_settings

            # We need to update the config.txt file manually
            # Read the file and update the [SETTINGS] section
            try:
                with open('config.txt', 'r', encoding='utf-8') as f:
                    lines = f.readlines()

                new_lines = []
                in_settings = False

                for line in lines:
                    stripped = line.strip()

                    if stripped == '[SETTINGS]':
                        in_settings = True
                        new_lines.append(line)
                        # Add comment
                        new_lines.append("# Maximum length of summary in tokens (affects cost)\n")
                        new_lines.append(f"SUMMARY_LENGTH={config_updates.get('SUMMARY_LENGTH', current_settings.get('SUMMARY_LENGTH', '500'))}\n")
                        new_lines.append("\n# Skip YouTube Shorts videos (true/false)\n")
                        new_lines.append(f"SKIP_SHORTS={config_updates.get('SKIP_SHORTS', current_settings.get('SKIP_SHORTS', 'true'))}\n")
                        new_lines.append("\n# Maximum videos to check per channel\n")
                        new_lines.append(f"MAX_VIDEOS_PER_CHANNEL={config_updates.get('MAX_VIDEOS_PER_CHANNEL', current_settings.get('MAX_VIDEOS_PER_CHANNEL', '5'))}\n")
                        continue

                    if in_settings:
                        # Skip old settings lines
                        if stripped.startswith('['):
                            in_settings = False
                            new_lines.append(line)
                        elif not stripped or stripped.startswith('#'):
                            # Skip comments and empty lines in settings section
                            pass
                        elif '=' not in stripped:
                            pass  # Skip malformed lines
                        else:
                            pass  # Skip old key=value lines (we already wrote them)
                    else:
                        new_lines.append(line)

                # Write back
                with open('config.txt', 'w', encoding='utf-8') as f:
                    f.writelines(new_lines)

                results["config"] = f"Updated {len(config_updates)} config settings"
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
        # Read current config
        with open('config.txt', 'r', encoding='utf-8') as f:
            lines = f.readlines()

        new_lines = []
        in_prompt = False
        prompt_written = False

        for line in lines:
            stripped = line.strip()

            if stripped == '[PROMPT]':
                in_prompt = True
                new_lines.append(line)
                # Write the new prompt
                new_lines.append(data.prompt)
                new_lines.append('\n\n')
                prompt_written = True
                continue

            if in_prompt:
                # Skip old prompt lines until next section
                if stripped.startswith('['):
                    in_prompt = False
                    new_lines.append(line)
                else:
                    pass  # Skip old prompt content
            else:
                new_lines.append(line)

        # Write back
        with open('config.txt', 'w', encoding='utf-8') as f:
            f.writelines(new_lines)

        logger.info("Updated prompt template")

        return {
            "status": "success",
            "message": "Prompt updated successfully",
            "restart_required": False
        }

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


@app.post("/api/settings/test")
async def test_credentials(data: CredentialTest):
    """Test API credentials using provided values or saved values from .env"""
    try:
        if data.credential_type == 'openai':
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


# ============================================================================
# IMPORT/EXPORT ENDPOINTS
# ============================================================================

@app.get("/api/export/feed")
async def export_feed(format: str = "json"):
    """
    Export Feed level data (channels + videos).

    Parameters:
    - format: 'json' or 'csv' (default: 'json')

    Returns:
    - FileResponse with downloadable export file
    """
    try:
        if format not in ("json", "csv"):
            raise HTTPException(
                status_code=400,
                detail="Invalid format parameter. Must be 'json' or 'csv'"
            )

        if format == "json":
            # Export to JSON
            data = export_manager.export_feed_json()
            filename = export_manager.generate_export_filename("feed_export", "json")

            # Convert to JSON string
            json_str = json.dumps(data, indent=2, ensure_ascii=False)

            # Return as downloadable file
            return StreamingResponse(
                io.BytesIO(json_str.encode('utf-8')),
                media_type="application/json",
                headers={
                    "Content-Disposition": f'attachment; filename="{filename}"'
                }
            )

        elif format == "csv":
            # Export to CSV
            csv_content = export_manager.export_videos_csv()
            filename = export_manager.generate_export_filename("videos", "csv")

            # Return as downloadable file
            return StreamingResponse(
                io.BytesIO(csv_content.encode('utf-8')),
                media_type="text/csv; charset=utf-8",
                headers={
                    "Content-Disposition": f'attachment; filename="{filename}"'
                }
            )

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
    - FileResponse with downloadable JSON backup file
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

        if import_result.success:
            logger.info(
                f"Import successful: {import_result.channels_added} channels, "
                f"{import_result.videos_added} videos, {import_result.settings_updated} settings"
            )

            return JSONResponse(
                status_code=200,
                content={
                    "success": True,
                    "channels_added": import_result.channels_added,
                    "videos_added": import_result.videos_added,
                    "settings_updated": import_result.settings_updated,
                    "errors": []
                }
            )
        else:
            logger.error(f"Import failed: {'; '.join(import_result.errors)}")

            return JSONResponse(
                status_code=200,
                content={
                    "success": False,
                    "channels_added": 0,
                    "videos_added": 0,
                    "settings_updated": 0,
                    "errors": import_result.errors
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


# ============================================================================
# APPLICATION ENTRY POINT
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    logger.info("Starting YouTube Summarizer Web UI (Modern Minimalist)")
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
