"""Local web + WebSocket server. Serves the phone client and pushes subtitles to it."""
from __future__ import annotations

import asyncio
import json
import logging
import secrets
import threading
import time
from collections import OrderedDict

from aiohttp import WSMsgType, web

from ..paths import resource_dir

log = logging.getLogger(__name__)
WEB_DIR = resource_dir() / "server" / "web"


class SubtitleServer:
    def __init__(self, port: int, pin: str, token: str, require_pin: bool = True, ssl_context=None):
        self.port = port
        self.pin = pin
        self.token = token
        self.require_pin = require_pin
        self.ssl_context = ssl_context
        self.lines: OrderedDict[int, dict] = OrderedDict()     # conversation, by entry id
        self.visible: list[int] = []
        self.phone: dict | None = None                         # last in-game phone state
        self.status: dict = {"type": "status", "state": "stopped"}
        self.client_settings: dict = {}
        self._clients: dict[web.WebSocketResponse, dict] = {}
        self._failed: dict[str, list[float]] = {}
        self._loop: asyncio.AbstractEventLoop | None = None
        self._runner: web.AppRunner | None = None
        self._thread: threading.Thread | None = None
        self.on_clients_changed = lambda n, names: None
        self.error: str = ""
        self._ready = threading.Event()

    # ---------------------------------------------------------------- lifecycle
    def start(self) -> bool:
        self._thread = threading.Thread(target=self._run, name="server", daemon=True)
        self._thread.start()
        self._ready.wait(5)
        return not self.error

    def stop(self):
        if self._loop:
            fut = asyncio.run_coroutine_threadsafe(self._shutdown(), self._loop)
            try:
                fut.result(3)
            except Exception:  # noqa: BLE001
                pass
            self._loop.call_soon_threadsafe(self._loop.stop)
        if self._thread:
            self._thread.join(3)

    def _run(self):
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._startup())
        except OSError as e:
            self.error = f"A(z) {self.port} port foglalt vagy nem elérhető ({e.strerror})."
            self._ready.set()
            return
        self._ready.set()
        self._loop.run_forever()

    async def _startup(self):
        app = web.Application()
        app.router.add_get("/ws", self._ws)
        app.router.add_get("/", self._index)
        app.router.add_get("/api/info", self._info)
        app.router.add_static("/static/", WEB_DIR, show_index=False)
        for name in ("manifest.webmanifest", "sw.js"):
            app.router.add_get(f"/{name}", self._file(name))
        app.middlewares.append(self._headers)
        self._runner = web.AppRunner(app, access_log=None)
        await self._runner.setup()
        site = web.TCPSite(self._runner, "0.0.0.0", self.port, ssl_context=self.ssl_context)
        await site.start()

    async def _shutdown(self):
        for ws in list(self._clients):
            await ws.close()
        if self._runner:
            await self._runner.cleanup()

    @web.middleware
    async def _headers(self, request, handler):
        resp = await handler(request)
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["Referrer-Policy"] = "no-referrer"
        if request.path.startswith("/static/") or request.path == "/":
            resp.headers["Cache-Control"] = "no-cache"
        return resp

    def _file(self, name):
        async def handler(_request):
            ctype = "application/manifest+json" if name.endswith("webmanifest") else None
            return web.FileResponse(WEB_DIR / name, headers={"Content-Type": ctype} if ctype else None)
        return handler

    async def _index(self, _request):
        return web.FileResponse(WEB_DIR / "index.html")

    async def _info(self, _request):
        return web.json_response({"name": "SubBridge", "pin_required": self.require_pin})

    # ---------------------------------------------------------------- websocket
    def _too_many_failures(self, ip: str) -> bool:
        now = time.time()
        recent = [t for t in self._failed.get(ip, []) if now - t < 60]
        self._failed[ip] = recent
        return len(recent) >= 5

    async def _ws(self, request: web.Request):
        ws = web.WebSocketResponse(heartbeat=15, max_msg_size=64 * 1024)
        await ws.prepare(request)
        ip = request.remote or "?"
        authed = not self.require_pin
        try:
            if not authed:
                msg = await ws.receive(timeout=30)
                if msg.type != WSMsgType.TEXT:
                    await ws.close()
                    return ws
                try:
                    hello = json.loads(msg.data)
                except ValueError:
                    hello = {}
                if self._too_many_failures(ip):
                    await ws.send_json({"type": "auth", "ok": False, "reason": "locked"})
                    await ws.close()
                    return ws
                tok, pin = str(hello.get("token", "")), str(hello.get("pin", ""))
                if (tok and secrets.compare_digest(tok, self.token)) or \
                        (pin and secrets.compare_digest(pin, self.pin)):
                    authed = True
                else:
                    self._failed.setdefault(ip, []).append(time.time())
                    await ws.send_json({"type": "auth", "ok": False, "reason": "bad_pin"})
                    await ws.close()
                    return ws
            name = ""
            await ws.send_json({"type": "auth", "ok": True, "token": self.token})
            await ws.send_json(self.status)
            if self.client_settings:
                await ws.send_json({"type": "settings", "settings": self.client_settings})
            await ws.send_json({"type": "history", "items": list(self.lines.values()),
                                "visible": self.visible})
            if self.phone:
                await ws.send_json(self.phone)
            self._clients[ws] = {"ip": ip, "name": name, "since": time.time()}
            self._notify_clients()
            async for msg in ws:
                if msg.type == WSMsgType.TEXT:
                    try:
                        d = json.loads(msg.data)
                    except ValueError:
                        continue
                    if d.get("type") == "hello":
                        self._clients[ws]["name"] = str(d.get("device", ""))[:40]
                        self._notify_clients()
                    elif d.get("type") == "ping":
                        await ws.send_json({"type": "pong", "t": d.get("t")})
                elif msg.type in (WSMsgType.ERROR, WSMsgType.CLOSE):
                    break
        except (asyncio.TimeoutError, ConnectionResetError):
            pass
        finally:
            if self._clients.pop(ws, None) is not None:
                self._notify_clients()
        return ws

    def _notify_clients(self):
        names = [c["name"] or c["ip"] for c in self._clients.values()]
        try:
            self.on_clients_changed(len(names), names)
        except Exception:  # noqa: BLE001
            log.exception("client callback")

    # ---------------------------------------------------------------- publish (thread-safe)
    def publish(self, msg: dict):
        t = msg.get("type")
        if t == "line":
            self.lines[msg["id"]] = msg
            while len(self.lines) > 80:
                self.lines.popitem(last=False)
        elif t == "visible":
            self.visible = list(msg.get("ids", []))
        elif t == "phone":
            self.phone = msg if msg.get("items") else None
        elif t == "status":
            self.status = msg
        elif t == "settings":
            self.client_settings = msg.get("settings", {})
        if self._loop:
            asyncio.run_coroutine_threadsafe(self._broadcast(msg), self._loop)

    async def _broadcast(self, msg: dict):
        data = json.dumps(msg, ensure_ascii=False)
        for ws in list(self._clients):
            try:
                await ws.send_str(data)
            except (ConnectionResetError, RuntimeError):
                self._clients.pop(ws, None)

    @property
    def client_count(self) -> int:
        return len(self._clients)
