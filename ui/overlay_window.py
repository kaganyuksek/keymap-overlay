"""
Main overlay window.

- Frameless, always-on-top, semi-transparent background (rounded rect drawn in paintEvent).
- Dragging is done from the "move" handle in the top-left corner.
- "Locked/click-through" mode: on X11 the window input region is restricted to the
  lock button, so the rest of the window passes clicks through while the lock
  button always remains clickable.
- Character selector at the top (when there are multiple characters) and a lock button.
"""

import ctypes

from PyQt6.QtCore import QPoint, QPointF, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QGuiApplication, QPainter, QPen, QPolygonF
from PyQt6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from config.constants import (
    BACKGROUND_ALPHA,
    BACKGROUND_COLOR,
    CORNER_RADIUS,
    DRAG_HANDLE_COLOR,
    DRAG_HANDLE_SIZE,
    FONT_FAMILY,
    FONT_SIZE_TITLE,
    GROUP_SPACING,
    LOCK_BUTTON_SIZE,
    LOCKED_COLOR,
    PANEL_PADDING,
    TEXT_COLOR,
    UNLOCKED_COLOR,
    WINDOW_HEIGHT,
    WINDOW_POS_X,
    WINDOW_POS_Y,
    WINDOW_WIDTH,
    rgb,
)
from ui.group_widget import GroupWidget


# --- X11 click-through helpers --------------------------------------------
# WA_TransparentForMouseEvents is not reliable under XWayland. Instead we set
# the window input region directly via X11 ShapeInput. In locked mode the input
# region is only the lock button, so the button stays clickable while the rest
# of the window passes clicks through.

class _XRectangle(ctypes.Structure):
    _fields_ = [
        ("x", ctypes.c_short),
        ("y", ctypes.c_short),
        ("width", ctypes.c_ushort),
        ("height", ctypes.c_ushort),
    ]


_SHAPE_INPUT = 2
_SHAPE_SET = 0
_UNSORTED = 0

_x11 = {"dpy": None, "xlib": None, "xshape": None}


def _x11_ready() -> bool:
    """Set up X11/XShape access once and report whether it is available."""
    if _x11["dpy"] is not None:
        return True
    try:
        xlib = ctypes.CDLL("libX11.so.6")
        xshape = ctypes.CDLL("libXext.so.6")
        xlib.XOpenDisplay.restype = ctypes.c_void_p
        xlib.XOpenDisplay.argtypes = [ctypes.c_char_p]
        xlib.XFlush.argtypes = [ctypes.c_void_p]
        xshape.XShapeCombineRectangles.argtypes = [
            ctypes.c_void_p,            # Display*
            ctypes.c_ulong,             # Window dest
            ctypes.c_int,               # dest_kind
            ctypes.c_int,               # x_off
            ctypes.c_int,               # y_off
            ctypes.POINTER(_XRectangle),  # rectangles
            ctypes.c_int,               # n_rects
            ctypes.c_int,               # op
            ctypes.c_int,               # ordering
        ]
        dpy = xlib.XOpenDisplay(None)
        if not dpy:
            return False
        _x11["xlib"] = xlib
        _x11["xshape"] = xshape
        _x11["dpy"] = dpy
        return True
    except OSError:
        return False


def _set_input_shape(win_id: int, rect) -> None:
    """Restrict the window input region to a single rectangle (X11)."""
    if not _x11_ready():
        return
    x, y, w, h = rect
    rect = _XRectangle(x, y, w, h)
    arr = (_XRectangle * 1)(rect)
    _x11["xshape"].XShapeCombineRectangles(
        _x11["dpy"], win_id, _SHAPE_INPUT, 0, 0, arr, 1, _SHAPE_SET, _UNSORTED
    )
    _x11["xlib"].XFlush(_x11["dpy"])


