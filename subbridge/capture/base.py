from __future__ import annotations

import sys
from dataclasses import dataclass

import numpy as np


class CaptureError(Exception):
    """User-readable capture problem. ``code`` selects the help text in the UI."""

    def __init__(self, message: str, code: str = "generic"):
        super().__init__(message)
        self.code = code


@dataclass
class WindowInfo:
    id: int
    title: str
    app: str = ""


class CaptureSource:
    """Backend interface. All coordinates are in pixels of the source (screen or window)."""

    def list_windows(self) -> list[WindowInfo]:
        return []

    def list_screens(self) -> list[tuple[int, int, int, int]]:
        return []

    def source_size(self, kind: str, ident) -> tuple[int, int]:
        raise NotImplementedError

    def grab(self, kind: str, ident, rect: tuple[int, int, int, int] | None = None) -> np.ndarray:
        """Return an RGB uint8 array. ``rect`` = (x, y, w, h) inside the source."""
        raise NotImplementedError

    def origin(self, kind: str, ident) -> tuple[int, int]:
        """Top-left of the source in desktop (physical) pixels – used to place the in-game overlay."""
        if kind == "screen":
            screens = self.list_screens()
            x, y, _w, _h = screens[min(int(ident or 0), len(screens) - 1)]
            return x, y
        raise NotImplementedError

    def is_foreground(self, kind: str, ident) -> bool:
        """Is the source window the active one? (The overlay hides while you use other programs.)"""
        return True

    def close(self) -> None:
        pass


def create_backend() -> CaptureSource:
    if sys.platform.startswith("linux"):
        import os
        if os.environ.get("XDG_SESSION_TYPE") == "wayland" and not os.environ.get("DISPLAY"):
            raise CaptureError("Wayland-only session: run under XWayland or an X11 session.", "wayland")
        from .x11 import X11Capture
        return X11Capture()
    if sys.platform == "win32":
        from .windows import WindowsCapture
        return WindowsCapture()
    from .mss_backend import MssCapture
    return MssCapture()
