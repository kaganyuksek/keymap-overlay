"""
Overlay window.

- Frameless, always-on-top, semi-transparent background (rounded rect drawn in paintEvent).
- Dragging is done from the "move" handle in the top-left corner.
- "Locked/click-through" mode: on X11 the window input region is restricted to the
  lock button (main window) so the rest of the window passes clicks through while
  the lock button always remains clickable. Extra windows become fully click-through.
- The main window holds the profile selector, the lock button and a "+" button
  to create extra windows; extra windows hold a close button.
- Content is a set of (group title, rows) sections; the window auto-sizes to its
  content (grows downward) instead of scrolling.
"""

import ctypes
import math

from PyQt6.QtCore import QPoint, QPointF, QRectF, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QGuiApplication, QPainter, QPen, QPolygonF
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
    COLUMN_SPACING,
    CORNER_RADIUS,
    DRAG_HANDLE_COLOR,
    DRAG_HANDLE_SIZE,
    EMPTY_WINDOW_MIN_ROWS,
    FONT_FAMILY,
    FONT_SIZE_HOTKEY,
    FONT_SIZE_KEY,
    GROUP_SPACING,
    ICON_SIZE,
    ICON_TEXT_SPACING,
    LOCK_BUTTON_SIZE,
    LOCKED_COLOR,
    MIN_ROWS_PER_COLUMN,
    PANEL_PADDING,
    RESIZE_HANDLE_WIDTH,
    ROW_COLUMN_WIDTH,
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
from ui.flow_layout import FlowLayout
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


class ResizeHandle(QWidget):
    """Vertical grab strip on the right edge used to resize the width."""

    resize_started = pyqtSignal(QPoint)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setCursor(Qt.CursorShape.SizeHorCursor)
        self.setToolTip("Resize width")

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.resize_started.emit(event.globalPosition().toPoint())
        event.accept()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QColor(*DRAG_HANDLE_COLOR))
        painter.setPen(Qt.PenStyle.NoPen)

        w = 3
        h = min(44, self.height() - 8)
        x = (self.width() - w) / 2.0
        y = (self.height() - h) / 2.0
        painter.drawRoundedRect(QRectF(x, y, w, h), 1.5, 1.5)
        painter.end()