class LockButton(QWidget):
    """Small lock icon in the top-right corner. Emits a toggle signal on click."""

    clicked = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._locked = False
        self.setFixedSize(LOCK_BUTTON_SIZE, LOCK_BUTTON_SIZE)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("Lock / unlock (clicks pass through)")

    def set_locked(self, locked: bool) -> None:
        self._locked = locked
        self.update()

    def mousePressEvent(self, event) -> None:
        # Accepting the press is required: otherwise the event propagates to the
        # parent, the drag logic grabs the mouse and the release never reaches
        # this button (so 'clicked' would never fire).
        event.accept()

    def mouseReleaseEvent(self, event) -> None:
        # Only counts as a click if released inside the button area.
        if event.button() == Qt.MouseButton.LeftButton:
            if self.rect().contains(event.position().toPoint()):
                self.clicked.emit()
        event.accept()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        color = QColor(*(UNLOCKED_COLOR if not self._locked else LOCKED_COLOR))
        pen = QPen(color, 1.6)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)

        # Shackle: closed half-loop when locked, open loop when unlocked.
        if self._locked:
            painter.drawArc(6, 2, 10, 10, 0, 180 * 16)
        else:
            painter.drawArc(9, 3, 8, 8, 90 * 16, 180 * 16)

        # Body
        painter.setBrush(color)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(4, 9, 14, 11, 2, 2)

        # Keyhole
        painter.setBrush(QColor(20, 20, 20))
        painter.drawEllipse(9, 12, 4, 4)
        painter.drawRect(10, 15, 2, 3)
        painter.end()


class DragHandle(QWidget):
    """Small square grab area used for dragging; draws a "move" icon inside."""

    drag_started = pyqtSignal(QPoint)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(DRAG_HANDLE_SIZE, DRAG_HANDLE_SIZE)
        self.setCursor(Qt.CursorShape.SizeAllCursor)
        self.setToolTip("Drag")

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_started.emit(event.globalPosition().toPoint())
        event.accept()

    def mouseMoveEvent(self, event) -> None:
        event.accept()

    def mouseReleaseEvent(self, event) -> None:
        event.accept()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QColor(*DRAG_HANDLE_COLOR))
        painter.setPen(Qt.PenStyle.NoPen)

        cx = self.width() / 2.0
        cy = self.height() / 2.0

        def arrow(tip, base1, base2):
            painter.drawPolygon(
                QPolygonF([QPointF(*tip), QPointF(*base1), QPointF(*base2)])
            )

        # Four-way "move" arrows: up, down, left, right.
        arrow((cx, cy - 7), (cx - 3.5, cy - 1), (cx + 3.5, cy - 1))
        arrow((cx, cy + 7), (cx - 3.5, cy + 1), (cx + 3.5, cy + 1))
        arrow((cx - 7, cy), (cx - 1, cy - 3.5), (cx - 1, cy + 3.5))
        arrow((cx + 7, cy), (cx + 1, cy - 3.5), (cx + 1, cy + 3.5))
        painter.end()


