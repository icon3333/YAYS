#!/bin/bash
# YAYS Update Script - Pulls latest code and rebuilds containers

set -e  # Exit on error

echo "🔄 Updating YAYS to latest version..."
echo ""

# Backup critical configuration files before update
echo "💾 Backing up configuration..."
if [ -f .env ]; then
    cp .env .env.backup.update
    echo "   ✓ Backed up .env"
fi
if [ -f config.txt ]; then
    cp config.txt config.txt.backup.update
    echo "   ✓ Backed up config.txt"
fi

# Stop containers (preserve data volumes)
# IMPORTANT: Do NOT use -v flag here, as it can delete bind mount data
# including database (data/), config (config.txt), and .env settings
echo "📦 Stopping containers..."
docker compose down

# Discard local changes and pull latest
echo "⬇️  Pulling latest code from GitHub..."
git fetch origin
git reset --hard origin/main

# Show what version we're updating to
echo ""
echo "📌 Updated to:"
git log --oneline -3
echo ""

# Restore configuration files if they were overwritten by git reset
echo "♻️  Restoring configuration..."
if [ -f .env.backup.update ]; then
    if [ ! -f .env ] || [ "$(wc -c < .env)" -lt 100 ]; then
        # Restore if .env is missing or looks like the example template (small size)
        cp .env.backup.update .env
        echo "   ✓ Restored .env from backup"
    fi
    rm .env.backup.update
fi
if [ -f config.txt.backup.update ]; then
    if [ ! -f config.txt ] || [ "$(wc -c < config.txt)" -lt 200 ]; then
        # Restore if config.txt is missing or looks like default (small size)
        cp config.txt.backup.update config.txt
        echo "   ✓ Restored config.txt from backup"
    fi
    rm config.txt.backup.update
fi

# Ensure .env exists (create from example if needed)
if [ ! -f .env ]; then
    if [ -f .env.example ]; then
        cp .env.example .env
        echo "⚠️  Created .env from .env.example - Please configure your settings in the Web UI"
    else
        echo "❌ Warning: .env.example not found. You'll need to configure settings in the Web UI."
    fi
fi

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
