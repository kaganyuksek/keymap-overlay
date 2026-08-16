"""
Cross-platform window enumeration and foreground-window detection.

Supported platforms: Linux (X11/XWayland) and Windows (Win32).
Each window is described by a stable id and a title.
"""

import sys

import ctypes


def is_supported() -> bool:
    return sys.platform.startswith("linux") or sys.platform == "win32"


def list_windows():
    """Return a list of {"id": str, "title": str} for visible top-level windows."""
    if sys.platform.startswith("linux"):
        return _x11_list_windows()
    if sys.platform == "win32":
        return _win32_list_windows()
    return []


def foreground_title():
    """Return the title of the currently focused window, or None if unknown."""
    if sys.platform.startswith("linux"):
        return _x11_foreground_title()
    if sys.platform == "win32":
        return _win32_foreground_title()
    return None


def foreground_id():
    """Return the raw id of the focused window, or None if unknown.

    On Linux this is the X11 window id; on Windows the HWND. A native Wayland
    window is reported with a sentinel id that has no X11 title.
    """
    if sys.platform.startswith("linux"):
        return _x11_foreground_id()
    if sys.platform == "win32":
        return _win32_foreground_id()
    return None


# --- Linux / X11 ----------------------------------------------------------

_X_ERROR_HANDLER = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p)
_X_ERROR_HANDLER_REF = None
_XLIB = None
_DPY = None


def _ignore_x_error(_display, _event):
    # Ignore errors (e.g. BadWindow when a window is closed mid-enumeration).
    return 0


def _x11():
    global _XLIB, _DPY
    if _DPY:
        return _XLIB, _DPY

    xlib = ctypes.CDLL("libX11.so.6")
    xlib.XOpenDisplay.restype = ctypes.c_void_p
    xlib.XOpenDisplay.argtypes = [ctypes.c_char_p]
    xlib.XDefaultRootWindow.restype = ctypes.c_ulong
    xlib.XDefaultRootWindow.argtypes = [ctypes.c_void_p]
    xlib.XInternAtom.restype = ctypes.c_ulong
    xlib.XInternAtom.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int]
    xlib.XGetWindowProperty.restype = ctypes.c_int
    xlib.XGetWindowProperty.argtypes = [
        ctypes.c_void_p,
        ctypes.c_ulong,
        ctypes.c_ulong,
        ctypes.c_long,
        ctypes.c_long,
        ctypes.c_int,
        ctypes.c_ulong,
        ctypes.POINTER(ctypes.c_ulong),
        ctypes.POINTER(ctypes.c_int),
        ctypes.POINTER(ctypes.c_ulong),
        ctypes.POINTER(ctypes.c_ulong),
        ctypes.POINTER(ctypes.POINTER(ctypes.c_ubyte)),
    ]
    xlib.XFree.argtypes = [ctypes.c_void_p]
    xlib.XFetchName.restype = ctypes.c_int
    xlib.XFetchName.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.POINTER(ctypes.c_char_p)]

    # Install an error handler so stale windows don't abort the process.
    xlib.XSetErrorHandler.restype = ctypes.c_void_p
    xlib.XSetErrorHandler.argtypes = [ctypes.c_void_p]
    global _X_ERROR_HANDLER_REF
    _X_ERROR_HANDLER_REF = _X_ERROR_HANDLER(_ignore_x_error)
    xlib.XSetErrorHandler(_X_ERROR_HANDLER_REF)

    dpy = xlib.XOpenDisplay(None)
    if not dpy:
        return None, None
    _XLIB = xlib
    _DPY = dpy
    return xlib, dpy


