"""Headless live run against a real window (read-only).
Usage: python tools/live.py <window title> <seconds> [argos|deepl]"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from subbridge.capture import create_backend  # noqa: E402
from subbridge.config import AppSettings, Profile  # noqa: E402
from subbridge.engine import Callbacks, Engine  # noqa: E402


def main():
    title, secs = sys.argv[1], float(sys.argv[2])
    st = AppSettings.load()
    p = Profile(name="live", source_kind="window", window_title=title, region=[0.3202, 0.697, 0.3988, 0.303],
                engine=sys.argv[3] if len(sys.argv) > 3 else "argos", game_phone=True)
    st.profiles = [p.__dict__]
    st.active_profile = "live"
    cap = create_backend()

    def sub(m):
        if m["type"] == "line":
            print(f"#{m['id']:<3} [{m['action']:6}] {m['engine']:5} {m['latency_ms']:4}ms {m.get('speaker') or '-':10} "
                  f"{m['original']}  ->  {m['text']}", flush=True)

    def stats(d):
        print(f"stats {d['fps']:.1f} reads/s, ocr {d['ocr_ms']:.0f} ms", flush=True)

    eng = Engine(st, cap, Callbacks(subtitle=sub, status=lambda *a: print("status", a, flush=True), stats=stats))
    eng.start()
    time.sleep(secs)
    eng.shutdown()


main()
