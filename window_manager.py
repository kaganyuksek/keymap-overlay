"""
Window manager for the overlay.

Manages multiple overlay windows, distributes hotkey rows among them and
persists the layout. Lock state and opacity are global across all windows.
"""

import re

from PyQt6.QtCore import QObject, QTimer, pyqtSignal
from PyQt6.QtGui import QGuiApplication

import window_detector
from config.constants import FOCUS_HIDE_DELAY_MS, WINDOW_POS_X, WINDOW_POS_Y
from ui.overlay_window import OverlayWindow


class WindowManager(QObject):
    lock_changed = pyqtSignal(bool)

    def __init__(self, keymap: dict, settings: dict, save_callback=None) -> None:
        super().__init__()
        self.keymap = keymap
        self.profiles = keymap.get("profiles", [])
        self.settings = settings
        self.save_callback = save_callback
        self.layout = settings.get("window_layout", {})
        self.windows = []
        self.current_index = self._find_profile_index(
            settings.get("selected_profile") or settings.get("selected_character")
        )
        self._locked = False
        self._opacity = int(settings.get("opacity_percent", 90))
        self._master_visible = True
        self.patterns = set(settings.get("active_windows", []))
        self.custom_rules = settings.get("custom_rules", [])
        self._open_titles = set()
        self._foreground_id = window_detector.foreground_id()
        self._foreground_title = window_detector.foreground_title()
        self._refresh_open_titles()

        # Poll the foreground window to show/hide the overlay when a checked
        # application is focused.
        self._poll_timer = QTimer(self)
        self._poll_timer.timeout.connect(self._poll_foreground)
        self._poll_timer.start(500)

        # Single-shot timer used to debounce the overlay hide.
        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self._hide_due)

        self._main_window = self._create_window(is_main=True)
        self._build_all_windows()
        self._prune_empty_windows()

    # --- Window lifecycle --------------------------------------------------
    def _create_window(self, is_main: bool) -> OverlayWindow:
        idx = 0 if is_main else len(self.windows)
        win = OverlayWindow(is_main=is_main)
        win.set_opacity_percent(self._opacity)
        win.set_locked(self._locked)
        if is_main:
            win.profile_changed.connect(self.set_profile)
            win.create_window_requested.connect(self.create_window)
            win.lock_toggled.connect(self.set_locked)
        else:
            win.close_requested.connect(lambda w=win: self.close_window(w))
        win.row_dropped.connect(lambda row_id, w=win: self.move_row(row_id, w))
        win.position_changed.connect(self._on_window_moved)

        if is_main:
            win.move(WINDOW_POS_X, WINDOW_POS_Y)
        else:
            win.move(WINDOW_POS_X + idx * 40, WINDOW_POS_Y + idx * 40)

        self.windows.append(win)
        win.show()
        return win

    def create_window(self) -> None:
        self._create_window(is_main=False)
        # Register an (empty) slot for this window in the current profile so
        # it becomes active/visible instead of being hidden.
        if self.profiles and 0 <= self.current_index < len(self.profiles):
            profile_id = self.profiles[self.current_index].get("id", "?")
            self._layout_for_profile(profile_id).append([])
        self._build_all_windows()
        self._save()

    def close_window(self, win: OverlayWindow) -> None:
        if win is self._main_window or win not in self.windows:
            return
        idx = self.windows.index(win)
        # Move its rows back to the main window for every profile.
        for layout in self.layout.values():
            if idx < len(layout):
                moved = layout.pop(idx)
                if layout:
                    layout[0].extend(moved)
        self.windows.remove(win)
        win.deleteLater()
        self._save()
        self._build_all_windows()

    def toggle_visibility(self) -> None:
        self._master_visible = not self._master_visible
        self._refresh_visibility(immediate=True)

    def is_pattern_active(self, pattern: str) -> bool:
        return pattern in self.patterns

    def toggle_pattern(self, pattern: str) -> None:
        if pattern in self.patterns:
            self.patterns.discard(pattern)
        else:
            self.patterns.add(pattern)
        self._save()
        self._refresh_visibility(immediate=True)

    def _rule_matches(self, title: str, rule: dict) -> bool:
        mode = rule.get("mode", "exact")
        pattern = rule.get("pattern", "")
        if mode == "regex":
            try:
                return re.search(pattern, title, re.IGNORECASE) is not None
            except re.error:
                return False
        t = title.casefold()
        p = pattern.casefold()
        if mode == "exact":
            return t == p
        if mode == "startswith":
            return t.startswith(p)
        if mode == "contains":
            return p in t
        if mode == "endswith":
            return t.endswith(p)
        return False

    def _any_matches(self, title: str) -> bool:
        if title in self.patterns:
            return True
        for rule in self.custom_rules:
            if rule.get("enabled", True) and self._rule_matches(title, rule):
                return True
        return False

    def add_custom_rule(self, name: str, pattern: str, mode: str) -> None:
        self.custom_rules = [r for r in self.custom_rules if r.get("name") != name]
        self.custom_rules.append(
            {"name": name, "pattern": pattern, "mode": mode, "enabled": True}
        )
        self._save()
        self._refresh_visibility(immediate=True)

    def remove_custom_rule(self, name: str) -> None:
        self.custom_rules = [r for r in self.custom_rules if r.get("name") != name]
        self._save()
        self._refresh_visibility(immediate=True)

    def set_custom_rule_enabled(self, name: str, enabled: bool) -> None:
        for r in self.custom_rules:
            if r.get("name") == name:
                r["enabled"] = bool(enabled)
        self._save()
        self._refresh_visibility(immediate=True)

    def is_custom_rule_enabled(self, name: str) -> bool:
        return any(
            r.get("name") == name and r.get("enabled", True)
            for r in self.custom_rules
        )

    def _refresh_open_titles(self) -> None:
        self._open_titles = {
            w["title"] for w in window_detector.list_windows()
        }

    def _poll_foreground(self) -> None:
        self._refresh_open_titles()
        fg_id = window_detector.foreground_id()
        title = window_detector.foreground_title()
        if fg_id != self._foreground_id or title != self._foreground_title:
            self._foreground_id = fg_id
            self._foreground_title = title
            self._refresh_visibility()

    def _own_window_ids(self) -> set:
        return {int(w.winId()) for w in self.windows}

    def _should_show(self) -> bool:
        if not self._master_visible:
            return False
        if not self.patterns and not any(
            r.get("enabled", True) for r in self.custom_rules
        ):
            return True
        # Fallback: if no tracked rule matches an open window, stay visible.
        if not any(self._any_matches(t) for t in self._open_titles):
            return True
        fg_id = self._foreground_id
        if fg_id is None:
            # No active window (e.g. desktop) -> hide.
            return False
        if fg_id in self._own_window_ids():
            # Our own overlay window is focused -> keep visible.
            return True
        if not self._foreground_title:
            # A native Wayland window (sentinel id, no X11 title) is focused.
            return False
        return self._any_matches(self._foreground_title)

    def _active_window_count(self) -> int:
        if not self.profiles or self.current_index >= len(self.profiles):
            return 1
        profile_id = self.profiles[self.current_index].get("id", "?")
        return max(1, len(self.layout.get(profile_id, [])))

    def _set_all_visible(self, visible: bool) -> None:
        count = self._active_window_count()
        for i, win in enumerate(self.windows):
            win.setVisible(visible and i < count)

    def _refresh_visibility(self, immediate: bool = False) -> None:
        if self._should_show():
            self._hide_timer.stop()
            self._set_all_visible(True)
        elif immediate:
            self._hide_timer.stop()
            self._set_all_visible(False)
        else:
            # Debounce the hide to avoid flicker from transient focus changes.
            if not self._hide_timer.isActive():
                self._hide_timer.start(FOCUS_HIDE_DELAY_MS)

    def _hide_due(self) -> None:
        if not self._should_show():
            self._set_all_visible(False)

    def raise_all(self) -> None:
        for win in self.windows:
            win.raise_()

    def _on_window_moved(self) -> None:
        self._save()

    def reset_positions(self) -> None:
        """Center the overlay windows on the primary screen (recovery)."""
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            return
        geo = screen.availableGeometry()
        for i, win in enumerate(self.windows):
            x = geo.x() + (geo.width() - win.width()) // 2
            y = geo.y() + (geo.height() - win.height()) // 2
            win.move(x + i * 40, y + i * 40)
        self.settings["window_positions"] = {}
        self._save()

    def _restore_positions(self) -> None:
        if not self.profiles or self.current_index >= len(self.profiles):
            return
        profile_id = self.profiles[self.current_index].get("id", "?")
        positions = self.settings.get("window_positions", {}).get(profile_id, [])
        for i, pos in enumerate(positions):
            if i < len(self.windows):
                self.windows[i].move(pos[0], pos[1])

    def _save_positions(self) -> None:
        if not self.profiles or self.current_index >= len(self.profiles):
            return
        profile_id = self.profiles[self.current_index].get("id", "?")
        count = self._active_window_count()
        positions = self.settings.setdefault("window_positions", {})
        positions[profile_id] = [
            [w.pos().x(), w.pos().y()] for w in self.windows[:count]
        ]

    # --- Lock / opacity (global) ------------------------------------------
    def is_locked(self) -> bool:
        return self._locked

    def set_locked(self, locked: bool) -> None:
        self._locked = bool(locked)
        for win in self.windows:
            win.set_locked(self._locked)
        self.lock_changed.emit(self._locked)

    def toggle_lock(self) -> None:
        self.set_locked(not self._locked)

    def opacity_percent(self) -> int:
        return self._opacity

    def set_opacity_percent(self, percent: int) -> None:
        self._opacity = int(percent)
        self.settings["opacity_percent"] = self._opacity
        for win in self.windows:
            win.set_opacity_percent(self._opacity)
        self._save()

    # --- Data / layout -----------------------------------------------------
    def set_profile(self, index: int) -> None:
        if 0 <= index < len(self.profiles):
            self.current_index = index
        self._build_all_windows()
        self._save()

    def reload_keymap(self, keymap: dict) -> None:
        previous_id = None
        if self.profiles and 0 <= self.current_index < len(self.profiles):
            previous_id = self.profiles[self.current_index].get("id")
        self.keymap = keymap
        self.profiles = keymap.get("profiles", [])
        self.current_index = self._find_profile_index(previous_id)
        self._build_all_windows()
        self._prune_empty_windows()
        self._save()

    def move_row(self, row_id: str, target_win: OverlayWindow) -> None:
        if not self.profiles or target_win not in self.windows:
            return
        profile_id = self.profiles[self.current_index].get("id", "?")
        layout = self._layout_for_profile(profile_id)
        target_index = self.windows.index(target_win)
        while len(layout) <= target_index:
            layout.append([])
        source_index = None
        for i, win_ids in enumerate(layout):
            if row_id in win_ids:
                source_index = i
                break
        if source_index is None or source_index == target_index:
            return
        layout[source_index].remove(row_id)
        layout[target_index].append(row_id)
        self._save()
        # Rebuild after the drag & drop completes; rebuilding synchronously
        # deletes the drag source mid-gesture and breaks subsequent drags.
        QTimer.singleShot(0, self._build_all_windows)

    def _build_all_windows(self) -> None:
        names = [c.get("name", "?") for c in self.profiles]
        if not self.profiles:
            self._main_window.set_profiles([], 0)
            for win in self.windows:
                win.set_sections([])
            self._refresh_visibility(immediate=True)
            return
        profile = self.profiles[self.current_index]
        layout, rows = self._reconcile(profile)
        row_map = {r["id"]: r for r in rows}
        self._main_window.set_profiles(names, self.current_index)
        while len(self.windows) < len(layout):
            self._create_window(is_main=False)
        for i, win in enumerate(self.windows):
            if i < len(layout):
                win_rows = [row_map[rid] for rid in layout[i] if rid in row_map]
                win.set_sections(self._group_rows(win_rows))
        self._restore_positions()
        self._refresh_visibility(immediate=True)

    # --- Helpers -----------------------------------------------------------
    def _find_profile_index(self, profile_id) -> int:
        if profile_id:
            for i, c in enumerate(self.profiles):
                if c.get("id") == profile_id:
                    return i
        return 0

    def _rows_for_profile(self, profile: dict) -> list:
        rows = []
        profile_id = profile.get("id", "?")
        for group in profile.get("groups", []):
            group_title = group.get("title", "")
            for hk in group.get("hotkeys", []):
                rows.append(
                    {
                        "id": f"{profile_id}||{group_title}||{hk.get('key', '')}",
                        "group": group_title,
                        "key": hk.get("key", ""),
                        "label": hk.get("label", ""),
                        "icon": hk.get("icon"),
                    }
                )
        return rows

    def _layout_for_profile(self, profile_id: str) -> list:
        if profile_id not in self.layout:
            self.layout[profile_id] = [[]]
        return self.layout[profile_id]

    def _reconcile(self, profile: dict) -> tuple[list, list]:
        profile_id = profile.get("id", "?")
        rows = self._rows_for_profile(profile)
        ids = [r["id"] for r in rows]
        id_set = set(ids)
        layout = self._layout_for_profile(profile_id)
        cleaned = [[rid for rid in win_ids if rid in id_set] for win_ids in layout]
        assigned = set()
        for win_ids in cleaned:
            assigned.update(win_ids)
        for rid in ids:
            if rid not in assigned:
                cleaned[0].append(rid)
        self.layout[profile_id] = cleaned
        return cleaned, rows

    def _window_is_empty(self, index: int) -> bool:
        for layout in self.layout.values():
            if index < len(layout) and layout[index]:
                return False
        return True

    def _prune_empty_windows(self) -> None:
        """Close extra windows that have no rows for any profile."""
        to_remove = [
            i for i in range(1, len(self.windows)) if self._window_is_empty(i)
        ]
        for i in reversed(to_remove):
            win = self.windows.pop(i)
            win.deleteLater()
            for layout in self.layout.values():
                if i < len(layout):
                    layout.pop(i)

    @staticmethod
    def _group_rows(rows: list) -> list:
        sections = []
        current_title = None
        current_rows = []
        for r in rows:
            if r["group"] != current_title:
                if current_title is not None:
                    sections.append((current_title, current_rows))
                current_title = r["group"]
                current_rows = []
            current_rows.append(r)
        if current_title is not None:
            sections.append((current_title, current_rows))
        return sections

    def _save(self) -> None:
        if self.save_callback:
            self.settings["window_layout"] = self.layout
            self.settings["active_windows"] = sorted(self.patterns)
            self.settings["custom_rules"] = self.custom_rules
            self._save_positions()
            if self.profiles and 0 <= self.current_index < len(self.profiles):
                self.settings["selected_profile"] = (
                    self.profiles[self.current_index].get("id")
                )
            self.save_callback(self.settings)