class OverlayWindow(QWidget):
    """Frameless, draggable, semi-transparent hotkey reference panel."""

    lock_changed = pyqtSignal(bool)

    def __init__(self, keymap: dict, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.keymap = keymap
        self.characters = keymap.get("characters", [])
        self.current_character = None
        self._locked = False
        self._drag_offset = None

        self._build_ui()

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.resize(WINDOW_WIDTH, WINDOW_HEIGHT)
        self.move(WINDOW_POS_X, WINDOW_POS_Y)

    # --- UI setup ----------------------------------------------------------
    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(
            PANEL_PADDING, PANEL_PADDING, PANEL_PADDING, PANEL_PADDING
        )
        outer.setSpacing(GROUP_SPACING)

        # Top bar: character selector + drag handle + lock button
        top_bar = QHBoxLayout()
        top_bar.setSpacing(GROUP_SPACING)

        self.character_combo = QComboBox()
        self.character_combo.addItems([c.get("name", "?") for c in self.characters])
        self.character_combo.currentIndexChanged.connect(self._on_character_changed)

        self.title_label = QLabel()
        self.title_label.setFont(self._title_font())
        self.title_label.setStyleSheet("color: {};".format(rgb(TEXT_COLOR)))

        # Both the dropdown and the title label are added; their visibility is
        # switched based on the character count (it can change on reload).
        self.drag_handle = DragHandle()
        self.drag_handle.drag_started.connect(self._start_drag)
        top_bar.addWidget(self.drag_handle, alignment=Qt.AlignmentFlag.AlignLeft)

        top_bar.addWidget(self.character_combo, stretch=1)
        top_bar.addWidget(self.title_label, stretch=1)

        self.lock_button = LockButton()
        self.lock_button.clicked.connect(self.toggle_lock)
        top_bar.addWidget(self.lock_button, alignment=Qt.AlignmentFlag.AlignRight)
        outer.addLayout(top_bar)

        # Scroll area holding the groups
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self._set_transparent(self.scroll)
        self._set_transparent(self.scroll.viewport())

        self.content = QWidget()
        self._set_transparent(self.content)
        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(GROUP_SPACING)
        self.content_layout.addStretch(1)
        self.scroll.setWidget(self.content)
        outer.addWidget(self.scroll)

        # Select the first character
        self._set_selector_mode()
        self._on_character_changed(0)

    def _set_selector_mode(self) -> None:
        use_combo = len(self.characters) > 1
        self.character_combo.setVisible(use_combo)
        self.title_label.setVisible(not use_combo)

    @staticmethod
    def _title_font():
        from PyQt6.QtGui import QFont

        font = QFont(FONT_FAMILY, FONT_SIZE_TITLE)
        font.setBold(True)
        return font

    @staticmethod
    def _set_transparent(widget: QWidget) -> None:
        widget.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        widget.setStyleSheet("background: transparent;")

    def _clear_groups(self) -> None:
        # Clear the group widgets from content_layout (except the stretch).
        while self.content_layout.count() > 1:
            item = self.content_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _on_character_changed(self, index: int) -> None:
        if not self.characters or index < 0 or index >= len(self.characters):
            return
        self.current_character = self.characters[index]
        self.title_label.setText(self.current_character.get("name", ""))
        self._clear_groups()
        for group in self.current_character.get("groups", []):
            self.content_layout.insertWidget(
                self.content_layout.count() - 1,
                GroupWidget(group.get("title", ""), group.get("hotkeys", [])),
            )

    # --- Lock / click-through ----------------------------------------------
    def is_locked(self) -> bool:
        return self._locked

    def set_locked(self, locked: bool) -> None:
        self._locked = locked
        self.lock_button.set_locked(locked)
        self._apply_click_through()
        self.lock_changed.emit(locked)

    def toggle_lock(self) -> None:
        self.set_locked(not self._locked)

    def _apply_click_through(self) -> None:
        """Make the window click-through when locked (except the lock button)."""
        if QGuiApplication.platformName() == "xcb":
            win_id = int(self.winId())
            if win_id:
                if self._locked:
                    # Input region = lock button only (in window coordinates)
                    rect = self.lock_button.geometry().getRect()
                else:
                    # Input region = whole window
                    rect = (0, 0, self.width(), self.height())
                _set_input_shape(win_id, rect)
                return
        # Fall back to the classic Qt behavior when X11/XShape is unavailable.
        self.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents, self._locked
        )

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._apply_click_through()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self._locked:
            self._apply_click_through()

    # --- Data reload -------------------------------------------------------
    def reload_keymap(self, keymap: dict) -> None:
        previous_id = (
            self.current_character.get("id") if self.current_character else None
        )
        self.keymap = keymap
        self.characters = keymap.get("characters", [])

        # Update the character list (rebuilds the dropdown).
        self.character_combo.blockSignals(True)
        self.character_combo.clear()
        self.character_combo.addItems([c.get("name", "?") for c in self.characters])
        self.character_combo.blockSignals(False)

        # Update dropdown/title visibility.
        self._set_selector_mode()

        # Restore the previously selected character by id.
        index = 0
        if previous_id:
            for i, c in enumerate(self.characters):
                if c.get("id") == previous_id:
                    index = i
                    break
        self.character_combo.setCurrentIndex(index)
        self._on_character_changed(index)
        if self._locked:
            self._apply_click_through()

    # --- Dragging ----------------------------------------------------------
    # Dragging is started only from the DragHandle in the top-left. Pressing the
    # handle emits drag_started, which calls _start_drag, grabs the mouse to the
    # window and lets subsequent move/release events be handled by the window.

    def _start_drag(self, global_pos) -> None:
        self._drag_offset = global_pos - self.frameGeometry().topLeft()
        self.grabMouse()

    def _move_drag(self, global_pos) -> None:
        if self._drag_offset is not None:
            self.move(global_pos - self._drag_offset)

    def _end_drag(self) -> None:
        self._drag_offset = None
        self.releaseMouse()

    def mouseMoveEvent(self, event) -> None:
        if self._drag_offset is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self._move_drag(event.globalPosition().toPoint())
            event.accept()

    def mouseReleaseEvent(self, event) -> None:
        self._end_drag()

    # --- Background painting -----------------------------------------------
    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QColor(BACKGROUND_COLOR[0], BACKGROUND_COLOR[1], BACKGROUND_COLOR[2], BACKGROUND_ALPHA))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(self.rect(), CORNER_RADIUS, CORNER_RADIUS)
        painter.end()
