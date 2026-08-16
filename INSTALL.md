# Installation

## Requirements

- Linux (X11 or Wayland with XWayland)
- Python 3 (3.9+)
- `python3-venv` (usually included, otherwise install with your package manager)

## Option A — Run with `run.sh` (recommended)

1. Clone the repository and enter it:

   ```bash
   git clone https://github.com/kaganyuksek/keymap-overlay.git
   cd keymap-overlay
   ```

2. Run the launcher:

   ```bash
   ./run.sh
   ```

   The script creates a `.venv` virtual environment and installs PyQt6 on the
   first run. Every later run just launches the app.

## Option B — Manual setup

1. Create and activate a virtual environment:

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

2. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

3. Run:

   ```bash
   python main.py
   ```

## Building a single-file executable

```bash
./build.sh
```

This produces `dist/KeymapOverlay` using PyInstaller. Keep the `data/` and
`assets/` folders next to the executable.

## Usage

- **Drag**: hold the move handle (top-left) to reposition the window.
- **Lock / click-through**: click the lock button (top-right). When locked,
  clicks pass through to the window behind; click the lock again (or use the
  tray menu) to unlock.
- **Tray icon**: right-click to show/hide, lock/unlock, change opacity, or quit.

Edit `data/keymap.json` to change the hotkeys — the overlay reloads it
automatically when the file is saved.
