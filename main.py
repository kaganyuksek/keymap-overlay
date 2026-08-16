"""
Keymap Overlay — entry point.

- Launches the overlay window.
- Adds a system tray icon (show/hide, lock, quit).
- Watches data/keymap.json and reloads it automatically when saved.
"""

import json
import os
import sys

# Under a KDE/Wayland session Qt's "always-on-top" hint (WindowStaysOnTopHint)
# can be ignored. Force the XWayland (xcb) backend under Wayland so the window
# reliably stays above all others. Must run BEFORE Qt is imported.
if os.environ.get("XDG_SESSION_TYPE") == "wayland" and "QT_QPA_PLATFORM" not in os.environ:
    os.environ["QT_QPA_PLATFORM"] = "xcb"

from PyQt6.QtCore import QFileSystemWatcher, Qt, QTimer
from PyQt6.QtGui import QColor, QIcon, QPainter, QPixmap
from PyQt6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from config.constants import (
    APP_TITLE,
    BACKGROUND_COLOR,
    KEYMAP_PATH,
    TRAY_ICON_BAR_COLOR,
    TRAY_ICON_SIZE,
    rgb,
)
from ui.overlay_window import OverlayWindow


def load_keymap() -> dict:
    """Read keymap.json; return an empty structure on failure."""
    try:
        with open(KEYMAP_PATH, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {"characters": []}


def make_tray_icon() -> QIcon:
    """Draw a simple tray icon (dark rounded panel + colored bars)."""
    pixmap = QPixmap(TRAY_ICON_SIZE, TRAY_ICON_SIZE)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(*BACKGROUND_COLOR))
    painter.drawRoundedRect(2, 2, TRAY_ICON_SIZE - 4, TRAY_ICON_SIZE - 4, 6, 6)

    painter.setBrush(QColor(*TRAY_ICON_BAR_COLOR))
    bar_h = 3
    gap = 4
    x = 7
    w = TRAY_ICON_SIZE - 14
    for i in range(3):
        y = 9 + i * (bar_h + gap)
        painter.drawRoundedRect(x, y, w, bar_h, 1, 1)
    painter.end()

    return QIcon(pixmap)


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName(APP_TITLE)
    # Keep the app alive in the tray even if the frameless window is closed.
    app.setQuitOnLastWindowClosed(False)

    window = OverlayWindow(load_keymap())
    window.show()

    # Some WMs ignore the stay-on-top hint; periodically raise the window to
    # guarantee the overlay stays on top.
    keep_on_top = QTimer()
    keep_on_top.timeout.connect(window.raise_)
    keep_on_top.start(2000)

    # --- System tray -------------------------------------------------------
    tray = QSystemTrayIcon(make_tray_icon())
    tray.setToolTip(APP_TITLE)

    menu = QMenu()

    show_action = menu.addAction("Show / Hide")
    show_action.triggered.connect(window.setVisible)

    lock_action = menu.addAction("Lock (click-through)")

    def update_lock_text(locked: bool) -> None:
        lock_action.setText(
            "Unlock (normal mode)" if locked else "Lock (click-through)"
        )

    lock_action.triggered.connect(window.toggle_lock)
    window.lock_changed.connect(update_lock_text)
    update_lock_text(window.is_locked())

    menu.addSeparator()
    quit_action = menu.addAction("Quit")
    quit_action.triggered.connect(app.quit)

    tray.setContextMenu(menu)
    # Left click toggles the window visibility.
    tray.activated.connect(
        lambda reason: (
            window.setVisible(not window.isVisible())
            if reason == QSystemTrayIcon.ActivationReason.Trigger
            else None
        )
    )
    tray.show()

    # --- keymap.json watcher -----------------------------------------------
    watcher = QFileSystemWatcher()
    watcher.addPath(str(KEYMAP_PATH))

    def on_file_changed(path: str) -> None:
        window.reload_keymap(load_keymap())
        # Editors may save atomically (rename); refresh the watch.
        watcher.addPath(str(KEYMAP_PATH))

    watcher.fileChanged.connect(on_file_changed)

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
