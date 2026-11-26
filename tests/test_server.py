import asyncio
import socket

import aiohttp
import pytest

from subbridge.server.server import SubtitleServer


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


@pytest.fixture(scope="module")
def server():
    srv = SubtitleServer(free_port(), "123456", "tok-abc")
    assert srv.start()
    srv.publish({"type": "line", "id": 1, "action": "new", "speaker": None, "text": "Szia", "original": "Hi"})
    yield srv
    srv.stop()


async def hello(port, payload):
    async with aiohttp.ClientSession() as s, s.ws_connect(f"http://127.0.0.1:{port}/ws") as ws:
        await ws.send_json(payload)
        msgs = []
        for _ in range(4):
            try:
                m = await ws.receive_json(timeout=2)
            except (TypeError, asyncio.TimeoutError):
                break
            msgs.append(m)
        return msgs


def test_serves_page(server):
    async def go():
        async with aiohttp.ClientSession() as s:
            async with s.get(f"http://127.0.0.1:{server.port}/") as r:
                return r.status, await r.text()
    st, body = asyncio.run(go())
    assert st == 200 and "SubBridge" in body


def test_wrong_pin_rejected(server):
    msgs = asyncio.run(hello(server.port, {"pin": "000000"}))
    assert msgs[0] == {"type": "auth", "ok": False, "reason": "bad_pin"}


def test_token_accepted_and_history_sent(server):
    msgs = asyncio.run(hello(server.port, {"token": "tok-abc"}))
    assert msgs[0]["ok"] is True
    hist = next(m for m in msgs if m["type"] == "history")
    assert hist["items"][0]["text"] == "Szia"


def test_pin_accepted(server):
    msgs = asyncio.run(hello(server.port, {"pin": "123456"}))
    assert msgs[0]["ok"] is True and msgs[0]["token"] == "tok-abc"


def test_lockout_after_failures(server):
    for _ in range(5):
        asyncio.run(hello(server.port, {"pin": "999999"}))
    msgs = asyncio.run(hello(server.port, {"pin": "123456"}))
    assert msgs[0]["reason"] == "locked"


def test_overlay_page_served():
    import asyncio
    import aiohttp
    from subbridge.server.server import SubtitleServer
    srv = SubtitleServer(18799, "123456", "tok")
    assert srv.start()
    try:
        async def go():
            async with aiohttp.ClientSession() as s:
                async with s.get("http://127.0.0.1:18799/overlay") as r:
                    assert r.status == 200 and "OBS" in await r.text()
                async with s.ws_connect("http://127.0.0.1:18799/ws?view=overlay") as ws:
                    m = await ws.receive_json(timeout=5)
                    assert m["type"] == "auth" and m["ok"]
        asyncio.run(go())
    finally:
        srv.stop()
