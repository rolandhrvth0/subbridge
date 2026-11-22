"""Replay recorded frames through the full pipeline (engine + server + a WebSocket client).
Usage: python tools/replay.py <folder with *.jpg|*.png frames> [--engine argos|deepl] [--fps 4]
Measures time from 'frame first shows the subtitle' to 'client received it'."""
from __future__ import annotations

import argparse
import asyncio
import glob
import json
import sys
import threading
import time
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from subbridge.capture.base import CaptureSource  # noqa: E402
from subbridge.config import AppSettings, Profile  # noqa: E402
from subbridge.engine import Callbacks, Engine  # noqa: E402
from subbridge.server.server import SubtitleServer  # noqa: E402


class ReplayCapture(CaptureSource):
    def __init__(self, files, fps):
        self.frames = [np.asarray(Image.open(f).convert("RGB")) for f in files]
        self.fps = fps
        self.t0 = None
        self.shown_at = {}

    def index(self):
        if self.t0 is None:
            self.t0 = time.time()
        return int((time.time() - self.t0) * self.fps)

    def source_size(self, kind, ident):
        h, w = self.frames[0].shape[:2]
        return w, h

    def grab(self, kind, ident, rect=None):
        i = min(self.index(), len(self.frames) - 1)
        self.shown_at.setdefault(i, time.time())
        return self.frames[i]


async def client(port, token, received, stop):
    import aiohttp
    async with aiohttp.ClientSession() as s, s.ws_connect(f"http://127.0.0.1:{port}/ws") as ws:
        await ws.send_json({"token": token})
        async for m in ws:
            d = json.loads(m.data)
            if d["type"] == "line":
                received.append((time.time(), d))
            if stop.is_set():
                break


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("folder")
    ap.add_argument("--engine", default="argos")
    ap.add_argument("--fps", type=float, default=2.0, help="recorded frames per second of playback")
    ap.add_argument("--limit", type=int, default=80)
    a = ap.parse_args()
    files = sorted(glob.glob(f"{a.folder}/*eredeti*.jpg") or glob.glob(f"{a.folder}/*.png") or glob.glob(f"{a.folder}/*.jpg"))[: a.limit]
    cap = ReplayCapture(files, a.fps)
    st = AppSettings.load()
    st.port = 8799
    p = Profile(name="replay", source_kind="screen", region=[0, 0, 1, 1], engine=a.engine, interval_ms=200)
    st.profiles = [p.__dict__]
    st.active_profile = "replay"
    srv = SubtitleServer(st.port, st.pin, st.token)
    srv.start()
    eng = Engine(st, cap, Callbacks(subtitle=srv.publish, status=lambda *x: print("status", x)))
    received, stop = [], threading.Event()
    loop = asyncio.new_event_loop()
    th = threading.Thread(target=lambda: loop.run_until_complete(client(st.port, st.token, received, stop)), daemon=True)
    th.start()
    time.sleep(0.5)
    eng.start()
    time.sleep(len(files) / a.fps + 2)
    stop.set()
    eng.shutdown()
    srv.stop()
    lat = []
    for t, d in received:
        lat.append(d["latency_ms"])
        note = f"({d['note']}) " if d.get("note") else ""
        print(f"#{d['id']:<3} [{d['action']:6}] {d['engine']:5} {d['latency_ms']:4} ms  {d.get('speaker') or '-':10} {note}{d['original']}  ->  {d['text']}")
    if lat:
        lat.sort()
        print(f"\n{len(lat)} messages; capture→client latency median {lat[len(lat)//2]} ms, max {lat[-1]} ms")


if __name__ == "__main__":
    main()
