#!/bin/bash
# ashare API watchdog — checks health, restarts if down
# Usage: called by OpenClaw cron every 5 minutes

set -euo pipefail

LOG="/Users/wendy/ashare/logs/watchdog.log"
API_URL="http://127.0.0.1:8000/api/status"
ASHARE_DIR="/Users/wendy/ashare"
VENV_PYTHON="$ASHARE_DIR/.venv/bin/python"

log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') | $1" >> "$LOG"
}

# Check if API responds within 30 seconds (was 10s, caused false kills)
if curl -sf --max-time 30 "$API_URL" > /dev/null 2>&1; then
    # Healthy — log only every hour (minute 0) to reduce noise
    if [ "$(date +%M)" -lt 5 ]; then
        log "OK — API healthy"
    fi
    exit 0
fi

log "WARN — API not responding, attempting restart"

# Kill existing uvicorn if any
pkill -f "uvicorn web.app:app" 2>/dev/null || true
sleep 2

# Restart
cd "$ASHARE_DIR"
nohup "$VENV_PYTHON" -m uvicorn web.app:app \
    --host 127.0.0.1 --port 8000 --workers 1 \
    >> logs/backend.log 2>&1 &

NEW_PID=$!
sleep 4

if curl -sf --max-time 10 "$API_URL" > /dev/null 2>&1; then
    log "OK — API restarted successfully (PID=$NEW_PID)"
else
    log "ERROR — API failed to restart (PID=$NEW_PID)"
    exit 1
fi
