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

    def do_GET(self):
        if not V.handle(self):
            self._out(404, {"ok": False, "error": "not found"})

    def do_POST(self):
        if self.path.startswith(BASE) and V.handle(self):
            return
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


# ---------------------------------------------------------------- private report viewer (maintainer only)
# GET /subbridge/reports/?k=<token>  – token in /etc/subbridge-report.token; a cookie keeps you signed in.
import hmac
import html as _html
from http.cookies import SimpleCookie
from urllib.parse import parse_qs, urlsplit

TOKEN_FILE = os.environ.get("REPORT_TOKEN_FILE", "/etc/subbridge-report.token")
BASE = "/subbridge/reports"


def _token() -> str:
    try:
        return open(TOKEN_FILE, encoding="utf-8").read().strip()
    except OSError:
        return ""


def _state() -> dict:
    try:
        return json.load(open(os.path.join(ROOT, "state.json"), encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _save_state(st: dict):
    tmp = os.path.join(ROOT, "state.json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(st, f, ensure_ascii=False)
    os.replace(tmp, os.path.join(ROOT, "state.json"))


def _rows(name: str) -> list[dict]:
    out = []
    try:
        for ln in open(os.path.join(ROOT, name), encoding="utf-8"):
            try:
                out.append(json.loads(ln))
            except ValueError:
                pass
    except OSError:
        pass
    return out


E = _html.escape
CSS = """
:root{--bg:#0f1115;--card:#171a21;--line:#262b35;--tx:#e8eaf0;--mu:#8b93a5;--ac:#5b8cff;--ok:#33c48d;--warn:#f0a43a;--bad:#ef5b5b}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--tx);font:15px/1.45 system-ui,-apple-system,Segoe UI,Roboto,sans-serif}
a{color:inherit;text-decoration:none}header{position:sticky;top:0;background:rgba(15,17,21,.92);backdrop-filter:blur(8px);border-bottom:1px solid var(--line);padding:14px 16px;display:flex;gap:12px;align-items:center;flex-wrap:wrap;z-index:2}
h1{font-size:17px;margin:0;font-weight:650}.tabs{display:flex;gap:6px;margin-left:auto}.tabs a{padding:6px 12px;border:1px solid var(--line);border-radius:8px;color:var(--mu);font-size:13px}.tabs a.on{color:var(--tx);border-color:var(--ac);background:rgba(91,140,255,.12)}
main{max-width:980px;margin:0 auto;padding:16px}.stats{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:14px}.stat{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px 14px;min-width:110px}.stat b{display:block;font-size:22px}.stat span{color:var(--mu);font-size:12px}
.r{display:block;background:var(--card);border:1px solid var(--line);border-radius:12px;padding:12px 14px;margin-bottom:10px}.r:hover{border-color:#3a4252}.r.done{opacity:.5}
.top{display:flex;gap:8px;align-items:center;flex-wrap:wrap;font-size:12.5px;color:var(--mu)}.id{font-family:ui-monospace,monospace;color:var(--tx)}
.pill{padding:2px 8px;border-radius:99px;font-size:11.5px;border:1px solid var(--line)}.p-new{color:var(--ac);border-color:var(--ac)}.p-done{color:var(--ok);border-color:var(--ok)}
.h-ok{color:var(--ok)}.h-covered,.h-not_front{color:var(--warn)}.h-no_box,.h-error,.h-dead{color:var(--bad)}
.note{margin-top:6px;font-size:15px;white-space:pre-wrap;word-break:break-word}
img{max-width:100%;border-radius:8px;border:1px solid var(--line);display:block;margin:8px 0}
pre{background:#0b0d11;border:1px solid var(--line);border-radius:8px;padding:10px;overflow:auto;font-size:12px;max-height:420px}
.kv{display:grid;grid-template-columns:140px 1fr;gap:4px 12px;font-size:13.5px}.kv div:nth-child(odd){color:var(--mu)}
button{background:var(--ac);color:#fff;border:0;border-radius:8px;padding:8px 14px;font:inherit;font-weight:600;cursor:pointer}button.sec{background:transparent;border:1px solid var(--line);color:var(--tx)}
h2{font-size:15px;margin:22px 0 8px;color:var(--mu);font-weight:600;text-transform:uppercase;letter-spacing:.04em}
.fx{font-size:13.5px}.fx .en{color:var(--mu)}.fx .mt{color:var(--bad)}.fx .fix{color:var(--ok)}
@media(max-width:560px){.kv{grid-template-columns:1fr}.kv div:nth-child(odd){margin-top:6px}}
"""


def _page(title: str, body: str, tab: str = "") -> bytes:
    t = lambda k, lbl: f'<a class="{"on" if tab == k else ""}" href="{BASE}/{k}">{lbl}</a>'
    return (f'<!doctype html><html lang="hu"><head><meta charset="utf-8"><meta name="viewport" '
            f'content="width=device-width,initial-scale=1"><meta name="robots" content="noindex">'
            f'<title>{E(title)}</title><style>{CSS}</style></head><body><header><h1>SubBridge – hibajelentések</h1>'
            f'<nav class="tabs">{t("", "Jelentések")}{t("fixes", "Javított fordítások")}</nav></header>'
            f'<main>{body}</main></body></html>').encode()


class V:
    @staticmethod
    def handle(h) -> bool:
        u = urlsplit(h.path)
        if not u.path.startswith(BASE):
            return False
        tok, q = _token(), parse_qs(u.query)
        ck = SimpleCookie(h.headers.get("Cookie", ""))
        given = (q.get("k") or [""])[0] or (ck["sbr"].value if "sbr" in ck else "")
        if not tok or not hmac.compare_digest(given.encode(), tok.encode()):
            h.send_response(404); h.end_headers(); return True
        sub = u.path[len(BASE):].strip("/")
        if h.command == "POST" and sub.startswith("done/"):
            d = sub[5:]
            st = _state(); st[d] = not st.get(d, False); _save_state(st)
            h.send_response(303); h.send_header("Location", f"{BASE}/r/{d}"); h.end_headers(); return True
        if sub.startswith("img/"):
            parts = sub.split("/")
            if len(parts) == 3 and re.fullmatch(r"[\w-]+", parts[1]) and parts[2] in ("strip.jpg", "frame.jpg"):
                fp = os.path.join(ROOT, parts[1], parts[2])
                if os.path.isfile(fp):
                    data = open(fp, "rb").read()
                    h.send_response(200); h.send_header("Content-Type", "image/jpeg")
                    h.send_header("Content-Length", str(len(data))); h.send_header("Cache-Control", "private, max-age=86400")
                    h.end_headers(); h.wfile.write(data); return True
            h.send_response(404); h.end_headers(); return True
        if sub.startswith("r/"):
            body = V.detail(sub[2:])
        elif sub == "fixes":
            body = V.fixes()
        else:
            body = V.index()
        if body is None:
            h.send_response(404); h.end_headers(); return True
        data = _page("SubBridge jelentések", body, "fixes" if sub == "fixes" else ("" if not sub else "r"))
        h.send_response(200)
        h.send_header("Content-Type", "text/html; charset=utf-8")
        h.send_header("Content-Length", str(len(data)))
        h.send_header("Cache-Control", "no-store")
        h.send_header("X-Robots-Tag", "noindex")
        if (q.get("k") or [""])[0]:
            h.send_header("Set-Cookie", f"sbr={tok}; Path={BASE}; Max-Age=31536000; HttpOnly; Secure; SameSite=Strict")
        h.end_headers(); h.wfile.write(data)
        return True

    @staticmethod
    def index() -> str:
        rows, st = _rows("index.jsonl")[::-1], _state()
        fixes = _rows("corrections.jsonl")
        new = sum(1 for r in rows if not st.get(r["dir"]))
        today = time.strftime("%Y-%m-%d")
        out = [f'<div class="stats"><div class="stat"><b>{new}</b><span>nyitott</span></div>'
               f'<div class="stat"><b>{sum(1 for r in rows if r["t"].startswith(today))}</b><span>ma</span></div>'
               f'<div class="stat"><b>{len(rows)}</b><span>összes</span></div>'
               f'<div class="stat"><b>{len(fixes)}</b><span>javított fordítás</span></div></div>']
        if not rows:
            out.append('<p style="color:var(--mu)">Még nincs jelentés.</p>')
        for r in rows:
            done = st.get(r["dir"])
            hl = r.get("health") or "–"
            out.append(f'<a class="r{" done" if done else ""}" href="{BASE}/r/{E(r["dir"])}"><div class="top">'
                       f'<span class="pill {"p-done" if done else "p-new"}">{"kész" if done else "új"}</span>'
                       f'<span class="id">{E(r["id"])}</span><span>{E(r["t"])}</span><span>v{E(str(r.get("app")))}</span>'
                       f'<span>{E(r.get("os", "")[:30])}</span><span class="h-{E(hl)}">{E(hl)}</span></div>'
                       f'<div class="note">{E(r.get("note") or "(nincs megjegyzés)")}</div></a>')
        return "".join(out)

    @staticmethod
    def detail(d: str):
        if not re.fullmatch(r"[\w-]+", d):
            return None
        try:
            r = json.load(open(os.path.join(ROOT, d, "report.json"), encoding="utf-8"))
        except (OSError, ValueError):
            return None
        done = _state().get(d)
        ov = r.get("overlay") or {}
        src = r.get("source") or {}
        prof = ((r.get("settings") or {}).get("profiles") or [{}])[0]
        kv = [("Verzió", f'{r.get("app")}{" (telepített)" if r.get("frozen") else ""}'), ("Rendszer", r.get("os")),
              ("Érkezett", r.get("received")), ("Kapcsolat", r.get("contact") or "–"),
              ("Forrás", f'{src.get("kind")} · {src.get("label")} · {src.get("size")}'),
              ("Képernyők", ", ".join(f'{s.get("geo")} x{s.get("dpr")}' for s in r.get("screens") or [])),
              ("Felirat-állapot", ov.get("health")), ("Számlálók", json.dumps(ov.get("stats"))),
              ("OCR / fordító", f'{prof.get("ocr_engine")} / {prof.get("engine")}'),
              ("Fut", r.get("running"))]
        imgs = "".join(f'<img loading="lazy" src="{BASE}/img/{d}/{n}" alt="{n}">' for n in ("strip.jpg", "frame.jpg")
                       if os.path.isfile(os.path.join(ROOT, d, n)))
        crash = f'<h2>Összeomlás</h2><pre>{E(r["crash"])}</pre>' if r.get("crash") else ""
        return (f'<p><a href="{BASE}/" style="color:var(--mu)">← vissza</a></p>'
                f'<div class="r" style="cursor:default"><div class="top"><span class="id">{E(d)}</span></div>'
                f'<div class="note" style="font-size:17px">{E(r.get("note") or "(nincs megjegyzés)")}</div>'
                f'<form method="post" action="{BASE}/done/{E(d)}" style="margin-top:10px">'
                f'<button class="{"sec" if done else ""}">{"Újranyitás" if done else "Kész, megoldva"}</button></form></div>'
                f'<h2>Adatok</h2><div class="kv">' + "".join(f"<div>{E(k)}</div><div>{E(str(v))}</div>" for k, v in kv) +
                f'</div><h2>Képek</h2>{imgs or "<p>nincs kép</p>"}{crash}'
                f'<h2>Napló</h2><pre>{E(str(r.get("log", ""))[-12000:])}</pre>'
                f'<h2>Beállítások</h2><pre>{E(json.dumps(r.get("settings"), ensure_ascii=False, indent=1))}</pre>')

    @staticmethod
    def fixes() -> str:
        rows = _rows("corrections.jsonl")[::-1]
        if not rows:
            return '<p style="color:var(--mu)">Még nem küldött senki javított fordítást.</p>'
        return "".join(f'<div class="r fx"><div class="top"><span>{E(r.get("t", ""))}</span><span>v{E(r.get("app", ""))}</span></div>'
                       f'<div class="en">{E(r.get("en", ""))}</div><div class="mt">gép: {E(r.get("mt", ""))}</div>'
                       f'<div class="fix">javítva: {E(r.get("fix", ""))}</div></div>' for r in rows)


if __name__ == "__main__":
    os.makedirs(ROOT, mode=0o700, exist_ok=True)
    ThreadingHTTPServer(("127.0.0.1", int(os.environ.get("PORT", "3310"))), H).serve_forever()
