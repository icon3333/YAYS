#!/bin/bash
# YAYS Update Script - Pulls latest code and rebuilds containers

set -e  # Exit on error

echo "🔄 Updating YAYS to latest version..."
echo ""

# Stop containers
echo "📦 Stopping containers..."
docker compose down

# Discard local changes and pull latest
echo "⬇️  Pulling latest code from GitHub..."
git fetch origin
git reset --hard origin/main

# Rebuild without cache (ensures all dependencies are fresh)
echo "🔨 Rebuilding containers (this takes ~60 seconds)..."
docker compose build --no-cache

# Start containers
echo "🚀 Starting containers..."
docker compose up -d

# Wait for health check
echo "⏳ Waiting for services to be healthy..."
sleep 5

# Show status
echo ""
echo "✅ Update complete!"
echo ""
docker compose ps
echo ""
echo "📊 View logs: docker compose logs -f"
echo "🌐 Web UI: http://localhost:8015"
echo ""
