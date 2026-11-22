#!/usr/bin/env python3
"""SubBridge bug-report receiver (runs on the project server behind nginx: POST /subbridge/api/report).

Stores each report in /var/lib/subbridge-reports/<time>-<id>/ (report.json, strip.jpg, frame.jpg) and appends a
line to index.jsonl. Limits: 4 MB per request, 6 reports / hour / IP, 400 / day overall. Standard library only."""
import base64
import json
import os
import re
import secrets
import time
from collections import defaultdict, deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.environ.get("REPORT_DIR", "/var/lib/subbridge-reports")
MAX_BODY = 4_000_000
PER_IP, PER_DAY = 6, 400
_ip_hits: dict[str, deque] = defaultdict(deque)
_day: deque = deque()
_fix_hits: dict[str, deque] = defaultdict(deque)


def _fix_limited(ip: str) -> bool:
    now, q = time.time(), _fix_hits[ip]
    while q and now - q[0] > 3600:
        q.popleft()
    if len(q) >= 60:
        return True
    q.append(now)
    return False


def _limited(ip: str) -> bool:
    now = time.time()
    q = _ip_hits[ip]
    while q and now - q[0] > 3600:
        q.popleft()
    while _day and now - _day[0] > 86400:
        _day.popleft()
    if len(q) >= PER_IP or len(_day) >= PER_DAY:
        return True
    q.append(now)
    _day.append(now)
    return False


def _jpeg(b64) -> bytes | None:
    if not isinstance(b64, str) or len(b64) > 2_000_000:
        return None
    try:
        raw = base64.b64decode(b64, validate=True)
    except ValueError:
        return None
    return raw if raw[:3] == b"\xff\xd8\xff" else None


class H(BaseHTTPRequestHandler):
    server_version = "sbreport"

    def _out(self, code: int, obj: dict):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if self.path.rstrip("/") not in ("/subbridge/api/report", "/report"):
            return self._out(404, {"ok": False, "error": "not found"})
        try:
            n = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            n = 0
        if not 0 < n <= MAX_BODY:
            return self._out(413, {"ok": False, "error": "too large"})
        ip = self.headers.get("X-Real-IP") or self.client_address[0]
        if n <= 20_000 and self.headers.get("X-Kind") == "correction":
            return self._correction(ip, n)
        if _limited(ip):
            return self._out(429, {"ok": False, "error": "too many reports, try later"})
        try:
            d = json.loads(self.rfile.read(n))
            assert isinstance(d, dict) and re.fullmatch(r"\d+\.\d+\.\d+", str(d.get("app", "")))
        except Exception:  # noqa: BLE001
            return self._out(400, {"ok": False, "error": "bad report"})
        rid = secrets.token_hex(3).upper()
        folder = os.path.join(ROOT, time.strftime("%Y%m%d-%H%M%S") + "-" + rid)
        os.makedirs(folder, mode=0o700)
        for key, name in (("image", "strip.jpg"), ("frame", "frame.jpg")):
            img = _jpeg(d.pop(key, None))
            if img:
                with open(os.path.join(folder, name), "wb") as f:
                    f.write(img)
        d["received"] = time.strftime("%Y-%m-%d %H:%M:%S")
        with open(os.path.join(folder, "report.json"), "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=1)
        line = {"id": rid, "dir": os.path.basename(folder), "t": d["received"], "app": d.get("app"),
                "os": str(d.get("os", ""))[:60], "health": (d.get("overlay") or {}).get("health"),
                "note": str(d.get("note", ""))[:160]}
        with open(os.path.join(ROOT, "index.jsonl"), "a", encoding="utf-8") as f:
            f.write(json.dumps(line, ensure_ascii=False) + "\n")
        return self._out(200, {"ok": True, "id": rid})

    def _correction(self, ip: str, n: int):
        """A user's fixed translation (sentence + machine output + fix): collected to improve the packs."""
        if _fix_limited(ip):
            return self._out(429, {"ok": False, "error": "too many"})
        try:
            d = json.loads(self.rfile.read(n))
            row = {k: str(d.get(k, ""))[:1000] for k in ("app", "src", "tgt", "en", "mt", "fix")}
            assert row["en"] and row["fix"]
        except Exception:  # noqa: BLE001
            return self._out(400, {"ok": False, "error": "bad correction"})
        row["t"] = time.strftime("%Y-%m-%d %H:%M:%S")
        with open(os.path.join(ROOT, "corrections.jsonl"), "a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
        return self._out(200, {"ok": True, "id": "fix"})

    def log_message(self, fmt, *args):
        pass


if __name__ == "__main__":
    os.makedirs(ROOT, mode=0o700, exist_ok=True)
    ThreadingHTTPServer(("127.0.0.1", int(os.environ.get("PORT", "3310"))), H).serve_forever()
