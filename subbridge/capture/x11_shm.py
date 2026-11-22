"""Fast X11 window/screen grabs through the MIT-SHM extension (libX11/libXext via ctypes).

A plain XGetImage of a large window ships every pixel over the X connection (60–140 ms for 3440×1440)
and holds the X server meanwhile – the game window visibly hitches. XShmGetImage copies into shared
memory instead: a few milliseconds, no stall. Each thread gets its own Display connection and buffers."""
from __future__ import annotations

import ctypes
import ctypes.util
import threading

import numpy as np

_x11 = ctypes.CDLL(ctypes.util.find_library("X11") or "libX11.so.6")
_xext = ctypes.CDLL(ctypes.util.find_library("Xext") or "libXext.so.6")
_libc = ctypes.CDLL(ctypes.util.find_library("c") or "libc.so.6", use_errno=True)

ZPixmap, IPC_PRIVATE, IPC_CREAT, IPC_RMID = 2, 0, 0o1000, 0
ALL_PLANES = ctypes.c_ulong(0xFFFFFFFF)


class XImage(ctypes.Structure):
    _fields_ = [("width", ctypes.c_int), ("height", ctypes.c_int), ("xoffset", ctypes.c_int),
                ("format", ctypes.c_int), ("data", ctypes.c_void_p), ("byte_order", ctypes.c_int),
                ("bitmap_unit", ctypes.c_int), ("bitmap_bit_order", ctypes.c_int), ("bitmap_pad", ctypes.c_int),
                ("depth", ctypes.c_int), ("bytes_per_line", ctypes.c_int), ("bits_per_pixel", ctypes.c_int),
                ("red_mask", ctypes.c_ulong), ("green_mask", ctypes.c_ulong), ("blue_mask", ctypes.c_ulong),
                ("obdata", ctypes.c_void_p), ("f", ctypes.c_void_p * 6)]


class XShmSegmentInfo(ctypes.Structure):
    _fields_ = [("shmseg", ctypes.c_ulong), ("shmid", ctypes.c_int), ("shmaddr", ctypes.c_void_p),
                ("readOnly", ctypes.c_int)]


class XWindowAttributes(ctypes.Structure):
    _fields_ = [("x", ctypes.c_int), ("y", ctypes.c_int), ("width", ctypes.c_int), ("height", ctypes.c_int),
                ("border_width", ctypes.c_int), ("depth", ctypes.c_int), ("visual", ctypes.c_void_p),
                ("root", ctypes.c_ulong), ("class_", ctypes.c_int), ("bit_gravity", ctypes.c_int),
                ("win_gravity", ctypes.c_int), ("backing_store", ctypes.c_int), ("backing_planes", ctypes.c_ulong),
                ("backing_pixel", ctypes.c_ulong), ("save_under", ctypes.c_int), ("colormap", ctypes.c_ulong),
                ("map_installed", ctypes.c_int), ("map_state", ctypes.c_int), ("all_event_masks", ctypes.c_long),
                ("your_event_mask", ctypes.c_long), ("do_not_propagate_mask", ctypes.c_long),
                ("override_redirect", ctypes.c_int), ("screen", ctypes.c_void_p)]


_x11.XOpenDisplay.restype = ctypes.c_void_p
_x11.XOpenDisplay.argtypes = [ctypes.c_char_p]
_x11.XDefaultRootWindow.restype = ctypes.c_ulong
_x11.XDefaultRootWindow.argtypes = [ctypes.c_void_p]
_x11.XGetWindowAttributes.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.POINTER(XWindowAttributes)]
_x11.XSync.argtypes = [ctypes.c_void_p, ctypes.c_int]
_xext.XShmQueryExtension.argtypes = [ctypes.c_void_p]
_xext.XShmCreateImage.restype = ctypes.POINTER(XImage)
_xext.XShmCreateImage.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint, ctypes.c_int, ctypes.c_void_p,
                                  ctypes.POINTER(XShmSegmentInfo), ctypes.c_uint, ctypes.c_uint]
_xext.XShmAttach.argtypes = [ctypes.c_void_p, ctypes.POINTER(XShmSegmentInfo)]
_xext.XShmDetach.argtypes = [ctypes.c_void_p, ctypes.POINTER(XShmSegmentInfo)]
_xext.XShmGetImage.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.POINTER(XImage), ctypes.c_int, ctypes.c_int,
                               ctypes.c_ulong]
