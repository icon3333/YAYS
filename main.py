#!/usr/bin/env python3
"""
Main Entry Point for Web Application
Starts the FastAPI web server
"""

import uvicorn
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

if __name__ == "__main__":
    uvicorn.run(
        "src.web.app:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
        log_level="info"
    )