def _x11_get_property(xlib, dpy, win, atom):
    actual_type = ctypes.c_ulong()
    actual_format = ctypes.c_int()
    nitems = ctypes.c_ulong()
    bytes_after = ctypes.c_ulong()
    data = ctypes.POINTER(ctypes.c_ubyte)()
    r = xlib.XGetWindowProperty(
        dpy, win, atom, 0, 0x7FFFFFFF, 0, 0,
        ctypes.byref(actual_type),
        ctypes.byref(actual_format),
        ctypes.byref(nitems),
        ctypes.byref(bytes_after),
        ctypes.byref(data),
    )
    if r != 0 or not data or nitems.value == 0:
        return None
    try:
        if actual_format.value == 32:
            arr = ctypes.cast(data, ctypes.POINTER(ctypes.c_uint32))
            return [arr[i] for i in range(nitems.value)]
        if actual_format.value == 8:
            return bytes(data[: nitems.value])
        return bytes(data[: nitems.value * (actual_format.value // 8)])
    finally:
        xlib.XFree(data)


def _x11_window_title(xlib, dpy, win):
    if not win:
        return ""
    net_wm_name = xlib.XInternAtom(dpy, b"_NET_WM_NAME", 0)
    utf8 = xlib.XInternAtom(dpy, b"UTF8_STRING", 0)

    # Prefer _NET_WM_NAME (UTF8).
    actual_type = ctypes.c_ulong()
    actual_format = ctypes.c_int()
    nitems = ctypes.c_ulong()
    bytes_after = ctypes.c_ulong()
    data = ctypes.POINTER(ctypes.c_ubyte)()
    r = xlib.XGetWindowProperty(
        dpy, win, net_wm_name, 0, 0x7FFFFFFF, 0, utf8,
        ctypes.byref(actual_type),
        ctypes.byref(actual_format),
        ctypes.byref(nitems),
        ctypes.byref(bytes_after),
        ctypes.byref(data),
    )
    if r == 0 and data and nitems.value > 0:
        title = bytes(data[: nitems.value]).decode("utf-8", errors="replace")
        xlib.XFree(data)
        if title.strip():
            return title

    # Fallback to WM_NAME.
    name = ctypes.c_char_p()
    if xlib.XFetchName(dpy, win, ctypes.byref(name)) and name.value:
        title = name.value.decode("utf-8", errors="replace")
        xlib.XFree(name)
        return title
    return ""


def _x11_list_windows():
    xlib, dpy = _x11()
    if not dpy:
        return []
    root = xlib.XDefaultRootWindow(dpy)
    net_client_list = xlib.XInternAtom(dpy, b"_NET_CLIENT_LIST", 0)

    ids = _x11_get_property(xlib, dpy, root, net_client_list) or []
    windows = []
    for wid in ids:
        title = _x11_window_title(xlib, dpy, wid)
        if title.strip():
            windows.append({"id": f"x11:{wid}", "title": title})
    return windows


def _x11_foreground_title():
    xlib, dpy = _x11()
    if not dpy:
        return None
    root = xlib.XDefaultRootWindow(dpy)
    net_active = xlib.XInternAtom(dpy, b"_NET_ACTIVE_WINDOW", 0)
    ids = _x11_get_property(xlib, dpy, root, net_active)
    if not ids:
        return None
    return _x11_window_title(xlib, dpy, ids[0]) or None


def _x11_foreground_id():
    xlib, dpy = _x11()
    if not dpy:
        return None
    root = xlib.XDefaultRootWindow(dpy)
    net_active = xlib.XInternAtom(dpy, b"_NET_ACTIVE_WINDOW", 0)
    ids = _x11_get_property(xlib, dpy, root, net_active)
    if not ids:
        return None
    return int(ids[0])


# --- Windows / Win32 ------------------------------------------------------

def _win32_list_windows():
    import ctypes

    user32 = ctypes.windll.user32
    results = []
    proc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

    def callback(hwnd, _lparam):
        if user32.IsWindowVisible(hwnd):
            length = user32.GetWindowTextLengthW(hwnd)
            if length:
                buf = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buf, length + 1)
                title = buf.value.strip()
                if title:
                    results.append({"id": f"win:{hwnd}", "title": title})
        return True

    user32.EnumWindows(proc(callback), 0)
    return results


def _win32_foreground_title():
    import ctypes

    user32 = ctypes.windll.user32
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return None
    length = user32.GetWindowTextLengthW(hwnd)
    if not length:
        return None
    buf = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buf, length + 1)
    return buf.value


def _win32_foreground_id():
    import ctypes

    user32 = ctypes.windll.user32
    hwnd = user32.GetForegroundWindow()
    return int(hwnd) if hwnd else None
