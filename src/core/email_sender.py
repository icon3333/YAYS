#!/usr/bin/env python3
"""
Email Delivery
Handles SMTP email sending
"""

import smtplib
import logging
from time import sleep
from typing import Dict
from email.mime.text import MIMEText
from email.header import Header


logger = logging.getLogger(__name__)


class EmailSender:
    """SMTP email sender"""

    RETRY_ATTEMPTS = 3
    RETRY_DELAY_BASE = 5  # seconds

    def __init__(self, smtp_user: str, smtp_pass: str, target_email: str):
        """Initialize with SMTP credentials"""
        self.smtp_user = smtp_user
        self.smtp_pass = smtp_pass
        self.target_email = target_email

    def send_email(self, video: Dict, summary: str, channel_name: str = None) -> bool:
        """
        Send summary via email with retry logic
        Returns True on success
        """
        # Build metadata header
        metadata_lines = []

        if channel_name:
            metadata_lines.append(f"📺 Channel: {channel_name}")

        if video.get('duration_string'):
            metadata_lines.append(f"⏱️  Duration: {video['duration_string']}")

        if video.get('view_count') and video['view_count'] > 0:
            view_count = video['view_count']
            if view_count < 1000:
                view_str = f"{view_count:,} views"
            elif view_count < 1_000_000:
                view_str = f"{view_count/1000:.1f}K views"
            else:
                view_str = f"{view_count/1_000_000:.1f}M views"
            metadata_lines.append(f"👁️  Views: {view_str}")

        if video.get('upload_date'):
            metadata_lines.append(f"📅 Uploaded: {video['upload_date']}")

        # Construct video URL from ID
        video_url = video.get('url', f"https://youtube.com/watch?v={video['id']}")

        # Compose email body
        if metadata_lines:
            metadata_section = "\n".join(metadata_lines)
            email_body = f"{metadata_section}\n\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n{summary}\n\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n🎬 Watch video: {video_url}"
        else:
            email_body = f"{summary}\n\n---\n🎬 Watch video: {video_url}"

        msg = MIMEText(email_body, 'plain', 'utf-8')
        # Properly encode subject line with UTF-8
        subject = f"YAYS: {video['title'][:60]}"
        msg['Subject'] = Header(subject, 'utf-8')
        msg['From'] = self.smtp_user
        msg['To'] = self.target_email

        # Try sending with retry
        for attempt in range(self.RETRY_ATTEMPTS):
            try:
                # Create SMTP connection with UTF-8 support
                with smtplib.SMTP('smtp.gmail.com', 587, timeout=30) as server:
                    server.ehlo()
                    server.starttls()
                    server.ehlo()
                    server.login(self.smtp_user, self.smtp_pass)
                    # Use send_message which properly handles UTF-8
                    server.send_message(msg)

                logger.debug(f"Email sent successfully (attempt {attempt + 1})")
                return True

            except smtplib.SMTPAuthenticationError as e:
                logger.error("SMTP authentication failed!")
                logger.error("Please check SMTP_USER and SMTP_PASS in .env")
                logger.error("You may need to generate a new app password")
                return False  # Don't retry auth errors

            except smtplib.SMTPException as e:
                logger.warning(f"SMTP error (attempt {attempt + 1}/{self.RETRY_ATTEMPTS}): {e}")
                if attempt < self.RETRY_ATTEMPTS - 1:
                    delay = self.RETRY_DELAY_BASE
                    logger.info(f"Retrying in {delay}s...")
                    sleep(delay)
                else:
                    logger.error("Max retries reached for SMTP")
                    return False

            except Exception as e:
                logger.error(f"Unexpected email error: {e}")
                return False

        return False
