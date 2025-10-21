# Multi-stage Dockerfile for YouTube Summarizer (Refactored)
# ==========================================================
# Optimized for small image size and security

# Stage 1: Base image with dependencies
FROM python:3.11-slim as base

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN groupadd -r appuser && useradd -r -g appuser -u 1000 appuser

# Set working directory
WORKDIR /app

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Stage 2: Summarizer service
FROM base as summarizer

# Copy application code
COPY src/ ./src/
COPY process_videos.py .

# Create necessary directories with correct permissions
RUN mkdir -p /app/data /app/logs && \
    chown -R appuser:appuser /app

# Switch to non-root user
USER appuser

# Health check
HEALTHCHECK --interval=5m --timeout=10s --start-period=30s --retries=3 \
    CMD python -c "import sys; sys.exit(0)"

# Run summarizer in a loop with configurable interval
CMD ["sh", "-c", "while true; do python -u process_videos.py; sleep ${CHECK_INTERVAL_SECONDS:-14400}; done"]

# Stage 3: Web service
FROM base as web

# Copy application code
COPY src/ ./src/
COPY main.py .

# Create necessary directories with correct permissions
RUN mkdir -p /app/logs && \
    chown -R appuser:appuser /app

# Switch to non-root user
USER appuser

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Run web server
CMD ["python", "main.py"]
