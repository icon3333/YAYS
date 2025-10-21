#!/bin/bash
# Install systemd service for YouTube Summarizer
# ===============================================
# This script automates the installation of the systemd service
# for automatic startup on boot.

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

print_success() {
    echo -e "${GREEN}✓${NC} $1"
}

print_error() {
    echo -e "${RED}✗${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}⚠${NC} $1"
}

print_info() {
    echo -e "${YELLOW}ℹ${NC} $1"
}

# Check if running with sudo
if [ "$EUID" -eq 0 ]; then
    print_error "Do not run this script with sudo. It will ask for sudo when needed."
    exit 1
fi

# Check if service file exists
if [ ! -f "youtube-summarizer.service" ]; then
    print_error "youtube-summarizer.service file not found!"
    print_info "Make sure you're in the youtube-summarizer directory"
    exit 1
fi

# Get current username
USERNAME=$(whoami)
PROJECT_DIR=$(pwd)

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  YouTube Summarizer - Systemd Service Installation"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
print_info "User:        $USERNAME"
print_info "Project dir: $PROJECT_DIR"
echo ""

# Create temporary service file with correct paths
TEMP_SERVICE=$(mktemp)
sed "s|YOUR_USERNAME|$USERNAME|g" youtube-summarizer.service > "$TEMP_SERVICE"
sed -i'.bak' "s|WorkingDirectory=/home/$USERNAME/youtube-summarizer|WorkingDirectory=$PROJECT_DIR|g" "$TEMP_SERVICE"
rm -f "$TEMP_SERVICE.bak"

# Check if docker-compose exists
if ! command -v docker-compose &> /dev/null; then
    print_error "docker-compose not found in PATH"
    print_info "Checking for 'docker compose' plugin..."
    if docker compose version &> /dev/null; then
        print_success "Found 'docker compose' plugin"
        # Update service file to use 'docker compose' instead
        sed -i'.bak' 's|/usr/bin/docker-compose|/usr/bin/docker compose|g' "$TEMP_SERVICE"
        rm -f "$TEMP_SERVICE.bak"
    else
        print_error "Neither docker-compose nor docker compose plugin found"
        exit 1
    fi
fi

# Install service file
print_info "Installing service file to /etc/systemd/system/..."
sudo cp "$TEMP_SERVICE" /etc/systemd/system/youtube-summarizer.service
rm "$TEMP_SERVICE"
print_success "Service file installed"

# Reload systemd
print_info "Reloading systemd daemon..."
sudo systemctl daemon-reload
print_success "Systemd reloaded"

# Enable service
print_info "Enabling service for auto-start on boot..."
sudo systemctl enable youtube-summarizer
print_success "Service enabled"

# Ask if user wants to start now
echo ""
read -p "Do you want to start the service now? (y/N): " -n 1 -r
echo ""
if [[ $REPLY =~ ^[Yy]$ ]]; then
    print_info "Starting service..."
    sudo systemctl start youtube-summarizer
    sleep 2

    # Check status
    if sudo systemctl is-active --quiet youtube-summarizer; then
        print_success "Service started successfully!"
    else
        print_error "Service failed to start"
        print_info "Checking status..."
        sudo systemctl status youtube-summarizer --no-pager
        exit 1
    fi
else
    print_info "Service not started. You can start it later with:"
    echo "  sudo systemctl start youtube-summarizer"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Installation Complete! 🎉"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "Useful commands:"
echo "  Status:   sudo systemctl status youtube-summarizer"
echo "  Start:    sudo systemctl start youtube-summarizer"
echo "  Stop:     sudo systemctl stop youtube-summarizer"
echo "  Restart:  sudo systemctl restart youtube-summarizer"
echo "  Logs:     sudo journalctl -u youtube-summarizer -f"
echo "  Disable:  sudo systemctl disable youtube-summarizer"
echo ""
echo "The service will now start automatically on boot!"
echo ""
