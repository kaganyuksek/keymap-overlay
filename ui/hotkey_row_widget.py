"""
Widget representing a single hotkey row.

A row looks like: [icon] [F1] Description
- If the icon is null in JSON (or the file is missing) the icon is omitted
  with no gap left; only the key badge + description remain.
- A row can be dragged to move it between overlay windows (drag & drop).
"""

from PyQt6.QtCore import QMimeData, Qt
from PyQt6.QtGui import QDrag, QFont, QPixmap
from PyQt6.QtWidgets import QApplication, QHBoxLayout, QLabel, QWidget

from config.constants import (
    FONT_FAMILY,
    FONT_SIZE_HOTKEY,
    FONT_SIZE_KEY,
    ICON_SIZE,
    ICON_TEXT_SPACING,
    ICONS_DIR,
    KEY_BADGE_BG,
    KEY_BADGE_TEXT_COLOR,
    ROW_MIME_TYPE,
    TEXT_COLOR,
    rgb,
)


class HotkeyRowWidget(QWidget):
    def __init__(self, hotkey: dict, row_id: str | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._row_id = row_id if row_id is not None else hotkey.get("id")
        self._press_pos = None
        self._build(hotkey)

    def _build(self, hotkey: dict) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(ICON_TEXT_SPACING)

        # Icon (if present)
        icon_name = hotkey.get("icon")
        if icon_name:
            icon_path = ICONS_DIR / icon_name
            if icon_path.exists():
                icon_label = QLabel()
                pixmap = QPixmap(str(icon_path)).scaled(
                    ICON_SIZE,
                    ICON_SIZE,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                icon_label.setPixmap(pixmap)
                icon_label.setFixedSize(ICON_SIZE, ICON_SIZE)
                layout.addWidget(icon_label)

        # Key badge (F1, F2, ...)
        key_label = QLabel(hotkey.get("key", ""))
        key_font = QFont(FONT_FAMILY, FONT_SIZE_KEY)
        key_font.setBold(True)
        key_label.setFont(key_font)
        key_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        # Minimum width keeps short keys tidy; the badge grows for long keys
        # (e.g. "Ctrl+Shift+F") so the text never clips.
        key_label.setMinimumWidth(ICON_SIZE * 2)
        key_label.setStyleSheet(
            "background-color: {};"
            "color: {};"
            "border-radius: 4px;"
            "padding: 2px 4px;".format(rgb(KEY_BADGE_BG), rgb(KEY_BADGE_TEXT_COLOR))
        )
        layout.addWidget(key_label)

        # Description
        desc_label = QLabel(hotkey.get("label", ""))
        desc_label.setFont(QFont(FONT_FAMILY, FONT_SIZE_HOTKEY))
        desc_label.setStyleSheet("color: {};".format(rgb(TEXT_COLOR)))
        desc_label.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        layout.addWidget(desc_label, stretch=1)

    # --- Drag & drop (source) ---------------------------------------------
    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._press_pos = event.position().toPoint()
        event.accept()

    def mouseMoveEvent(self, event) -> None:
        if (
            self._press_pos is not None
            and event.buttons() & Qt.MouseButton.LeftButton
            and self._row_id is not None
        ):
            if (
                event.position().toPoint() - self._press_pos
            ).manhattanLength() >= QApplication.startDragDistance():
                self._start_drag()
                return
        event.accept()

    def mouseReleaseEvent(self, event) -> None:
        self._press_pos = None
        event.accept()

    def _start_drag(self) -> None:
        drag = QDrag(self)
        mime = QMimeData()
        mime.setData(ROW_MIME_TYPE, self._row_id.encode("utf-8"))
        drag.setMimeData(mime)
        drag.exec(Qt.DropAction.MoveAction)
        self._press_pos = None
