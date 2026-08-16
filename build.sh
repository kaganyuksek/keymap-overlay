#!/usr/bin/env bash
# Build a single-file executable (PyInstaller).
# Output: dist/KeymapOverlay
# Note: keep the data/ and assets/ folders next to the executable.
set -e
cd "$(dirname "$0")"

if [ ! -d ".venv" ]; then
    ./run.sh --help >/dev/null 2>&1 || true
fi

.venv/bin/pip install pyinstaller >/dev/null

.venv/bin/pyinstaller \
    --noconfirm \
    --onefile \
    --windowed \
    --name KeymapOverlay \
    main.py

echo
echo "Built: dist/KeymapOverlay"
echo "Remember to copy data/ and assets/ next to the executable."
