"""
All visual/dimensional constants are collected here.

Tweak this file to customize the overlay appearance to your liking. No
size/color value is hardcoded anywhere in the code; everything is read
from this module.
"""

import sys
from pathlib import Path

# --- Paths ----------------------------------------------------------------
# Project root: config/constants.py -> config/ -> project root.
# When bundled with PyInstaller (frozen), writable data (keymap/settings) is
# stored next to the executable, while read-only bundled resources (the
# example keymap) are unpacked into the temp dir exposed via sys._MEIPASS.
if getattr(sys, "frozen", False):
    PROJECT_ROOT = Path(sys.executable).resolve().parent
    BUNDLE_DIR = Path(getattr(sys, "_MEIPASS", PROJECT_ROOT))
else:
    PROJECT_ROOT = Path(__file__).resolve().parent.parent
    BUNDLE_DIR = PROJECT_ROOT
DATA_DIR = PROJECT_ROOT / "data"
KEYMAP_PATH = DATA_DIR / "keymap.json"
KEYMAP_EXAMPLE_PATH = BUNDLE_DIR / "data" / "keymap.example.json"
SETTINGS_PATH = DATA_DIR / "settings.json"
ICONS_DIR = PROJECT_ROOT / "assets" / "icons"
PLUGINS_DIR = PROJECT_ROOT / "plugins"

# --- Window ---------------------------------------------------------------
WINDOW_WIDTH = 320
WINDOW_HEIGHT = 700
WINDOW_POS_X = 1920      # start of the empty area on an ultra-wide monitor
WINDOW_POS_Y = 100

# --- Appearance -----------------------------------------------------------
BACKGROUND_COLOR = (20, 20, 20)
BACKGROUND_ALPHA = 230   # 0-255, ~90% opacity
CORNER_RADIUS = 10

# --- Typography -----------------------------------------------------------
FONT_FAMILY = "Sans"
FONT_SIZE_TITLE = 13
FONT_SIZE_GROUP_HEADER = 12
FONT_SIZE_HOTKEY = 11
FONT_SIZE_KEY = 11
TEXT_COLOR = (240, 240, 240)
GROUP_HEADER_COLOR = (180, 180, 255)

# --- Key badge (the F1/F2 style shortcut label in a hotkey row) -----------
KEY_BADGE_BG = (45, 45, 55)
KEY_BADGE_TEXT_COLOR = (255, 210, 120)

# --- Icon -----------------------------------------------------------------
ICON_SIZE = 24
ICON_TEXT_SPACING = 8

# --- Row / group spacing --------------------------------------------------
ROW_SPACING = 6
GROUP_SPACING = 16
PANEL_PADDING = 12

# --- Lock button ----------------------------------------------------------
LOCK_BUTTON_SIZE = 22
LOCKED_COLOR = (240, 240, 240)
UNLOCKED_COLOR = (120, 220, 120)

# --- Drag handle ----------------------------------------------------------
DRAG_HANDLE_SIZE = 22
DRAG_HANDLE_COLOR = (120, 120, 140)

# --- Resize handle --------------------------------------------------------
# Vertical grab strip on the right edge shown while the overlay is unlocked.
RESIZE_HANDLE_WIDTH = 8

# --- Group column flow ----------------------------------------------------
# As the overlay is widened, hotkey rows re-flow into extra columns instead of
# staying in one long column. A column never holds fewer than this many rows,
# so rows split 2-by-2 (e.g. 5 rows -> columns of 2 + 2 + 1) rather than 1-by-1.
MIN_ROWS_PER_COLUMN = 2
# Minimum width of a hotkey-row column. Used as a floor for the measured row
# width and to estimate how many columns fit across the window at a given width.
ROW_COLUMN_WIDTH = 170
# Horizontal gap between the row columns.
COLUMN_SPACING = 24

# --- Multi-window ---------------------------------------------------------
EMPTY_WINDOW_MIN_ROWS = 3
ROW_HEIGHT_ESTIMATE = 30
ROW_MIME_TYPE = "application/x-keymap-row"
FOCUS_HIDE_DELAY_MS = 800

# --- System tray ----------------------------------------------------------
APP_TITLE = "Keymap Overlay"
TRAY_ICON_SIZE = 32
TRAY_ICON_BAR_COLOR = (180, 180, 255)


def rgb(color: tuple) -> str:
    """Convert an (r, g, b) tuple to a Qt stylesheet 'rgb(r,g,b)' string."""
    return "rgb({},{},{})".format(*color)
