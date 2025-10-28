#!/bin/bash
# YAYS Update Script - Convenience wrapper for install.sh
#
# This script simply calls install.sh, which automatically detects
# existing installations and performs updates. Keeping this script
# for backward compatibility and semantic clarity.

set -e  # Exit on error

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Call install.sh which handles both fresh installs and updates
exec "$SCRIPT_DIR/install.sh" "$@"
