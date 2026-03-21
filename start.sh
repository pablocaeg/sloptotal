#!/usr/bin/env bash
# SlopTotal — One-command local server launcher
# Usage: ./start.sh
#
# The server auto-detects your hardware (CPU cores, RAM, GPU)
# and configures itself for optimal performance.
#
# Override any setting with environment variables:
#   SLOPTOTAL_PROFILE=lite ./start.sh        # Force lite mode (low RAM)
#   SLOPTOTAL_DEVICE=cpu ./start.sh          # Force CPU even if GPU available
#   SLOPTOTAL_TORCH_THREADS=4 ./start.sh     # Override thread count

set -e

PORT="${SLOPTOTAL_PORT:-8000}"
HOST="${SLOPTOTAL_HOST:-0.0.0.0}"

echo ""
echo "  Starting SlopTotal..."
echo "  Models will be downloaded on first run (~2GB)."
echo ""

# Detect if running inside venv; if not, try to activate one
if [ -z "$VIRTUAL_ENV" ]; then
    if [ -f "venv/bin/activate" ]; then
        source venv/bin/activate
    elif [ -f ".venv/bin/activate" ]; then
        source .venv/bin/activate
    fi
fi

# Check Python is available
if ! command -v python &> /dev/null; then
    echo "Error: Python not found. Install Python 3.10+ and try again."
    exit 1
fi

# Install dependencies if needed
if ! python -c "import fastapi" 2>/dev/null; then
    echo "  Installing dependencies..."
    pip install -r requirements.txt
fi

exec python -m uvicorn app.main:app --host "$HOST" --port "$PORT"
