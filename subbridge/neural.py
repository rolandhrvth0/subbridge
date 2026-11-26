"""Experimental (local only): DLSS 5 neural rendering of the capture-card picture on AMD RDNA4 under Linux,
through the DLSSNR-AMD Vulkan runtime (a separate worker program, `sb-nr`).

Nothing of NVIDIA's ships with SubBridge: the worker and the model (extracted from the user's own
nvngx_dlssnr.dll) live in ~/.local/share/subbridge/nr/. When that folder is missing the feature is not offered.

The worker gets each real game picture (30 fps; the 60 Hz card's repeats are not sent) through a shared memory
file and hands the result back; the Game View shows the result, and frame generation runs after it. If the
worker is busy, dies or takes too long, the plain picture is shown – the Game View never waits on it.
"""
from __future__ import annotations

import logging
import mmap
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import numpy as np

log = logging.getLogger(__name__)


def nr_dir() -> Path:
    from .nrsetup import data_dir
    return data_dir()


def available() -> bool:
    """DLSS 5 can be switched on: Linux, the worker shipped, the user's model extracted."""
    from . import nrsetup
    return nrsetup.platform_ok() and nrsetup.worker().is_file() and nrsetup.model_ready()


class NeuralWorker:
    """One sb-nr process for one frame size. process(rgba) -> rgba (blocking, ~15 ms at 1440p) or None."""

    def __init__(self, width: int, height: int, temporal: bool = False):
        self.w, self.h = width, height
        self.bytes = width * height * 4
        self.ok = False
        self.ms = 0.0
        self.error = ""
        self._lock = threading.Lock()
        shm_dir = Path("/dev/shm") if Path("/dev/shm").is_dir() else Path("/tmp")
        self._shm_path = shm_dir / f"subbridge-nr-{os.getpid()}-{width}x{height}"
        with open(self._shm_path, "wb") as f:
            f.truncate(self.bytes * 2)
        self._fd = os.open(self._shm_path, os.O_RDWR)
        self._map = mmap.mmap(self._fd, self.bytes * 2)
        self._in = np.frombuffer(self._map, np.uint8, self.bytes, 0).reshape(height, width, 4)
        self._out = np.frombuffer(self._map, np.uint8, self.bytes, self.bytes).reshape(height, width, 4)
        from .capture.device import _clean_env, _die_with_parent
        env = _clean_env()
        env["NR_GPU"] = env.get("NR_GPU", "0")
        env["DISABLE_MANGOHUD"] = "1"
        env["SB_TEMPORAL"] = "1" if temporal else "0"
        d = nr_dir()
        from . import nrsetup
        self.proc = subprocess.Popen([str(nrsetup.worker("sb-nr")), str(d), str(width), str(height), str(self._shm_path)],
                                     stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                     text=True, bufsize=1, env=env, preexec_fn=_die_with_parent)
        self._ready = threading.Event()
        threading.Thread(target=self._wait_ready, daemon=True, name="nr-start").start()

    def _reply(self) -> str:
        """Next protocol line; the runtime's own log lines ("[nr] ...") go to our log."""
        while True:
            line = self.proc.stdout.readline()
            if not line:
                return ""
            line = line.strip()
            if line.startswith(("ready", "done", "err")):
                return line
            if line:
                log.debug("sb-nr: %s", line)

    def _wait_ready(self):
        line = self._reply()
        if line.startswith("ready"):
            self.ok = True
            log.info("neural rendering ready (%sx%s, build %s ms)", self.w, self.h, line.split()[-1])
        else:
            self.error = line or "sb-nr exited"
            log.warning("neural rendering failed to start: %s", self.error)
        self._ready.set()

    @property
    def starting(self) -> bool:
        return not self._ready.is_set()

    def set_look(self, style: int, intensity: float, skin: bool) -> bool:
        if not self.ok or self.proc.poll() is not None:
            return False
        with self._lock:
            try:
                self.proc.stdin.write(f"c {float(intensity):.2f} {int(style)} 1 1 {1 if skin else 0}\n")
                self.proc.stdin.flush()
                while True:
                    line = self.proc.stdout.readline()
                    if not line:
                        return False
                    if line.strip() == "look":
                        return True
            except (BrokenPipeError, OSError):
                return False

    def process(self, rgba: np.ndarray) -> np.ndarray | None:
        if not self.ok or self.proc.poll() is not None:
            return None
        with self._lock:
            self._in[...] = rgba
            try:
                self.proc.stdin.write("f\n")
                self.proc.stdin.flush()
                line = self._reply()
            except (BrokenPipeError, OSError):
                self.ok = False
                return None
            if not line.startswith("done"):
                self.ok, self.error = False, line or "sb-nr exited"
                log.warning("neural rendering stopped: %s", self.error)
                return None
            self.ms = float(line.split()[-1])
            return self._out.copy()

    def close(self):
        self.ok = False
        try:
            if self.proc.poll() is None:
                self.proc.stdin.write("q\n")
                self.proc.stdin.flush()
                self.proc.wait(2)
        except Exception:  # noqa: BLE001
            self.proc.kill()
        try:
            self._map.close()
            os.close(self._fd)
            self._shm_path.unlink()
        except Exception:  # noqa: BLE001
            pass


