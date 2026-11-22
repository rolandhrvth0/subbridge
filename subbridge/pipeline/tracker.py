"""Line tracker: turns noisy per-frame OCR readings into a clean, append-only conversation.

Every frame yields the dialogue lines currently on screen (one per speaker/box). Each line gets a
track. A track is *committed* (sent to the phone once) when it has been read the same way on
``stable_frames`` consecutive frames. Re-reads, fade-ins, flicker, a line that the game shows again,
or a line read once together with its neighbour and once alone never produce duplicates.

Events:
  ("new",    id, line)  – a new dialogue line
  ("update", id, line)  – the same line got longer / better read (typewriter reveal, speaker found)
"""
from __future__ import annotations

import itertools
import time
from collections import deque
from dataclasses import dataclass, field

from .dedup import is_extension, similarity
from .textclean import Line, normalise_for_compare


@dataclass
class LineEvent:
    kind: str
    id: int
    line: Line


@dataclass
class _Track:
    line: Line
    stable: int = 1              # consecutive frames the current text was read
    missed: int = 0
    committed: int | None = None
    sent_text: str = ""
    sent_speaker: str | None = None


def _n(t: str) -> str:
    return normalise_for_compare(t)


@dataclass
class LineTracker:
    stable_frames: int = 2
    similarity_threshold: float = 0.82
    forget_frames: int = 8               # a track survives this many frames without being seen
    recent_seconds: float = 90.0         # a line shown again within this window is not re-sent
    recent_size: int = 40
    _tracks: list = field(default_factory=list)
    _recent: deque = field(default_factory=lambda: deque(maxlen=40))   # (norm, speaker, id, t, text)
    _ids: itertools.count = field(default_factory=lambda: itertools.count(1))
    last_ids: list = field(default_factory=list)     # committed id of every line of the last feed (or None)

    def reset(self):
        self._tracks.clear()
        self._recent.clear()

    def visible_ids(self) -> list[int]:
        return [t.committed for t in self._tracks if t.committed and t.missed == 0]

    # ------------------------------------------------------------------ matching
    def _same(self, a: str, b: str) -> bool:
        return similarity(a, b) >= self.similarity_threshold or is_extension(a, b) or is_extension(b, a)

    def _match(self, line: Line, used: set) -> _Track | None:
        best, best_s = None, 0.0
        for t in self._tracks:
            if id(t) in used:
                continue
            if t.line.speaker and line.speaker and t.line.speaker.lower() != line.speaker.lower():
                if similarity(t.line.text, line.text) < 0.95:
                    continue
            s = similarity(t.line.text, line.text)
            if is_extension(t.line.text, line.text) or is_extension(line.text, t.line.text):
                s = max(s, self.similarity_threshold)
            if s >= self.similarity_threshold and s > best_s:
                best, best_s = t, s
        return best

    def _find_recent(self, line: Line, now: float):
        for norm, speaker, rid, t, text in reversed(self._recent):
            if now - t > self.recent_seconds:
                break
            if self._same(text, line.text):
                return rid, text
        return None

    # ------------------------------------------------------------------ main
    def feed(self, lines: list[Line], now: float | None = None) -> list[LineEvent]:
        now = time.time() if now is None else now
        used: set = set()
        events: list[LineEvent] = []
        seen_tracks = []
        for line in lines:
            t = self._match(line, used)
            if t is None:
                t = _Track(line)
                self._tracks.append(t)
            else:
                old = t.line
                if _n(line.text) == _n(old.text):
                    t.stable += 1
                elif len(_n(line.text)) > len(_n(old.text)):
                    t.line = Line(line.speaker or old.speaker, line.text, line.note or old.note)
                    t.stable = 1
                else:
                    # shorter / worse read of the same line: keep the better one, still counts as seen
                    t.stable += 1 if similarity(line.text, old.text) >= 0.95 else 0
                if line.speaker and not t.line.speaker:
                    t.line = Line(line.speaker, t.line.text, t.line.note or line.note)
                if line.note and not t.line.note:
                    t.line.note = line.note
            t.missed = 0
            used.add(id(t))
            seen_tracks.append(t)

        for t in self._tracks:
            if id(t) not in used:
                t.missed += 1
        self._tracks = [t for t in self._tracks if t.missed <= self.forget_frames]

        for t in seen_tracks:
            if t.stable < self.stable_frames:
                continue
            if t.committed is None:
                hit = self._find_recent(t.line, now)
                if hit:
                    rid, text = hit
                    t.committed, t.sent_text, t.sent_speaker = rid, text, t.line.speaker
                    if len(_n(t.line.text)) > len(_n(text)) + 2 and is_extension(text, t.line.text):
                        events.append(self._send(t, "update", now))
                    continue
                t.committed = next(self._ids)
                events.append(self._send(t, "new", now))
            elif (_n(t.line.text) != _n(t.sent_text) and len(_n(t.line.text)) > len(_n(t.sent_text)) + 2) \
                    or (t.line.speaker and not t.sent_speaker):
                events.append(self._send(t, "update", now))
        self.last_ids = [t.committed for t in seen_tracks]
        return events

    def _send(self, t: _Track, kind: str, now: float) -> LineEvent:
        t.sent_text, t.sent_speaker = t.line.text, t.line.speaker
        self._recent = deque([r for r in self._recent if r[2] != t.committed], maxlen=self.recent_size)
        self._recent.append((_n(t.line.text), t.line.speaker, t.committed, now, t.line.text))
        return LineEvent(kind, t.committed, Line(t.line.speaker, t.line.text, t.line.note))
