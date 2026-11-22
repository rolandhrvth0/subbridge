"""Run only the phone web server with demo subtitles (for UI work on the phone page).
Usage: python tools/demo_server.py [port]  → open http://<ip>:<port>/?k=demo"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from subbridge.server.server import SubtitleServer  # noqa: E402

DEMO = [
    ("Lena", "You should hear how he's talking now.", "Hallanod kéne, hogy most hogy beszél."),
    ("Theo", "Well, maybe he wants me to run things.", "Talán azt akarja, hogy én vezessem a dolgokat."),
    ("Lena", "Oh, hell yeah. You need some backup, I'm right here.", "Ó, de még mennyire. Ha kell erősítés, itt vagyok."),
    (None, "Get to the marked location.", "Menj a megjelölt helyre."),
    ("Theo", "We'll figure this out, I promise.", "Megoldjuk, ígérem."),
]

port = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 8797
srv = SubtitleServer(port, "123456", "demo")
srv.start()
srv.publish({"type": "status", "state": "running", "message": ""})
i = 0
while True:
    sp, en, hu = DEMO[i % len(DEMO)]
    srv.publish({"type": "line", "id": i + 1, "action": "new", "engine": "argos", "lang": "hu", "latency_ms": 240,
                 "speaker": sp, "note": None, "text": hu, "original": en, "ts": time.time()})
    srv.publish({"type": "visible", "ids": [i, i + 1] if i % 2 else [i + 1]})
    if "--phone" in sys.argv:
        srv.publish({"type": "phone", "header": "Nina", "items": [
            {"kind": "msg", "mine": True, "name": "", "en": "Almost there.", "text": "Mindjárt ott vagyok."},
            {"kind": "msg", "mine": False, "name": "", "en": "Take your time hon. Bring snacks??",
             "text": "Ráérsz, drágám. Hozol nasit??"},
            {"kind": "msg", "mine": False, "name": "", "en": "and dont forget the keys XOXO",
             "text": "És ne felejtsd el a kulcsokat XOXO"},
            {"kind": "reply", "mine": True, "name": "", "en": "Reply", "text": "Válasz"}]})
    i += 1
    time.sleep(2.5)
