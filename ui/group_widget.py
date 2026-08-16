"""
Widget representing a single hotkey group.

Shows a group header at the top (e.g. "Combat") with the hotkey rows below.
"""

from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QLabel, QVBoxLayout, QWidget

from config.constants import (
    FONT_FAMILY,
    FONT_SIZE_GROUP_HEADER,
    GROUP_HEADER_COLOR,
    ROW_SPACING,
    rgb,
)
from ui.hotkey_row_widget import HotkeyRowWidget


class GroupWidget(QWidget):
    def __init__(self, title: str, hotkeys: list, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._build(title, hotkeys)

    def _build(self, title: str, hotkeys: list) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(ROW_SPACING)

        header = QLabel(title)
        header_font = QFont(FONT_FAMILY, FONT_SIZE_GROUP_HEADER)
        header_font.setBold(True)
        header.setFont(header_font)
        header.setStyleSheet("color: {};".format(rgb(GROUP_HEADER_COLOR)))
        layout.addWidget(header)

        for hotkey in hotkeys:
            layout.addWidget(HotkeyRowWidget(hotkey))
