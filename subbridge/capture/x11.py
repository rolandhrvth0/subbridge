"""X11 capture with python-xlib. Window capture reads the window's own contents, so (with a
compositing window manager such as Cinnamon's Muffin) it works even when other windows cover it."""
from __future__ import annotations

import threading

import numpy as np
from Xlib import X, Xatom, display, error

from .base import CaptureError, CaptureSource, WindowInfo


class X11Capture(CaptureSource):
    def __init__(self):
        self._local = threading.local()
        try:
            from .x11_shm import ShmGrabber
            self._shm = ShmGrabber()
        except Exception:  # noqa: BLE001  (no libXext: plain XGetImage)
            self._shm = None
        d = self._d()
        self._atoms = {n: d.intern_atom(n) for n in (
            "_NET_CLIENT_LIST", "_NET_WM_NAME", "UTF8_STRING", "_NET_WM_STATE",
            "_NET_WM_STATE_HIDDEN", "WM_STATE", "_NET_WM_PID", "_NET_ACTIVE_WINDOW")}

    def _d(self) -> display.Display:
        d = getattr(self._local, "d", None)
        if d is None:
            try:
                d = self._local.d = display.Display()
            except Exception as e:  # noqa: BLE001
                raise CaptureError(f"Nem érem el az X kijelzőt: {e}", "no_display") from e
        return d

    # ------------------------------------------------------------ discovery
    def list_windows(self) -> list[WindowInfo]:
        d = self._d()
        root = d.screen().root
        prop = root.get_full_property(self._atoms["_NET_CLIENT_LIST"], X.AnyPropertyType)
        out = []
        for wid in (prop.value if prop else []):
            try:
                w = d.create_resource_object("window", wid)
                title = self._title(w)
                cls = w.get_wm_class()
                if title:
                    out.append(WindowInfo(int(wid), title, cls[1] if cls else ""))
            except error.XError:
                continue
        return out

    def _title(self, w) -> str:
        p = w.get_full_property(self._atoms["_NET_WM_NAME"], self._atoms["UTF8_STRING"])
        if p and p.value:
            v = p.value
            return v.decode("utf-8", "ignore") if isinstance(v, bytes) else str(v)
        name = w.get_wm_name()
        return name.decode("latin-1") if isinstance(name, bytes) else (name or "")

    def list_screens(self):
        d = self._d()
        root = d.screen().root
        try:
            mons = root.xrandr_get_monitors().monitors
            res = [(m.x, m.y, m.width_in_pixels, m.height_in_pixels) for m in mons]
            if res:
                return res
        except Exception:  # noqa: BLE001
            pass
        g = root.get_geometry()
        return [(0, 0, g.width, g.height)]

    # ------------------------------------------------------------ capture
    def _window(self, wid: int):
        d = self._d()
        w = d.create_resource_object("window", wid)
        try:
            attrs = w.get_attributes()
        except error.BadWindow as e:
            raise CaptureError("A kiválasztott ablak bezárult.", "window_gone") from e
        st = w.get_full_property(self._atoms["_NET_WM_STATE"], Xatom.ATOM)
        hidden = st is not None and self._atoms["_NET_WM_STATE_HIDDEN"] in st.value
        if hidden or attrs.map_state != X.IsViewable:
            raise CaptureError("A kiválasztott ablak le van kicsinyítve.", "minimized")
        return w

    def source_size(self, kind, ident):
        if kind == "window":
            g = self._window(int(ident)).get_geometry()
            return g.width, g.height
        screens = self.list_screens()
        x, y, w, h = screens[min(int(ident or 0), len(screens) - 1)]
        return w, h

    def origin(self, kind, ident):
        if kind != "window":
            return super().origin(kind, ident)
        d = self._d()
        try:
            c = d.screen().root.translate_coords(self._window(int(ident)), 0, 0)
        except error.XError as e:
            raise CaptureError("A kiválasztott ablak bezárult.", "window_gone") from e
        return c.x, c.y

    def is_foreground(self, kind, ident):
        if kind != "window":
            return True
        try:
            p = self._d().screen().root.get_full_property(self._atoms["_NET_ACTIVE_WINDOW"], X.AnyPropertyType)
            return bool(p and p.value and int(p.value[0]) == int(ident))
        except error.XError:
            return True

    def grab(self, kind, ident, rect=None):
        d = self._d()
        if kind == "window":
            drawable = self._window(int(ident))
            g = drawable.get_geometry()
            ox, oy, sw, sh = 0, 0, g.width, g.height
        else:
            drawable = d.screen().root
            screens = self.list_screens()
            ox, oy, sw, sh = screens[min(int(ident or 0), len(screens) - 1)]
        if rect is None:
            rect = (0, 0, sw, sh)
        x, y, w, h = rect
        x, y = max(0, min(x, sw - 1)), max(0, min(y, sh - 1))
        w, h = max(1, min(w, sw - x)), max(1, min(h, sh - y))
        if self._shm is not None:
            from .x11_shm import ShmError
            try:
                return self._shm.grab(int(drawable.id), ox + x, oy + y, w, h)
            except ShmError:
                pass
        try:
            raw = drawable.get_image(ox + x, oy + y, w, h, X.ZPixmap, 0xFFFFFFFF)
        except error.XError as e:
            raise CaptureError("Nem sikerült képet venni az ablakról.", "grab_failed") from e
        depth = 4
        arr = np.frombuffer(raw.data, dtype=np.uint8)
        if arr.size != w * h * depth:
            raise CaptureError("Váratlan képformátum.", "grab_failed")
        arr = arr.reshape(h, w, depth)
        return arr[..., 2::-1].copy()     # BGRX -> RGB
