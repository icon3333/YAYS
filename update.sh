#!/bin/bash
# YAYS Update Script - Pulls latest code and rebuilds containers

set -e  # Exit on error

echo "🔄 Updating YAYS to latest version..."
echo ""

# Stop containers and remove volumes
echo "📦 Stopping containers..."
docker compose down -v

# Discard local changes and pull latest
echo "⬇️  Pulling latest code from GitHub..."
git fetch origin
git reset --hard origin/main

# Show what version we're updating to
echo ""
echo "📌 Updated to:"
git log --oneline -3
echo ""

# Rebuild without cache and pull latest base images
echo "🔨 Rebuilding containers (this takes ~60 seconds)..."
docker compose build --no-cache --pull

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
