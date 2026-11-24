"""Build a local subtitle corpus from long gameplay recordings (LOCAL ONLY – never commit or publish
the videos, frames or extracted text).

  python tools/corpus.py extract build/corpus/v1.mp4 [--jobs 6] [--fps 2]
      -> build/corpus/<name>/lines.jsonl  {"t": sec, "speaker", "text"} (one row per new subtitle)
         build/corpus/<name>/img/<t>.jpg    subtitle band of each new subtitle (for overlay tests)
  python tools/corpus.py stats build/corpus/v1
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

Y0, Y1 = 0.70, 0.97          # subtitle band (fractions of the height)


def duration(path: str) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
                         capture_output=True, text=True).stdout
    return float(out.strip() or 0)


def _segment(args):
    path, start, length, fps, outdir, idx = args
    from PIL import Image
    from subbridge.engine import read_blocks
    from subbridge.ocr.preprocess import PrepOptions
    from subbridge.ocr.tesseract import TesseractEngine
    from subbridge.pipeline.textclean import normalise_for_compare
    W, H = 1920, 1080
    y0, y1 = int(H * Y0), int(H * Y1)
    bh = y1 - y0
    import os
    hw = ["-hwaccel", "vaapi", "-hwaccel_device", "/dev/dri/renderD128"] if os.environ.get("SB_HWACCEL") == "vaapi" else []
    cmd = ["ffmpeg", "-loglevel", "error", *hw, "-ss", str(start), "-t", str(length), "-i", path,
           "-vf", f"fps={fps},scale={W}:{H},crop={W}:{bh}:0:{y0}", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE)
    ocr = TesseractEngine("en")
    opts = PrepOptions()
    size = W * bh * 3
    rows, last_sig, last_keys, i = [], None, set(), 0
    img_dir = Path(outdir) / "img"
    img_dir.mkdir(parents=True, exist_ok=True)
    with open(Path(outdir) / f"part{idx:02d}.jsonl", "w", encoding="utf-8") as f:
        while True:
            buf = p.stdout.read(size)
            if len(buf) < size:
                break
            t = start + i / fps
            i += 1
            rgb = np.frombuffer(buf, np.uint8).reshape(bh, W, 3)
            # centre strip bright-pixel pattern: skip OCR when nothing changed
            strip = rgb[:, W // 2 - 300: W // 2 + 300: 3, :].max(axis=2) > 150
            sig = strip[::3, ::3]
            if last_sig is not None and np.mean(sig != last_sig) < 0.004:
                continue
            last_sig = sig
            if not strip.any():
                last_keys = set()
                continue
            try:
                blocks, boxes, _ = read_blocks(rgb, ocr, opts, 60, True)
            except Exception:  # noqa: BLE001
                continue
            keys = set()
            new = False
            for b in blocks:
                k = normalise_for_compare(f"{b.speaker}:{b.text}")
                keys.add(k)
                if k in last_keys:
                    continue
                new = True
                f.write(json.dumps({"t": round(t, 1), "speaker": b.speaker, "text": b.text, "boxes": len(boxes)},
                                   ensure_ascii=False) + "\n")
                f.flush()
            if new:
                Image.fromarray(rgb).save(img_dir / f"{t:08.1f}.jpg", quality=85)
            last_keys = keys
    p.wait()
    return idx


def extract(path: str, jobs: int, fps: float):
    name = Path(path).stem
    outdir = Path(path).parent / name
    outdir.mkdir(exist_ok=True)
    dur = duration(path)
    seg = dur / jobs
    args = [(path, k * seg, seg + 1, fps, str(outdir), k) for k in range(jobs)]
    with ProcessPoolExecutor(jobs) as ex:
        for idx in ex.map(_segment, args):
            print("segment done", idx, flush=True)
    rows = []
    for part in sorted(outdir.glob("part*.jsonl")):
        rows += [json.loads(x) for x in part.read_text(encoding="utf-8").splitlines() if x.strip()]
    rows.sort(key=lambda r: r["t"])
    (outdir / "lines.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    print(f"{len(rows)} lines -> {outdir / 'lines.jsonl'}")


def stats(d: str):
    rows = [json.loads(x) for x in (Path(d) / "lines.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
    from collections import Counter
    sp = Counter(r["speaker"] for r in rows)
    print(len(rows), "lines;", len(sp), "speakers:", sp.most_common(25))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["extract", "stats"])
    ap.add_argument("path")
    ap.add_argument("--jobs", type=int, default=6)
    ap.add_argument("--fps", type=float, default=2)
    a = ap.parse_args()
    extract(a.path, a.jobs, a.fps) if a.cmd == "extract" else stats(a.path)
