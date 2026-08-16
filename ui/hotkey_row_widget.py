"""
Widget representing a single hotkey row.

A row looks like: [icon] [F1] Description
- If the icon is null in JSON (or the file is missing) the icon is omitted
  with no gap left; only the key badge + description remain.
"""

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QPixmap
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QWidget

from config.constants import (
    FONT_FAMILY,
    FONT_SIZE_HOTKEY,
    FONT_SIZE_KEY,
    ICON_SIZE,
    ICON_TEXT_SPACING,
    ICONS_DIR,
    KEY_BADGE_BG,
    KEY_BADGE_TEXT_COLOR,
    TEXT_COLOR,
    rgb,
)


class HotkeyRowWidget(QWidget):
    def __init__(self, hotkey: dict, parent: QWidget | None = None) -> None:
        super().__init__(parent)
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
