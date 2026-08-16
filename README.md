# Keymap Overlay

A small, frameless, always-on-top reference panel that shows your hotkeys in a
semi-transparent overlay. Useful for keeping a keymap visible on a second
monitor or in the empty space of an ultra-wide screen while gaming or working.

Built with Python 3 and PyQt6.

## Features

- Frameless, always-on-top window with a semi-transparent rounded background.
- Drag the window using the **move handle** in the top-left corner.
- **Lock / click-through mode** via the lock button in the top-right corner.
  When locked, clicks pass through the window (so the game/app behind it stays
  clickable) while the lock button itself remains usable to unlock.
- System tray icon to show/hide, lock/unlock, adjust opacity and quit.
- Adjustable background opacity, persisted in `data/settings.json`.
- Multiple characters/groups loaded from `data/keymap.json` (created from
  `data/keymap.example.json` on first run).
- Hot-reloads `data/keymap.json` automatically when the file is saved.
- Plugin system: import hotkeys from external sources (see [PLUGINS.md](PLUGINS.md)).
- Optional icons per hotkey (from `assets/icons/`).
- All colors, sizes and spacing live in `config/constants.py` for easy tweaking.

## Screenshot

<img src="docs/screenshot.png" alt="Keymap Overlay" width="320">

The panel shows the character dropdown (top), a group block with its hotkey
rows, the drag handle (top-left) and the lock button (top-right).

## Quick start

```bash
./run.sh
```

The first run creates a virtual environment and installs the dependencies
(PyQt6) automatically.

See [INSTALL.md](INSTALL.md) for detailed setup instructions (and
[INSTALL.tr.md](INSTALL.tr.md) for Turkish).

## How it works

The overlay reads its data from `data/keymap.json`. On first run this file is
created from the example at `data/keymap.example.json`:

```json
{
  "characters": [
    {
      "id": "char1",
      "name": "Character 1",
      "groups": [
        {
          "title": "Combat",
          "hotkeys": [
            { "key": "F1", "label": "Attack", "icon": "attack.png" },
            { "key": "F2", "label": "Defend", "icon": null }
          ]
        }
      ]
    }
  ]
}
```

- Each character has its own groups; groups are rendered as titled blocks.
- `icon` may be `null` (or point to a missing file) — the row then shows only
  the key badge and the label.
- Icons are looked up in `assets/icons/`.

## Project structure

```
.
├── main.py                 # entry point (tray, watcher)
├── plugin_loader.py        # plugin discovery
├── PLUGINS.md              # plugin authoring guide
├── run.sh                  # run the app (auto-creates the venv)
├── build.sh                # build a single-file executable
├── config/
│   └── constants.py        # all visual/size constants
├── data/
│   ├── keymap.example.json # example data (committed)
│   └── keymap.json         # your hotkey data (generated, gitignored)
├── assets/
│   └── icons/              # optional per-hotkey icons
├── plugins/                # user-provided importers (gitignored)
└── ui/
    ├── overlay_window.py   # frameless window, drag, lock, painting
    ├── group_widget.py     # one group block
    └── hotkey_row_widget.py# one hotkey row
```

## Plugins

Plugins let you generate the keymap from an external source (for example, a
game's profile files). Drop a plugin into `plugins/` and it appears in the
tray's **Import** menu. See [PLUGINS.md](PLUGINS.md) for the full API.

## Customizing

Edit `config/constants.py` to change the window size/position, colors, fonts,
spacing and icon size. Nothing is hardcoded elsewhere.

## Notes

- On Linux/Wayland the app forces the XWayland (xcb) backend so the
  always-on-top behavior works reliably. Click-through is implemented via the
  X11 `ShapeInput` extension.
- Tested on Fedora (KDE/Wayland). Should also work on other Linux desktop
  environments with an X11/XWayland session.
