"""
Overlay window.

- Frameless, always-on-top, semi-transparent background (rounded rect drawn in paintEvent).
- Dragging is done from the "move" handle in the top-left corner.
- "Locked/click-through" mode: on X11 the window input region is restricted to the
  lock button (main window) so the rest of the window passes clicks through while
  the lock button always remains clickable. Extra windows become fully click-through.
- The main window holds the character selector, the lock button and a "+" button
  to create extra windows; extra windows hold a close button.
- Content is a set of (group title, rows) sections; the window auto-sizes to its
  content (grows downward) instead of scrolling.
"""

import ctypes

from PyQt6.QtCore import QPoint, QPointF, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QGuiApplication, QPainter, QPen, QPolygonF
from PyQt6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from config.constants import (
    BACKGROUND_ALPHA,
    BACKGROUND_COLOR,
    CORNER_RADIUS,
    DRAG_HANDLE_COLOR,
    DRAG_HANDLE_SIZE,
    EMPTY_WINDOW_MIN_ROWS,
    GROUP_SPACING,
    LOCK_BUTTON_SIZE,
    LOCKED_COLOR,
    PANEL_PADDING,
    ROW_HEIGHT_ESTIMATE,
    ROW_MIME_TYPE,
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
# region is only the lock button (main window) or empty (extra windows).

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


def _set_input_shape(win_id: int, rects) -> None:
    """Set the window input region to the given rectangles (X11)."""
    if not _x11_ready():
        return
    n = len(rects)
    arr = (_XRectangle * max(1, n))()
    for i, rect in enumerate(rects):
        x, y, w, h = rect
        arr[i] = _XRectangle(x, y, w, h)
    _x11["xshape"].XShapeCombineRectangles(
        _x11["dpy"], win_id, _SHAPE_INPUT, 0, 0, arr, n, _SHAPE_SET, _UNSORTED
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

    character_changed = pyqtSignal(int)
    create_window_requested = pyqtSignal()
    close_requested = pyqtSignal()
    row_dropped = pyqtSignal(str)
    lock_toggled = pyqtSignal(bool)
    position_changed = pyqtSignal()

    def __init__(self, is_main: bool = True, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.is_main = is_main
        self._locked = False
        self._drag_offset = None
        self._background_alpha = BACKGROUND_ALPHA

        self._build_ui()

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAcceptDrops(True)
        self.resize(WINDOW_WIDTH, WINDOW_HEIGHT)
        self.move(WINDOW_POS_X, WINDOW_POS_Y)

    # --- UI setup ----------------------------------------------------------
    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(
            PANEL_PADDING, PANEL_PADDING, PANEL_PADDING, PANEL_PADDING
        )
        outer.setSpacing(GROUP_SPACING)

        top_bar = QHBoxLayout()
        top_bar.setSpacing(GROUP_SPACING)

        self.drag_handle = DragHandle()
        self.drag_handle.drag_started.connect(self._start_drag)
        top_bar.addWidget(self.drag_handle, alignment=Qt.AlignmentFlag.AlignLeft)

        if self.is_main:
            self.character_combo = QComboBox()
            self.character_combo.currentIndexChanged.connect(self.character_changed.emit)
            self.character_combo.setStyleSheet(
                "QComboBox {"
                " background-color: rgb(45, 45, 55);"
                " color: rgb(240, 240, 240);"
                " border: 1px solid rgb(80, 80, 95);"
                " border-radius: 4px;"
                " padding: 2px 8px;"
                "}"
                "QComboBox::drop-down { border: none; }"
                "QComboBox QAbstractItemView {"
                " background-color: rgb(45, 45, 55);"
                " color: rgb(240, 240, 240);"
                " selection-background-color: rgb(70, 70, 90);"
                "}"
            )
            top_bar.addWidget(self.character_combo, stretch=1)

            self.add_button = self._make_icon_button("+", "New window")
            self.add_button.clicked.connect(self.create_window_requested.emit)
            top_bar.addWidget(self.add_button, alignment=Qt.AlignmentFlag.AlignRight)

            self.lock_button = LockButton()
            self.lock_button.clicked.connect(self._on_lock_clicked)
            top_bar.addWidget(self.lock_button, alignment=Qt.AlignmentFlag.AlignRight)
        else:
            top_bar.addStretch(1)
            self.close_button = self._make_icon_button("\u00d7", "Close window")
            self.close_button.clicked.connect(self.close_requested.emit)
            top_bar.addWidget(self.close_button, alignment=Qt.AlignmentFlag.AlignRight)

        outer.addLayout(top_bar)
        self.top_bar_layout = top_bar

        self.content_layout = QVBoxLayout()
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(GROUP_SPACING)
        outer.addLayout(self.content_layout, stretch=1)

    def _make_icon_button(self, text: str, tooltip: str) -> QToolButton:
        button = QToolButton()
        button.setText(text)
        button.setFixedSize(LOCK_BUTTON_SIZE, LOCK_BUTTON_SIZE)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setToolTip(tooltip)
        button.setStyleSheet(
            "color: {}; background: transparent; border: none;"
            "font-size: 14px; font-weight: bold;".format(rgb(TEXT_COLOR))
        )
        return button

    # --- Content -----------------------------------------------------------
    def set_sections(self, sections) -> None:
        """Render the given (group title, rows) sections and auto-size."""
        while self.content_layout.count():
            item = self.content_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        for title, rows in sections:
            self.content_layout.addWidget(GroupWidget(title, rows))
        self.content_layout.addStretch(1)
        # Defer so the widgets are polished and size hints are correct.
        QTimer.singleShot(0, self._autosize)

    def set_characters(self, names, current_index: int) -> None:
        """Update the character selector (main window only)."""
        if not self.is_main:
            return
        self.character_combo.blockSignals(True)
        self.character_combo.clear()
        self.character_combo.addItems(names)
        self.character_combo.setCurrentIndex(current_index)
        self.character_combo.blockSignals(False)

    def _autosize(self) -> None:
        self.layout().activate()
        height = self.sizeHint().height()
        top_h = self.top_bar_layout.sizeHint().height()
        min_content = EMPTY_WINDOW_MIN_ROWS * ROW_HEIGHT_ESTIMATE
        min_height = PANEL_PADDING * 2 + top_h + GROUP_SPACING + min_content
        self.resize(WINDOW_WIDTH, max(height, min_height))

    # --- Lock / click-through ----------------------------------------------
    def is_locked(self) -> bool:
        return self._locked

    def _on_lock_clicked(self) -> None:
        self.lock_toggled.emit(not self._locked)

    def set_locked(self, locked: bool) -> None:
        self._locked = locked
        if self.is_main:
            self.lock_button.set_locked(locked)
        self._apply_click_through()

    def toggle_lock(self) -> None:
        self.set_locked(not self._locked)

    # --- Opacity -----------------------------------------------------------
    def opacity_percent(self) -> int:
        return round(self._background_alpha * 100 / 255)

    def set_opacity_percent(self, percent: int) -> None:
        self._background_alpha = round(int(percent) * 255 / 100)
        self.update()

    def _apply_click_through(self) -> None:
        """Make the window click-through when locked (except the lock button)."""
        if QGuiApplication.platformName() == "xcb":
            win_id = int(self.winId())
            if win_id:
                if self._locked:
                    if self.is_main:
                        # Input region = lock button only (window coordinates)
                        rects = [self.lock_button.geometry().getRect()]
                    else:
                        # Extra windows are fully click-through when locked
                        rects = []
                else:
                    # Input region = whole window
                    rects = [(0, 0, self.width(), self.height())]
                _set_input_shape(win_id, rects)
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

    # --- Drag & drop (target) ---------------------------------------------
    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasFormat(ROW_MIME_TYPE):
            event.acceptProposedAction()

    def dragMoveEvent(self, event) -> None:
        if event.mimeData().hasFormat(ROW_MIME_TYPE):
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:
        if event.mimeData().hasFormat(ROW_MIME_TYPE):
            row_id = bytes(event.mimeData().data(ROW_MIME_TYPE)).decode("utf-8")
            self.row_dropped.emit(row_id)
            event.acceptProposedAction()

    # --- Dragging the window ----------------------------------------------
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
        self.position_changed.emit()

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
        painter.setBrush(QColor(BACKGROUND_COLOR[0], BACKGROUND_COLOR[1], BACKGROUND_COLOR[2], self._background_alpha))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(self.rect(), CORNER_RADIUS, CORNER_RADIUS)
        painter.end()
