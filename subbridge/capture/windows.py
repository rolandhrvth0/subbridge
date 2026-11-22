"""Windows capture backend (ctypes only, no extra dependencies).

Windows: PrintWindow(PW_RENDERFULLCONTENT) – works while the window is covered by other windows and
for GPU-rendered (DirectX/OpenGL/Vulkan) content on Windows 8.1+. A minimised window has no picture,
that is reported as ``minimized``. Screens: BitBlt from the desktop DC.
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import os

import numpy as np

from .base import CaptureError, CaptureSource, WindowInfo

user32 = ctypes.WinDLL("user32", use_last_error=True)
gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
try:
    dwmapi = ctypes.WinDLL("dwmapi")
except OSError:          # pragma: no cover
    dwmapi = None

PW_CLIENTONLY, PW_RENDERFULLCONTENT = 0x1, 0x2
SRCCOPY, CAPTUREBLT = 0x00CC0020, 0x40000000
DIB_RGB_COLORS, BI_RGB = 0, 0
GWL_EXSTYLE, WS_EX_TOOLWINDOW = -20, 0x00000080
DWMWA_CLOAKED = 14
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

# pointer-sized handles: without explicit types ctypes truncates them to 32-bit ints on x64
user32.GetDC.restype = wt.HDC
user32.GetDC.argtypes = [wt.HWND]
user32.ReleaseDC.argtypes = [wt.HWND, wt.HDC]
user32.PrintWindow.argtypes = [wt.HWND, wt.HDC, wt.UINT]
user32.IsWindow.argtypes = user32.IsIconic.argtypes = user32.IsWindowVisible.argtypes = [wt.HWND]
user32.GetClientRect.argtypes = [wt.HWND, ctypes.POINTER(wt.RECT)]
user32.GetWindowTextLengthW.argtypes = [wt.HWND]
user32.GetWindowTextW.argtypes = [wt.HWND, wt.LPWSTR, ctypes.c_int]
user32.GetWindowLongW.argtypes = [wt.HWND, ctypes.c_int]
user32.GetWindowThreadProcessId.argtypes = [wt.HWND, ctypes.POINTER(wt.DWORD)]
gdi32.CreateCompatibleDC.restype = wt.HDC
gdi32.CreateCompatibleDC.argtypes = [wt.HDC]
gdi32.CreateCompatibleBitmap.restype = wt.HBITMAP
gdi32.CreateCompatibleBitmap.argtypes = [wt.HDC, ctypes.c_int, ctypes.c_int]
gdi32.SelectObject.restype = wt.HGDIOBJ
gdi32.SelectObject.argtypes = [wt.HDC, wt.HGDIOBJ]
gdi32.DeleteObject.argtypes = [wt.HGDIOBJ]
gdi32.DeleteDC.argtypes = [wt.HDC]
gdi32.BitBlt.argtypes = [wt.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wt.HDC,
                         ctypes.c_int, ctypes.c_int, wt.DWORD]
gdi32.GetDIBits.argtypes = [wt.HDC, wt.HBITMAP, wt.UINT, wt.UINT, ctypes.c_void_p, ctypes.c_void_p, wt.UINT]
user32.ClientToScreen.argtypes = [wt.HWND, ctypes.POINTER(wt.POINT)]
user32.GetForegroundWindow.restype = wt.HWND
kernel32.OpenProcess.restype = wt.HANDLE
kernel32.OpenProcess.argtypes = [wt.DWORD, wt.BOOL, wt.DWORD]
kernel32.QueryFullProcessImageNameW.argtypes = [wt.HANDLE, wt.DWORD, wt.LPWSTR, ctypes.POINTER(wt.DWORD)]
kernel32.CloseHandle.argtypes = [wt.HANDLE]
if dwmapi:
    dwmapi.DwmGetWindowAttribute.argtypes = [wt.HWND, wt.DWORD, ctypes.c_void_p, wt.DWORD]

EnumWindowsProc = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
MonitorEnumProc = ctypes.WINFUNCTYPE(wt.BOOL, wt.HMONITOR, wt.HDC, ctypes.POINTER(wt.RECT), wt.LPARAM)


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", wt.DWORD), ("biWidth", wt.LONG), ("biHeight", wt.LONG), ("biPlanes", wt.WORD),
                ("biBitCount", wt.WORD), ("biCompression", wt.DWORD), ("biSizeImage", wt.DWORD),
                ("biXPelsPerMeter", wt.LONG), ("biYPelsPerMeter", wt.LONG), ("biClrUsed", wt.DWORD),
                ("biClrImportant", wt.DWORD)]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", wt.DWORD * 3)]


def _dpi_aware():
    """Physical pixels everywhere, otherwise scaled monitors give blurry, offset captures."""
    try:
        user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))     # PER_MONITOR_AWARE_V2
        return
    except (AttributeError, OSError):
        pass
    try:
        ctypes.WinDLL("shcore").SetProcessDpiAwareness(2)
    except (AttributeError, OSError):
        user32.SetProcessDPIAware()


class WindowsCapture(CaptureSource):
    def __init__(self):
        _dpi_aware()
        self._own_pid = os.getpid()

    # ------------------------------------------------------------------ listing
    @staticmethod
    def _title(hwnd) -> str:
        n = user32.GetWindowTextLengthW(hwnd)
        if n <= 0:
            return ""
        buf = ctypes.create_unicode_buffer(n + 1)
        user32.GetWindowTextW(hwnd, buf, n + 1)
        return buf.value

    @staticmethod
    def _process(hwnd) -> tuple[int, str]:
        pid = wt.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        name = ""
        h = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
        if h:
            buf = ctypes.create_unicode_buffer(520)
            size = wt.DWORD(520)
            if kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
                name = os.path.splitext(os.path.basename(buf.value))[0]
            kernel32.CloseHandle(h)
        return pid.value, name

    @staticmethod
    def _cloaked(hwnd) -> bool:
        if not dwmapi:
            return False
        v = ctypes.c_int(0)
        dwmapi.DwmGetWindowAttribute(hwnd, DWMWA_CLOAKED, ctypes.byref(v), ctypes.sizeof(v))
        return bool(v.value)

    def list_windows(self) -> list[WindowInfo]:
        out: list[WindowInfo] = []

        def cb(hwnd, _):
            if not user32.IsWindowVisible(hwnd) or self._cloaked(hwnd):
                return True
            if user32.GetWindowLongW(hwnd, GWL_EXSTYLE) & WS_EX_TOOLWINDOW:
                return True
            title = self._title(hwnd)
            if not title:
                return True
            pid, app = self._process(hwnd)
            if pid == self._own_pid or app.lower() in ("explorer", "textinputhost", "applicationframehost"):
                return True
            out.append(WindowInfo(int(hwnd), title, app))
            return True

        user32.EnumWindows(EnumWindowsProc(cb), 0)
        return out

    def list_screens(self):
        mons: list[tuple[int, int, int, int]] = []

        def cb(_h, _dc, rc, _):
            r = rc.contents
            mons.append((r.left, r.top, r.right - r.left, r.bottom - r.top))
            return True

        user32.EnumDisplayMonitors(None, None, MonitorEnumProc(cb), 0)
        mons.sort(key=lambda m: (m[0] != 0 or m[1] != 0, m[0], m[1]))      # primary (at 0,0) first
        return mons or [(0, 0, user32.GetSystemMetrics(0), user32.GetSystemMetrics(1))]

    # ------------------------------------------------------------------ geometry
    def _hwnd(self, ident) -> int:
        hwnd = int(ident)
        if not user32.IsWindow(hwnd):
            raise CaptureError("A kiválasztott ablak bezárult.", "window_gone")
        if user32.IsIconic(hwnd):
            raise CaptureError("Az ablak le van kicsinyítve.", "minimized")
        return hwnd

    def source_size(self, kind, ident):
        if kind == "screen":
            screens = self.list_screens()
            x, y, w, h = screens[int(ident)] if int(ident) < len(screens) else screens[0]
            return w, h
        rc = wt.RECT()
        user32.GetClientRect(self._hwnd(ident), ctypes.byref(rc))
        return max(1, rc.right - rc.left), max(1, rc.bottom - rc.top)

    def origin(self, kind, ident):
        if kind == "screen":
            return super().origin(kind, ident)
        pt = wt.POINT(0, 0)
        user32.ClientToScreen(self._hwnd(ident), ctypes.byref(pt))
        return pt.x, pt.y

    def is_foreground(self, kind, ident):
        """The game is in front when the active window is the chosen one – or any other window of the
        same program (Remote Play apps often show the stream in a separate window from the one listed)."""
        if kind != "window":
            return True
        fg = int(user32.GetForegroundWindow() or 0)
        if not fg:
            return False
        if fg == int(ident):
            return True
        a, b = wt.DWORD(), wt.DWORD()
        user32.GetWindowThreadProcessId(fg, ctypes.byref(a))
        user32.GetWindowThreadProcessId(int(ident), ctypes.byref(b))
        return a.value != 0 and a.value == b.value

    # ------------------------------------------------------------------ grabbing
    @staticmethod
    def _bits(memdc, bmp, w, h) -> np.ndarray:
        bi = BITMAPINFO()
        bi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        bi.bmiHeader.biWidth, bi.bmiHeader.biHeight = w, -h          # top-down
        bi.bmiHeader.biPlanes, bi.bmiHeader.biBitCount, bi.bmiHeader.biCompression = 1, 32, BI_RGB
        buf = (ctypes.c_ubyte * (w * h * 4))()
        gdi32.GetDIBits(memdc, bmp, 0, h, buf, ctypes.byref(bi), DIB_RGB_COLORS)
        return np.frombuffer(buf, np.uint8).reshape(h, w, 4)

    def grab(self, kind, ident, rect=None):
        if kind == "screen":
            screens = self.list_screens()
            sx, sy, sw, sh = screens[int(ident)] if int(ident) < len(screens) else screens[0]
            x, y, w, h = rect or (0, 0, sw, sh)
            src = user32.GetDC(None)
            memdc = gdi32.CreateCompatibleDC(src)
            bmp = gdi32.CreateCompatibleBitmap(src, w, h)
            old = gdi32.SelectObject(memdc, bmp)
            try:
                gdi32.BitBlt(memdc, 0, 0, w, h, src, sx + x, sy + y, SRCCOPY | CAPTUREBLT)
                arr = self._bits(memdc, bmp, w, h)
            finally:
                gdi32.SelectObject(memdc, old)
                gdi32.DeleteObject(bmp)
                gdi32.DeleteDC(memdc)
                user32.ReleaseDC(None, src)
            return arr[..., 2::-1].copy()

        hwnd = self._hwnd(ident)
        cw, ch = self.source_size("window", hwnd)
        wdc = user32.GetDC(hwnd)
        memdc = gdi32.CreateCompatibleDC(wdc)
        bmp = gdi32.CreateCompatibleBitmap(wdc, cw, ch)
        old = gdi32.SelectObject(memdc, bmp)
        try:
            ok = user32.PrintWindow(hwnd, memdc, PW_CLIENTONLY | PW_RENDERFULLCONTENT)
            if not ok:
                raise CaptureError("Nem sikerült képet kérni az ablakról.", "generic")
            arr = self._bits(memdc, bmp, cw, ch)
        finally:
            gdi32.SelectObject(memdc, old)
            gdi32.DeleteObject(bmp)
            gdi32.DeleteDC(memdc)
            user32.ReleaseDC(hwnd, wdc)
        if rect:
            x, y, w, h = rect
            arr = arr[max(0, y):y + h, max(0, x):x + w]
        return arr[..., 2::-1].copy()          # BGRA -> RGB
