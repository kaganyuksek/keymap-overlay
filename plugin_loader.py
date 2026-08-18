"""
Plugin discovery and loading.

Plugins live under plugins/ and come in two forms:

- Single file:  plugins/<name>.py
- Folder:       plugins/<name>/importer.py   (entry point; sibling modules can
                be imported from the same folder)

A plugin must expose:

    PLUGIN_ID        str   - unique identifier
    PLUGIN_NAME      str   - display name shown in the tray menu
    import_keymap()  -> dict  - returns {"profiles": [...]}

Optional:

    AUTO_IMPORT      bool  - if True, import_keymap() runs automatically at startup
    discover()       -> list - optional helper to list available sources
"""

import importlib.util
import sys
from pathlib import Path

from config.constants import PLUGINS_DIR

_PREFIX = "_keymap_overlay_plugin_"


def _load_module_from_file(path: Path, module_name: str, extra_path: Path | None = None):
    """Load a module from a file; return None on any failure."""
    if extra_path is not None and str(extra_path) not in sys.path:
        sys.path.insert(0, str(extra_path))
    try:
        spec = importlib.util.spec_from_file_location(module_name, path)
        if spec is None or spec.loader is None:
            return None
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        return module
    except Exception:
        sys.modules.pop(module_name, None)
        return None


def _is_valid(module) -> bool:
    return (
        isinstance(getattr(module, "PLUGIN_ID", None), str)
        and isinstance(getattr(module, "PLUGIN_NAME", None), str)
        and callable(getattr(module, "import_keymap", None))
    )


def discover_plugins() -> list:
    """Return a list of valid plugin modules found under plugins/."""
    plugins = []
    if not PLUGINS_DIR.is_dir():
        return plugins

    # Single-file plugins
    for path in sorted(PLUGINS_DIR.glob("*.py")):
        if path.stem.startswith("_"):
            continue
        module = _load_module_from_file(path, _PREFIX + path.stem)
        if module is not None and _is_valid(module):
            plugins.append(module)

    # Folder plugins
    for importer_path in sorted(PLUGINS_DIR.glob("*/importer.py")):
        folder = importer_path.parent
        module = _load_module_from_file(
            importer_path,
            _PREFIX + folder.name + "_importer",
            extra_path=folder,
        )
        if module is not None and _is_valid(module):
            plugins.append(module)

    return plugins
