#!/bin/bash
# Startup script for summarizer service
# Reads CHECK_INTERVAL_HOURS from database and runs processing loop
set -e

echo "🚀 Starting YAYS Summarizer Service"
echo "=================================="

# Function to read CHECK_INTERVAL_HOURS from database
get_check_interval_seconds() {
    python3 -c "
import sys
sys.path.insert(0, '/app/src')
try:
    from managers.settings_manager import SettingsManager
    settings_mgr = SettingsManager(db_path='/app/data/videos.db')
    interval_hours = settings_mgr.get_setting('CHECK_INTERVAL_HOURS')

    if interval_hours and interval_hours.isdigit():
        interval_seconds = int(interval_hours) * 3600
        print(interval_seconds)
    else:
        # Default to 4 hours if not set
        print(14400)
except Exception as e:
    print(f'Error reading interval from database: {e}', file=sys.stderr)
    # Default to 4 hours on error
    print(14400)
" 2>/dev/null || echo "14400"
}

# Main loop
while true; do
    # Read interval from database before each run (allows dynamic updates)
    INTERVAL_SECONDS=$(get_check_interval_seconds)
    INTERVAL_HOURS=$(echo "scale=2; $INTERVAL_SECONDS / 3600" | bc 2>/dev/null || echo "4")

    echo ""
    echo "📅 $(date '+%Y-%m-%d %H:%M:%S')"
    echo "⏰ Check interval: ${INTERVAL_HOURS} hours (${INTERVAL_SECONDS} seconds)"
    echo ""

    # Run the video processor
    python -u process_videos.py
    EXIT_CODE=$?

    if [ $EXIT_CODE -ne 0 ]; then
        echo "⚠️  Process exited with code $EXIT_CODE"
    fi

    echo ""
    echo "⏳ Sleeping for ${INTERVAL_HOURS} hours..."
    echo "Next run at: $(date -d "+${INTERVAL_SECONDS} seconds" '+%Y-%m-%d %H:%M:%S' 2>/dev/null || date -v +${INTERVAL_SECONDS}S '+%Y-%m-%d %H:%M:%S' 2>/dev/null || echo 'N/A')"

    # Sleep for the configured interval
    sleep "$INTERVAL_SECONDS"
done
