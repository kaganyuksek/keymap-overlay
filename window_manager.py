"""
Window manager for the overlay.

Manages multiple overlay windows, distributes hotkey rows among them and
persists the layout. Lock state and opacity are global across all windows.
"""

from PyQt6.QtCore import QObject, QTimer, pyqtSignal

import window_detector
from config.constants import FOCUS_HIDE_DELAY_MS, WINDOW_POS_X, WINDOW_POS_Y
from ui.overlay_window import OverlayWindow


class WindowManager(QObject):
    lock_changed = pyqtSignal(bool)

    def __init__(self, keymap: dict, settings: dict, save_callback=None) -> None:
        super().__init__()
        self.keymap = keymap
        self.characters = keymap.get("characters", [])
        self.settings = settings
        self.save_callback = save_callback
        self.layout = settings.get("window_layout", {})
        self.windows = []
        self.current_index = 0
        self._locked = False
        self._opacity = int(settings.get("opacity_percent", 90))
        self._master_visible = True
        self.checked_titles = set(settings.get("active_windows", []))
        self._foreground_id = window_detector.foreground_id()
        self._foreground_title = window_detector.foreground_title()

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
        win = OverlayWindow(is_main=is_main)
        win.set_opacity_percent(self._opacity)
        win.set_locked(self._locked)
        if is_main:
            win.character_changed.connect(self.set_character)
            win.create_window_requested.connect(self.create_window)
            win.lock_toggled.connect(self.set_locked)
            win.move(WINDOW_POS_X, WINDOW_POS_Y)
        else:
            idx = len(self.windows)
            win.close_requested.connect(lambda w=win: self.close_window(w))
            win.move(WINDOW_POS_X + idx * 40, WINDOW_POS_Y + idx * 40)
        win.row_dropped.connect(lambda row_id, w=win: self.move_row(row_id, w))
        self.windows.append(win)
        win.show()
        return win

    def create_window(self) -> None:
        self._create_window(is_main=False)
        self._build_all_windows()
        self._save()

    def close_window(self, win: OverlayWindow) -> None:
        if win is self._main_window or win not in self.windows:
            return
        idx = self.windows.index(win)
        # Move its rows back to the main window for every character.
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

    def is_window_title_checked(self, title: str) -> bool:
        return title in self.checked_titles

    def toggle_window_title(self, title: str) -> None:
        if title in self.checked_titles:
            self.checked_titles.discard(title)
        else:
            self.checked_titles.add(title)
        self._save()
        self._refresh_visibility(immediate=True)

    def _poll_foreground(self) -> None:
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
        if not self.checked_titles:
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
        return self._foreground_title in self.checked_titles

    def _set_all_visible(self, visible: bool) -> None:
        for win in self.windows:
            win.setVisible(visible)

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
    def set_character(self, index: int) -> None:
        if 0 <= index < len(self.characters):
            self.current_index = index
        self._build_all_windows()

    def reload_keymap(self, keymap: dict) -> None:
        previous_id = None
        if self.characters and 0 <= self.current_index < len(self.characters):
            previous_id = self.characters[self.current_index].get("id")
        self.keymap = keymap
        self.characters = keymap.get("characters", [])
        if previous_id:
            for i, c in enumerate(self.characters):
                if c.get("id") == previous_id:
                    self.current_index = i
                    break
        self._build_all_windows()
        self._prune_empty_windows()
        self._save()

    def move_row(self, row_id: str, target_win: OverlayWindow) -> None:
        if not self.characters or target_win not in self.windows:
            return
        char_id = self.characters[self.current_index].get("id", "?")
        layout = self._layout_for_char(char_id)
        target_index = self.windows.index(target_win)
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
        names = [c.get("name", "?") for c in self.characters]
        if not self.characters:
            self._main_window.set_characters([], 0)
            for win in self.windows:
                win.set_sections([])
            self._refresh_visibility(immediate=True)
            return
        char = self.characters[self.current_index]
        layout, rows = self._reconcile(char)
        row_map = {r["id"]: r for r in rows}
        self._main_window.set_characters(names, self.current_index)
        while len(self.windows) < len(layout):
            self._create_window(is_main=False)
        for i, win in enumerate(self.windows):
            if i < len(layout):
                win_rows = [row_map[rid] for rid in layout[i] if rid in row_map]
                win.set_sections(self._group_rows(win_rows))
            else:
                win.set_sections([])
        self._refresh_visibility(immediate=True)

    # --- Helpers -----------------------------------------------------------
    def _rows_for_character(self, char: dict) -> list:
        rows = []
        char_id = char.get("id", "?")
        for group in char.get("groups", []):
            group_title = group.get("title", "")
            for hk in group.get("hotkeys", []):
                rows.append(
                    {
                        "id": f"{char_id}||{group_title}||{hk.get('key', '')}",
                        "group": group_title,
                        "key": hk.get("key", ""),
                        "label": hk.get("label", ""),
                        "icon": hk.get("icon"),
                    }
                )
        return rows

    def _layout_for_char(self, char_id: str) -> list:
        if char_id not in self.layout:
            self.layout[char_id] = [[] for _ in self.windows]
        layout = self.layout[char_id]
        while len(layout) < len(self.windows):
            layout.append([])
        return layout

    def _reconcile(self, char: dict) -> tuple[list, list]:
        char_id = char.get("id", "?")
        rows = self._rows_for_character(char)
        ids = [r["id"] for r in rows]
        id_set = set(ids)
        layout = self._layout_for_char(char_id)
        cleaned = [[rid for rid in win_ids if rid in id_set] for win_ids in layout]
        assigned = set()
        for win_ids in cleaned:
            assigned.update(win_ids)
        for rid in ids:
            if rid not in assigned:
                cleaned[0].append(rid)
        self.layout[char_id] = cleaned
        return cleaned, rows

    def _window_is_empty(self, index: int) -> bool:
        for layout in self.layout.values():
            if index < len(layout) and layout[index]:
                return False
        return True

    def _prune_empty_windows(self) -> None:
        """Close extra windows that have no rows for any character."""
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
            self.settings["active_windows"] = sorted(self.checked_titles)
            self.save_callback(self.settings)
