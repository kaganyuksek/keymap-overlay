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
    --add-data "data/keymap.example.json:data" \
    main.py

echo
echo "Built: dist/KeymapOverlay"
echo "On first run it creates data/ (keymap.json, settings.json) next to the executable."
