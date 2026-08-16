#!/usr/bin/env bash
# Keymap Overlay launcher.
# Creates the virtual environment (.venv) on first run, then starts the app.
# Usage:  ./run.sh
set -e
cd "$(dirname "$0")"

if [ ! -d ".venv" ]; then
    echo "First run: installing dependencies (done only once)..."
    python3 -m venv .venv
    .venv/bin/pip install --upgrade pip >/dev/null
    .venv/bin/pip install -r requirements.txt
fi

exec .venv/bin/python main.py "$@"