class OverlayWindow(QWidget):
    """Frameless, draggable, semi-transparent hotkey reference panel."""

    profile_changed = pyqtSignal(int)
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
        self._resize_origin = None
        self._width = WINDOW_WIDTH
        self._sections = []
        self._total_cols = None
        self._columns = []
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
            self.profile_combo = QComboBox()
            self.profile_combo.currentIndexChanged.connect(self.profile_changed.emit)
            self.profile_combo.setStyleSheet(
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
            top_bar.addWidget(self.profile_combo, stretch=1)

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

        self.content_layout = FlowLayout(spacing=COLUMN_SPACING)
        outer.addLayout(self.content_layout, stretch=1)

        self.resize_handle = ResizeHandle(self)
        self.resize_handle.resize_started.connect(self._start_resize)
        self.resize_handle.setVisible(False)

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
        """Store the given (group title, rows) sections and re-render."""
        self._sections = sections
        self._total_cols = None
        # Defer so the widgets are polished and size hints are correct.
        QTimer.singleShot(0, self._autosize)

    def set_profiles(self, names, current_index: int) -> None:
        """Update the profile selector (main window only)."""
        if not self.is_main:
            return
        self.profile_combo.blockSignals(True)
        self.profile_combo.clear()
        self.profile_combo.addItems(names)
        self.profile_combo.setCurrentIndex(current_index)
        self.profile_combo.blockSignals(False)

    def _clear_content(self) -> None:
        while self.content_layout.count():
            item = self.content_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _column_width(self) -> int:
        """Estimate the natural width of the widest hotkey row."""
        key_font = QFont(FONT_FAMILY, FONT_SIZE_KEY)
        key_font.setBold(True)
        label_font = QFont(FONT_FAMILY, FONT_SIZE_HOTKEY)
        key_fm = QFontMetrics(key_font)
        label_fm = QFontMetrics(label_font)
        max_w = 0
        for _, rows in self._sections:
            for r in rows:
                icon_w = ICON_SIZE + ICON_TEXT_SPACING if r.get("icon") else 0
                badge_w = max(
                    ICON_SIZE * 2,
                    key_fm.horizontalAdvance(str(r.get("key", ""))) + 8,
                )
                label_w = label_fm.horizontalAdvance(str(r.get("label", "")))
                max_w = max(max_w, icon_w + badge_w + ICON_TEXT_SPACING + label_w)
        return max(ROW_COLUMN_WIDTH, max_w)

    def _cols_fit(self) -> int:
        inner_w = max(1, self._width - 2 * PANEL_PADDING)
        col_w = self._column_width()
        return max(1, (inner_w + COLUMN_SPACING) // (col_w + COLUMN_SPACING))

    def _distribute_columns(self, counts: list) -> list:
        """Assign columns to categories, prioritizing categories side by side.

        Each category gets at least one column (so categories sit next to each
        other first); leftover columns are handed out proportionally to row
        counts. The total is capped so every column holds at least
        MIN_ROWS_PER_COLUMN rows.
        """
        n = len(counts)
        if n == 0:
            return []
        total = sum(counts)
        cols_fit = self._cols_fit()
        max_cols = max(1, (total + MIN_ROWS_PER_COLUMN - 1) // MIN_ROWS_PER_COLUMN)
        cols = min(cols_fit, max_cols)
        if cols <= n or total == 0:
            return [1] * n
        remaining = cols - n
        frac = [c * remaining / total for c in counts]
        floors = [int(f) for f in frac]
        extra = remaining - sum(floors)
        order = sorted(range(n), key=lambda i: frac[i] - floors[i], reverse=True)
        for i in order[:extra]:
            floors[i] += 1
        return [1 + floors[i] for i in range(n)]

    def _fill_width(self, total_cols: int) -> int:
        cols_per_line = min(total_cols, self._cols_fit())
        inner_w = max(1, self._width - 2 * PANEL_PADDING)
        return max(1, (inner_w - (cols_per_line - 1) * COLUMN_SPACING) // cols_per_line)

    def _rebuild_content(self) -> None:
        self._clear_content()
        self._columns = []
        counts = [len(rows) for _, rows in self._sections]
        cols_per_cat = self._distribute_columns(counts)
        total_cols = max(1, sum(cols_per_cat))
        fill_w = self._fill_width(total_cols)
        for ci, (title, rows) in enumerate(self._sections):
            g = len(rows)
            c = cols_per_cat[ci]
            per = math.ceil(g / c) if g > 0 and c > 0 else 0
            first = True
            if not rows:
                col = GroupWidget(title, [], show_header=True, min_width=fill_w)
                self.content_layout.addWidget(col)
                self._columns.append(col)
                continue
            for i in range(0, g, per):
                chunk = rows[i:i + per]
                col = GroupWidget(title, chunk, show_header=first, min_width=fill_w)
                self.content_layout.addWidget(col)
                self._columns.append(col)
                first = False

    def _apply_fill_width(self) -> None:
        fill_w = self._fill_width(self._total_cols)
        for col in self._columns:
            col.setMinimumWidth(fill_w)
        self.content_layout.invalidate()

    def _resize_to_fit(self) -> None:
        top_h = self.top_bar_layout.sizeHint().height()
        inner_w = max(1, self._width - 2 * PANEL_PADDING)
        content_h = self.content_layout.heightForWidth(inner_w)
        min_content = EMPTY_WINDOW_MIN_ROWS * ROW_HEIGHT_ESTIMATE
        min_height = PANEL_PADDING * 2 + top_h + GROUP_SPACING + min_content
        total_h = PANEL_PADDING * 2 + top_h + GROUP_SPACING + content_h
        self.resize(self._width, max(total_h, min_height))
        self._position_resize_handle()

    def _autosize(self) -> None:
        self._relayout()

    def _relayout(self) -> None:
        """Re-flow the content for the current width and fit the height."""
        self._width = max(WINDOW_WIDTH, self._width)
        counts = [len(rows) for _, rows in self._sections]
        total_cols = max(1, sum(self._distribute_columns(counts)))
        if total_cols != self._total_cols:
            self._total_cols = total_cols
            self._rebuild_content()
        else:
            self._apply_fill_width()
        # Defer the resize: freshly built widgets have no valid size hints yet,
        # so fitting synchronously would size the window incorrectly.
        QTimer.singleShot(0, self._resize_to_fit)

    def set_width(self, width: int) -> None:
        self._width = max(WINDOW_WIDTH, int(width))
        self._relayout()

    def _position_resize_handle(self) -> None:
        self.resize_handle.setGeometry(
            self.width() - RESIZE_HANDLE_WIDTH,
            0,
            RESIZE_HANDLE_WIDTH,
            self.height(),
        )
        self.resize_handle.raise_()

    # --- Lock / click-through ----------------------------------------------
    def is_locked(self) -> bool:
        return self._locked

    def _on_lock_clicked(self) -> None:
        self.lock_toggled.emit(not self._locked)

    def set_locked(self, locked: bool) -> None:
        self._locked = locked
        if self.is_main:
            self.lock_button.set_locked(locked)
        self.resize_handle.setVisible(not locked)
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
        self._position_resize_handle()
        if self._locked:
            # Keep the click-through region (lock button only) in sync.
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

    def _start_resize(self, global_pos) -> None:
        self._resize_origin = (global_pos.x(), self._width)
        self.grabMouse()

    def _move_resize(self, global_pos) -> None:
        if self._resize_origin is None:
            return
        start_x, start_width = self._resize_origin
        self._width = max(WINDOW_WIDTH, start_width + (global_pos.x() - start_x))
        self._relayout()

    def _end_resize(self) -> None:
        self._resize_origin = None
        self.releaseMouse()
        self._apply_click_through()
        self.position_changed.emit()

    def mouseMoveEvent(self, event) -> None:
        if self._drag_offset is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self._move_drag(event.globalPosition().toPoint())
            event.accept()
        elif self._resize_origin is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self._move_resize(event.globalPosition().toPoint())
            event.accept()
        else:
            event.ignore()

    def mouseReleaseEvent(self, event) -> None:
        if self._drag_offset is not None:
            self._end_drag()
        if self._resize_origin is not None:
            self._end_resize()

    # --- Background painting -----------------------------------------------
    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QColor(BACKGROUND_COLOR[0], BACKGROUND_COLOR[1], BACKGROUND_COLOR[2], self._background_alpha))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(self.rect(), CORNER_RADIUS, CORNER_RADIUS)
        painter.end()
