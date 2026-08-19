"""
A single column of a hotkey group.

A group is split into one or more columns when the overlay is widened. The
first column carries the group header; continuation columns only hold rows.
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
    def __init__(
        self,
        title: str,
        hotkeys: list,
        show_header: bool = True,
        min_width: int | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        if min_width:
            self.setMinimumWidth(min_width)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(ROW_SPACING)

        # Always reserve the header line so continuation columns keep their
        # rows aligned with the first column that carries the group title.
        header_text = title if (show_header and title) else " "
        header = QLabel(header_text)
        header_font = QFont(FONT_FAMILY, FONT_SIZE_GROUP_HEADER)
        header_font.setBold(True)
        header.setFont(header_font)
        header.setStyleSheet("color: {};".format(rgb(GROUP_HEADER_COLOR)))
        layout.addWidget(header)

        for hotkey in hotkeys:
            layout.addWidget(HotkeyRowWidget(hotkey))
