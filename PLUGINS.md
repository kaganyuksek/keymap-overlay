# Writing a Plugin

Plugins let you import hotkey data from an external source (for example, a
game's profile files) and turn it into the overlay's `data/keymap.json`.

## Layout

Drop your plugin into the `plugins/` directory. Two forms are supported:

- **Single file**: `plugins/<name>.py`
- **Folder**: `plugins/<name>/importer.py` (the `importer.py` is the entry
  point; helper modules in the same folder can be imported with absolute
  imports)

## Interface

A plugin module must define:

```python
PLUGIN_ID = "my_game"
PLUGIN_NAME = "My Game"

def import_keymap():
    return {"profiles": [...]}
```

Optional:

- `AUTO_IMPORT = True` — run `import_keymap()` automatically at startup.
- `discover()` — helper to list available sources. The core does not call it,
  but it is handy if you want to show your own selection dialog.

`import_keymap()` must return the same structure as `data/keymap.json`:

```json
{
  "profiles": [
    {
      "id": "char1",
      "name": "Profile 1",
      "groups": [
        { "title": "Combat", "hotkeys": [ { "key": "F1", "label": "Attack", "icon": null } ] }
      ]
    }
  ]
}
```

## Example

```python
# plugins/example/importer.py
import json
from pathlib import Path

PLUGIN_ID = "example"
PLUGIN_NAME = "Example Importer"

def import_keymap():
    profiles = []
    for profile in sorted(Path.home().glob(".example/*.json")):
        data = json.loads(profile.read_text())
        groups = [
            {
                "title": title,
                "hotkeys": [{"key": key, "label": label, "icon": None}
                            for key, label in items.items()],
            }
            for title, items in data["groups"].items()
        ]
        profiles.append({
            "id": data["id"],
            "name": data["name"],
            "groups": groups,
        })
    return {"profiles": profiles}
```

## Notes

- Plugins may use PyQt6 to show their own dialogs (for example, to pick which
  profiles to import). The app runs plugins on the GUI thread, so this works
  out of the box.
- The overlay watches `data/keymap.json` and reloads it automatically, so a
  plugin only needs to return the data — the app writes the file.
- `plugins/` is gitignored; keep your plugins out of version control.