class NeuralStage:
    """Between the card and the Game View: newest real picture in, processed picture out (via `deliver`, called on
    the worker thread – the receiver must hop to the GUI thread). Older pending pictures are dropped."""

    def __init__(self, deliver):
        self.deliver = deliver
        self.worker: NeuralWorker | None = None
        self._cv = threading.Condition()
        self._job = None
        self._alive = True
        self.frames = 0
        self.dropped = 0
        threading.Thread(target=self._run, daemon=True, name="nr-stage").start()

    def put(self, raw):
        with self._cv:
            if self._job is not None:
                self.dropped += 1
            self._job = raw
            self._cv.notify()

    def stop(self):
        with self._cv:
            self._alive = False
            self._cv.notify()

    def _run(self):
        import cv2
        from .capture.device import raw_to_rgb
        while True:
            with self._cv:
                while self._alive and self._job is None:
                    self._cv.wait()
                if not self._alive:
                    break
                raw, self._job = self._job, None
            rgb = raw_to_rgb(raw)
            if rgb is None:
                continue
            h, w = rgb.shape[:2]
            if self.worker is None or (self.worker.w, self.worker.h) != (w, h):
                if self.worker is not None:
                    self.worker.close()
                self.worker = NeuralWorker(w, h)
            rgba = cv2.cvtColor(rgb, cv2.COLOR_RGB2RGBA)
            out = self.worker.process(rgba) if not self.worker.starting else None
            self.frames += out is not None
            self.deliver(out if out is not None else rgba)
        if self.worker is not None:
            self.worker.close()


# ---------------------------------------------------------------------------------------------------------------
# GPU-only Game View: the worker (sb-nrview) owns the window. The card's NV12 picture goes to it through shared
# memory (one copy), and everything else - colour conversion, DLSS 5, scaling, presenting, frame generation - runs
# on the graphics card. Subtitles and the phone card are SubBridge's own see-through overlay windows on top.
def view_available() -> bool:
    """The Vulkan Game View worker can run (DLSS 5 inside it is optional): Linux, worker present, shaders set up."""
    from . import nrsetup
    return nrsetup.platform_ok() and nrsetup.worker().is_file() and (nr_dir() / "dlssnr-amd" / "shaders").is_dir()


