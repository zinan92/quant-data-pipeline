#!/bin/bash
set -e

cd /Users/wendy/work/trading-co/ashare

# Install Python dependencies (both prod and dev)
if [ -d ".venv" ]; then
    .venv/bin/pip install -q -r requirements.txt -r requirements-dev.txt 2>/dev/null || true
fi

# Ensure CANDLE_LOOKBACK is set in .env
if ! grep -q "CANDLE_LOOKBACK" .env 2>/dev/null; then
    echo "CANDLE_LOOKBACK=1250" >> .env
fi

# Verify services are running (don't start them — they should already be running)
echo "Checking services..."
curl -sf http://localhost:8000/api/status > /dev/null 2>&1 && echo "Backend (8000): OK" || echo "Backend (8000): NOT RUNNING"
curl -sf http://localhost:5173 > /dev/null 2>&1 && echo "Frontend (5173): OK" || echo "Frontend (5173): NOT RUNNING"