_libc.shmget.argtypes = [ctypes.c_int, ctypes.c_size_t, ctypes.c_int]
_libc.shmat.restype = ctypes.c_void_p
_libc.shmat.argtypes = [ctypes.c_int, ctypes.c_void_p, ctypes.c_int]
_libc.shmdt.argtypes = [ctypes.c_void_p]
_libc.shmctl.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_void_p]

# Xlib's default error handler terminates the process; record errors instead.
_ERRHANDLER = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p)
_last_error = threading.local()


@_ERRHANDLER
def _on_error(_dpy, _ev):
    _last_error.flag = True
    return 0


_x11.XSetErrorHandler(_on_error)


class ShmError(Exception):
    pass


class _Buffer:
    def __init__(self, dpy, visual, depth, w, h):
        self.info = XShmSegmentInfo()
        self.img = _xext.XShmCreateImage(dpy, visual, depth, ZPixmap, None, ctypes.byref(self.info), w, h)
        if not self.img:
            raise ShmError("XShmCreateImage failed")
        size = self.img.contents.bytes_per_line * h
        self.info.shmid = _libc.shmget(IPC_PRIVATE, size, IPC_CREAT | 0o600)
        if self.info.shmid < 0:
            raise ShmError("shmget failed")
        addr = _libc.shmat(self.info.shmid, None, 0)
        if addr in (None, ctypes.c_void_p(-1).value):
            raise ShmError("shmat failed")
        self.info.shmaddr = addr
        self.img.contents.data = addr
        self.info.readOnly = 0
        _last_error.flag = False
        _xext.XShmAttach(dpy, ctypes.byref(self.info))
        _x11.XSync(dpy, 0)
        _libc.shmctl(self.info.shmid, IPC_RMID, None)      # freed automatically once both sides detach
        if getattr(_last_error, "flag", False):
            raise ShmError("XShmAttach failed (remote display?)")
        self.dpy, self.size, self.w, self.h = dpy, size, w, h

    def free(self):
        try:
            _xext.XShmDetach(self.dpy, ctypes.byref(self.info))
            _x11.XSync(self.dpy, 0)
            _libc.shmdt(self.info.shmaddr)
        except Exception:  # noqa: BLE001
            pass


class ShmGrabber:
    """grab(drawable, x, y, w, h) -> RGB uint8 array, or raises ShmError (caller falls back)."""

    def __init__(self):
        self._tls = threading.local()

    def _state(self):
        st = getattr(self._tls, "st", None)
        if st is None:
            dpy = _x11.XOpenDisplay(None)
            if not dpy or not _xext.XShmQueryExtension(dpy):
                raise ShmError("MIT-SHM not available")
            st = self._tls.st = {"dpy": dpy, "bufs": {}}
        return st

    def grab(self, drawable: int, x: int, y: int, w: int, h: int) -> np.ndarray:
        st = self._state()
        dpy = st["dpy"]
        attrs = XWindowAttributes()
        _last_error.flag = False
        if not _x11.XGetWindowAttributes(dpy, drawable, ctypes.byref(attrs)) or getattr(_last_error, "flag", False):
            raise ShmError("window attributes")
        key = (drawable, attrs.depth, attrs.visual, w, h)
        buf = st["bufs"].get(key)
        if buf is None:
            for k in [k for k in st["bufs"] if k[0] == drawable]:     # size changed: drop old buffers
                st["bufs"].pop(k).free()
            if len(st["bufs"]) > 6:
                st["bufs"].pop(next(iter(st["bufs"]))).free()
            buf = st["bufs"][key] = _Buffer(dpy, attrs.visual, attrs.depth, w, h)
        _last_error.flag = False
        ok = _xext.XShmGetImage(dpy, drawable, buf.img, x, y, ALL_PLANES)
        if not ok or getattr(_last_error, "flag", False):
            raise ShmError("XShmGetImage failed")
        im = buf.img.contents
        if im.bits_per_pixel != 32:
            raise ShmError(f"unsupported pixel size {im.bits_per_pixel}")
        raw = np.ctypeslib.as_array(ctypes.cast(buf.info.shmaddr, ctypes.POINTER(ctypes.c_uint8)), (buf.size,))
        arr = raw.reshape(h, im.bytes_per_line)[:, : w * 4].reshape(h, w, 4)
        return arr[..., 2::-1].copy()                                 # BGRX -> RGB (copy: buffer is reused)