class NrView:
    """Drop-in for the Game View (close / update_boxes / show_phone / show / raise_ / activateWindow / scale)."""

    def __init__(self, session, overlay, phone_panel, on_close=None, neural: bool = True, lsfg_mult: int = 0,
                 stable: bool = True):
        from .capture.device import _clean_env, _die_with_parent
        self.session, self.overlay, self.phone_panel, self.on_close = session, overlay, phone_panel, on_close
        self.scale = 1.0
        w, h = session.size()
        self.w, self.h = int(w), int(h)
        self.slot_bytes = self.w * self.h * 3 // 2
        shm_dir = Path("/dev/shm") if Path("/dev/shm").is_dir() else Path("/tmp")
        self._shm_path = shm_dir / f"subbridge-nrview-{os.getpid()}"
        with open(self._shm_path, "wb") as f:
            f.truncate(self.slot_bytes * 2)
        self._fd = os.open(self._shm_path, os.O_RDWR)
        self._map = mmap.mmap(self._fd, self.slot_bytes * 2)
        self._slots = [np.frombuffer(self._map, np.uint8, self.slot_bytes, i * self.slot_bytes) for i in (0, 1)]
        self._lock = threading.Lock()
        self._inflight = None          # slot the worker is drawing
        self._pending = None           # newest slot written while it was busy
        self._next = 0
        self.xid = 0
        self.ms = 0.0
        self.frames = 0
        self._geo = None
        self._geo_t = 0.0
        self._boxes: list = []
        self._look = ""
        self._stats = {"t0": time.time(), "in": 0, "size": 0, "fmt": 0, "over": 0, "done": 0, "ms": 0.0}
        self._phone = None
        self.closed = False
        env = _clean_env()
        env["DISABLE_MANGOHUD"] = "1"
        env["SB_TEMPORAL"] = "1" if stable else "0"
        if lsfg_mult >= 2:
            from . import fgmodes
            fi = fgmodes.info()
            if fi.lsfg_ok and fgmodes.lsfg_is_release(fi.lsfg_json):
                fgmodes.write_lsfg_conf(fi, lsfg_mult, {"sb-nrview"})
                from .paths import config_dir
                env["VK_ADD_LAYER_PATH"] = str(Path(fi.lsfg_json).parent)
                env["VK_INSTANCE_LAYERS"] = fgmodes.LSFG_LAYER
                env["LSFGVK_CONFIG"] = str(config_dir() / "lsfg-vk.toml")
        d = nr_dir()
        from .paths import config_dir
        self._errlog = open(config_dir() / "sb-nrview.log", "a", encoding="utf-8", errors="replace")
        self._errlog.write(f"\n--- {time.strftime('%Y-%m-%d %H:%M:%S')} start {self.w}x{self.h} stable={stable}\n")
        self._errlog.flush()
        self.crashed = False
        self._user_closed = False
        from . import nrsetup
        self.proc = subprocess.Popen([str(nrsetup.worker()), str(d), str(self.w), str(self.h), str(self._shm_path),
                                      "1" if neural else "0"],
                                     stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self._errlog,
                                     text=True, bufsize=1, env=env, preexec_fn=_die_with_parent)
        threading.Thread(target=self._reader, daemon=True, name="nrview-reader").start()
        session.set_nrview(self)

    # -- worker protocol ------------------------------------------------------------------------------------------
    def _send(self, line: str):
        try:
            self.proc.stdin.write(line + "\n")
            self.proc.stdin.flush()
        except (BrokenPipeError, OSError, ValueError):
            pass

    def _reader(self):
        for line in self.proc.stdout:
            line = line.strip()
            if line.startswith("done"):
                parts = line.split()
                self.ms = float(parts[-1])
                self.frames += 1
                st = self._stats
                st["done"] += 1
                st["ms"] += self.ms
                now = time.time()
                if now - st["t0"] >= 10:
                    dt = now - st["t0"]
                    log.info("DLSS 5 view: in %.1f/s (wrong size %d, other fmt %d, busy-overwrite %d) -> shown %.1f/s, "
                             "%.1f ms/frame", st["in"] / dt, st["size"], st["fmt"], st["over"], st["done"] / dt,
                             st["ms"] / max(1, st["done"]))
                    self._stats = {"t0": now, "in": 0, "size": 0, "fmt": 0, "over": 0, "done": 0, "ms": 0.0}
                with self._lock:
                    self._inflight = None
                    if self._pending is not None:
                        self._inflight, self._pending = self._pending, None
                        self._send(f"f {self._inflight}")
            elif line.startswith("win"):
                self.xid = int(line.split()[-1])
                log.info("DLSS 5 Game View window 0x%x", self.xid)
            elif line == "geom":
                self._geo_t = 0.0
            elif line.startswith("ready"):
                log.info("DLSS 5 Game View ready (build %s ms)", line.split()[-1])
                if self._look:
                    self._send(self._look)
            elif line.startswith("err"):
                log.warning("DLSS 5 Game View: %s", line)
            elif line == "closed":
                self._user_closed = True
                break
        code = self.proc.wait()
        if not self._user_closed and not self.closed:
            self.crashed = True                              # not closed by the user: the window restarts it
            log.warning("DLSS 5 Game View stopped unexpectedly (exit %s) – see sb-nrview.log", code)
        try:
            self._errlog.write(f"--- {time.strftime('%H:%M:%S')} exit {code} user_closed={self._user_closed}\n")
            self._errlog.flush()
        except Exception:  # noqa: BLE001
            pass
        self.closed = True
        cb, self.on_close = self.on_close, None
        if cb:
            cb()

    def put_frame(self, frame) -> bool:
        """GUI thread, for each real game picture: copy the NV12 planes straight into a free slot."""
        from PySide6.QtMultimedia import QVideoFrame, QVideoFrameFormat
        st = self._stats
        st["in"] += 1
        if self.closed or frame.pixelFormat() != QVideoFrameFormat.PixelFormat.Format_NV12:
            st["fmt"] += 1
            return False
        if frame.width() != self.w or frame.height() != self.h:
            st["size"] += 1
            return False
        with self._lock:
            slot = self._next if self._inflight != self._next else 1 - self._next
            if slot == self._inflight:
                return True
        if not frame.map(QVideoFrame.MapMode.ReadOnly):
            return False
        try:
            w, h = self.w, self.h
            dst = self._slots[slot]
            y = np.frombuffer(frame.bits(0), np.uint8, count=frame.bytesPerLine(0) * h).reshape(h, -1)[:, :w]
            uv = np.frombuffer(frame.bits(1), np.uint8, count=frame.bytesPerLine(1) * (h // 2)).reshape(h // 2, -1)[:, :w]
            dst[: w * h].reshape(h, w)[...] = y
            dst[w * h:].reshape(h // 2, w)[...] = uv
        finally:
            frame.unmap()
        with self._lock:
            self._next = 1 - slot
            if self._inflight is None:
                self._inflight = slot
                self._send(f"f {slot}")
            else:
                if self._pending is not None:
                    st["over"] += 1
                self._pending = slot
        return True

    def set_look(self, style: int, intensity: float, skin: bool):
        self._look = f"c {float(intensity):.2f} {int(style)} 1 1 {1 if skin else 0}"
        self._send(self._look)

    # -- where the picture is on screen (for the subtitle overlay) -----------------------------------------------
    def _geometry(self):
        now = time.time()
        if self._geo is not None and now - self._geo_t < 1.0:
            return self._geo
        self._geo_t = now
        if not self.xid:
            return None
        try:
            from Xlib import display
            dpy = getattr(self, "_dpy", None) or display.Display()
            self._dpy = dpy
            win = dpy.create_resource_object("window", self.xid)
            g = win.get_geometry()
            pos = dpy.screen().root.translate_coords(win, 0, 0)
            ww, wh = g.width, g.height
            s = min(ww / self.w, wh / self.h)
            ox = pos.x + (ww - self.w * s) / 2
            oy = pos.y + (wh - self.h * s) / 2
            self._geo = (ox, oy, s)
        except Exception:  # noqa: BLE001
            self._geo = None
        return self._geo

    def _map_box(self, b: dict, geo) -> dict:
        ox, oy, s = geo
        x0, y0, x1, y1 = b["rect"]
        m = dict(b)
        m["rect"] = (ox + x0 * s, oy + y0 * s, ox + x1 * s, oy + y1 * s)
        if "px" in m:
            m["px"] = m["px"] * s
        if m.get("max_w"):
            m["max_w"] = m["max_w"] * s
        return m

    def update_boxes(self, boxes: list):
        geo = self._geometry()
        if geo is None or self.closed:
            self.overlay.update([])
            return
        self.overlay.update([self._map_box(b, geo) for b in boxes])

    def show_phone(self, state):
        from PySide6.QtCore import QRect
        geo = self._geometry()
        if not state or not state.get("items") or geo is None:
            self.phone_panel.show_state(None, QRect(), QRect())
            return
        ox, oy, s = geo
        x0, y0, x1, y1 = state["rect"]
        area = QRect(int(ox), int(oy), int(self.w * s), int(self.h * s))
        phone = QRect(int(ox + x0 * s), int(oy + y0 * s), int((x1 - x0) * s), int((y1 - y0) * s))
        self.phone_panel.show_state(state, area, phone)

    # -- Game View interface ---------------------------------------------------------------------------------------
    def show(self):
        pass

    def raise_(self):
        pass

    def activateWindow(self):
        pass

    def close(self):
        if self.closed:
            return
        self.on_close = None
        self.session.set_nrview(None)
        self._send("q")
        try:
            self.proc.wait(2)
        except Exception:  # noqa: BLE001
            self.proc.kill()
        self.closed = True
        self.overlay.update([])
        try:
            self._map.close()
            os.close(self._fd)
            self._shm_path.unlink()
        except Exception:  # noqa: BLE001
            pass
