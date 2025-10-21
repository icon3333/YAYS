#!/bin/bash
# YAYS - Yet Another YouTube Summarizer
# ======================================
# One-line installer for Docker deployment
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/icon3333/YAYS/main/install.sh | bash
#
# What this does:
# 1. Checks prerequisites (Docker, git)
# 2. Clones the repository to ~/YAYS
# 3. Instructions to start containers
#
# Default port: 8000
# To change: Edit docker-compose.yml before running docker-compose up

set -e  # Exit on error

# =============================================================================
# Configuration
# =============================================================================

REPO_URL="https://github.com/icon3333/YAYS.git"
PROJECT_NAME="YAYS"
INSTALL_DIR="$HOME/$PROJECT_NAME"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

# =============================================================================
# Utility Functions
# =============================================================================

print_header() {
    echo -e "\n${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${CYAN}  $1${NC}"
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}\n"
}

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
    echo -e "${BLUE}ℹ${NC} $1"
}

print_step() {
    echo -e "\n${BLUE}▶${NC} $1"
}

exit_with_error() {
    print_error "$1"
    exit 1
}

command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# =============================================================================
# Prerequisite Checks
# =============================================================================

check_prerequisites() {
    print_step "Checking prerequisites..."

    # Check Docker
    if ! command_exists docker; then
        exit_with_error "Docker is not installed. Please install Docker first:

        macOS:   brew install --cask docker
        Linux:   curl -fsSL https://get.docker.com | sh

        Visit: https://docs.docker.com/get-docker/"
    fi

    if ! docker ps >/dev/null 2>&1; then
        exit_with_error "Docker daemon is not running. Please start Docker first."
    fi

    print_success "Docker is installed and running"

    # Check Docker Compose
    if ! command_exists docker-compose && ! docker compose version >/dev/null 2>&1; then
        exit_with_error "Docker Compose is not installed. Please install it first."
    fi

    print_success "Docker Compose is available"

    # Check git
    if ! command_exists git; then
        exit_with_error "Git is not installed. Please install git first:

        macOS:   brew install git
        Linux:   sudo apt-get install git  (or yum/dnf on RHEL-based)"
    fi

    print_success "Git is installed"
}

# =============================================================================
# Installation
# =============================================================================

clone_repository() {
    print_step "Cloning repository..."

    if [ -d "$INSTALL_DIR" ]; then
        print_warning "Directory $INSTALL_DIR already exists - using it"

        # Try to update it if it's a git repo
        if [ -d "$INSTALL_DIR/.git" ]; then
            cd "$INSTALL_DIR" || exit_with_error "Failed to enter directory: $INSTALL_DIR"
            print_info "Pulling latest changes..."
            git pull origin main 2>/dev/null || print_warning "Could not update (might have local changes)"
            cd - > /dev/null
        fi

        print_success "Using existing repository at $INSTALL_DIR"
        return 0
    fi

    git clone "$REPO_URL" "$INSTALL_DIR" || exit_with_error "Failed to clone repository"

    print_success "Repository cloned to $INSTALL_DIR"
}

check_ready() {
    print_step "Setup complete"

    cd "$INSTALL_DIR" || exit_with_error "Failed to enter directory: $INSTALL_DIR"

    print_info "Ready to start"
}

# =============================================================================
# Final Messages
# =============================================================================

print_success_message() {
    echo ""
    print_header "Installation Complete!"

    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${GREEN}Next Steps:${NC}"
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo ""
    echo -e "${YELLOW}1. (Optional) Change port:${NC}"
    echo -e "   Edit ${BLUE}docker-compose.yml${NC} line 16"
    echo "   Change \"8000:8000\" to \"3000:8000\" (or your port)"
    echo ""
    echo -e "${YELLOW}2. Start containers:${NC}"
    echo -e "   ${BLUE}cd $INSTALL_DIR${NC}"
    echo -e "   ${BLUE}docker-compose up -d${NC}"
    echo ""
    echo -e "${YELLOW}3. Open web UI and configure:${NC}"
    echo "   http://localhost:8000 (or your custom port)"
    echo ""
    echo "   In Settings tab, add:"
    echo "   - OpenAI API key"
    echo "   - Target email (RSS reader like Inoreader, or your inbox)"
    echo "   - Gmail SMTP credentials"
    echo ""
    echo -e "${YELLOW}4. Add YouTube channels and start processing!${NC}"
    echo ""
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${GREEN}Useful Commands:${NC}"
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo ""
    echo "  View logs:           docker-compose logs -f"
    echo "  Restart:             docker-compose restart"
    echo "  Stop:                docker-compose stop"
    echo "  Process videos now:  docker exec youtube-summarizer python process_videos.py"
    echo ""
    echo -e "${YELLOW}Documentation:${NC} $INSTALL_DIR/README.md"
    echo ""
}

# =============================================================================
# Main
# =============================================================================

main() {
    print_header "YAYS - Yet Another YouTube Summarizer"

    check_prerequisites
    clone_repository
    check_ready
    print_success_message
}

# Run main function
main "$@"
