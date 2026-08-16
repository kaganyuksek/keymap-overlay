# Installation

## Requirements

- Python 3 (3.9+)
- Linux: X11 or Wayland with XWayland (and `python3-venv`, usually included)
- Windows: Python 3 from [python.org](https://www.python.org/downloads/) with the
  "Add Python to PATH" option ticked

## Linux

### Option A — Run with `run.sh` (recommended)

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

### Option B — Manual setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

## Windows

1. Install Python 3 from [python.org](https://www.python.org/downloads/) and
   tick **Add Python to PATH**.
2. Open a terminal (PowerShell or Command Prompt) in the project folder.
3. Create and activate a virtual environment:

   ```powershell
   py -m venv .venv
   .venv\Scripts\activate
   ```

4. Install dependencies and run:

   ```powershell
   pip install -r requirements.txt
   python main.py
   ```

## Building a single-file executable

Linux:

```bash
./build.sh
```

Windows:

```powershell
pip install pyinstaller
pyinstaller --noconfirm --onefile --windowed --name KeymapOverlay main.py
```

The executable is created in `dist/`. Keep the `data/` and `assets/` folders
next to the executable.

## Usage

- **Drag**: hold the move handle (top-left) to reposition the window.
- **Lock / click-through**: click the lock button (top-right). When locked,
  clicks pass through to the window behind; click the lock again (or use the
  tray menu) to unlock.
- **Tray icon**: right-click to show/hide, lock/unlock, change opacity, or quit.

Edit `data/keymap.json` to change the hotkeys — the overlay reloads it
automatically when the file is saved. On first run the file is created from
`data/keymap.example.json`.
