#!/usr/bin/env python3
"""
AI Summarization using OpenAI GPT
Handles AI-powered video summarization
"""

import os
import logging
from time import sleep
from typing import Optional, Dict

import openai


logger = logging.getLogger(__name__)


class AISummarizer:
    """AI-powered video summarizer using OpenAI GPT"""

    # Constants
    MAX_TRANSCRIPT_CHARS = 15000  # ~3750 tokens
    RETRY_ATTEMPTS = 3
    RETRY_DELAY_BASE = 5  # Exponential backoff base (seconds)

    def __init__(self, api_key: str, model: Optional[str] = None):
        """Initialize with OpenAI API key and optional model selection"""
        self.api_key = api_key
        self.model = model or os.getenv('OPENAI_MODEL', 'gpt-4o-mini')
        try:
            self.client = openai.OpenAI(api_key=api_key)
            logger.info(f"OpenAI API client initialized with model: {self.model}")
        except Exception as e:
            logger.error(f"Failed to initialize OpenAI client: {e}")
            raise

    def summarize_with_retry(
        self,
        video: Dict,
        transcript: str,
        duration: str,
        prompt_template: str,
        max_tokens: Optional[int] = 500
    ) -> Optional[str]:
        """
        Generate AI summary with retry logic
        Returns summary text or None
        """
        # Truncate long transcripts
        truncated = False
        if len(transcript) > self.MAX_TRANSCRIPT_CHARS:
            transcript = transcript[:self.MAX_TRANSCRIPT_CHARS]
            truncated = True
            logger.debug(f"Truncated transcript to {self.MAX_TRANSCRIPT_CHARS} chars")

        # Format prompt
        try:
            prompt = prompt_template.format(
                title=video['title'],
                duration=duration or 'Unknown',
                transcript=transcript
            )
            if truncated:
                prompt += "\n\n[Note: Transcript was truncated due to length]"
        except KeyError as e:
            logger.warning(f"Prompt template missing variable: {e}, using fallback")
            prompt = f"Summarize this YouTube video:\n\nTitle: {video['title']}\nDuration: {duration}\n\nTranscript: {transcript}"

        # Get summary with retry
        for attempt in range(self.RETRY_ATTEMPTS):
            try:
                # Build API call parameters
                api_params = {
                    "model": self.model,
                    "temperature": 0.3,
                    "messages": [{"role": "user", "content": prompt}]
                }

                # Only add max_tokens if it's set
                if max_tokens is not None:
                    api_params["max_tokens"] = max_tokens

                response = self.client.chat.completions.create(**api_params)

                summary = response.choices[0].message.content
                logger.debug(f"API call successful (attempt {attempt + 1})")
                return summary

            except openai.RateLimitError as e:
                logger.warning(f"Rate limit hit (attempt {attempt + 1}/{self.RETRY_ATTEMPTS})")
                if attempt < self.RETRY_ATTEMPTS - 1:
                    delay = self.RETRY_DELAY_BASE * (2 ** attempt)
                    logger.info(f"Retrying in {delay}s...")
                    sleep(delay)
                else:
                    logger.error("Max retries reached for rate limit")
                    return None

            except openai.AuthenticationError as e:
                logger.error(f"Authentication error: Invalid OpenAI API key")
                return None

            except openai.APIError as e:
                logger.error(f"API error (attempt {attempt + 1}/{self.RETRY_ATTEMPTS}): {e}")
                if attempt < self.RETRY_ATTEMPTS - 1:
                    delay = self.RETRY_DELAY_BASE * (2 ** attempt)
                    logger.info(f"Retrying in {delay}s...")
                    sleep(delay)
                else:
                    logger.error("Max retries reached for API error")
                    return None

            except Exception as e:
                logger.error(f"Unexpected error during API call: {e}")
                return None

        return None
