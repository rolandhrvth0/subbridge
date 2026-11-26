"""Settings. App-wide settings + named profiles (one per game)."""
from __future__ import annotations

import json
import secrets
from dataclasses import asdict, dataclass, field, fields

from .paths import config_dir


@dataclass
class Profile:
    name: str = "Alap"
    # source
    source_kind: str = ""                # screen | window ("" = not chosen yet)
    window_title: str = ""               # matched by substring when the window id changed
    screen_index: int = 0
    device_id: str = ""                  # video capture device (capture card), kind "device"
    device_name: str = ""
    device_audio: bool = True            # play the card's sound in the Game View
    device_format: str = ""              # "" = automatic (1440p/1080p 60 fps), else "1920x1080@60:Jpeg"
    device_audio_id: str = ""            # "" = the card's own audio input
    region: list[float] = field(default_factory=lambda: [0.1, 0.72, 0.8, 0.22])  # x, y, w, h (fractions)
    # OCR
    ocr_engine: str = "auto"           # auto | tesseract | rapid | windows
    interval_ms: int = 250
    text_color: str = "light"
    threshold: int = 0
    scale: float = 0.0
    invert: bool = False
    find_box: bool = True
    min_confidence: int = 60
    # filter
    similarity: float = 0.85
    stable_frames: int = 2
    clear_frames: int = 6
    split_speaker: bool = True
    # translation
    source_lang: str = "en"
    target_lang: str = "hu"
    engine: str = "argos"
    glossary: list[dict] = field(default_factory=list)
    # in-game overlay: cover the original subtitle box with the translation (window sources only)
    overlay: bool = True
    # extra translation zones: [{"name", "kind": help|objective|notice|other, "region": [x,y,w,h], "on": bool}]
    zones: list[dict] = field(default_factory=list)
    game_phone: bool = True              # translate the in-game phone (chats, posts, news, replies)
    overlay_scale: float = 1.0
    learn_mode: bool = False
    low_latency: bool = True             # capture card: 60 fps formats first, no vsync wait, small audio buffers
    device_audio_out: str = ""           # where the card sound plays ("" = system default output)
    fg_multiplier: int = 2               # lsfg: 2/3/4 × the game's 30 fps = 60/90/120 fps
    neural: bool = False                 # experimental DLSS 5 neural rendering (only with a local sb-nr install)
    nr_style: int = 1                    # DLSS 5 look: 0 Standard, 1 Natural (NVIDIA's), 2 Cinematic
    nr_intensity: float = 0.75           # 0.25 .. 1.0
    nr_skin: bool = True                 # faces keep the game's own detail
    upscale: bool = True                 # Game View bigger than the card picture: GPU upscaling + sharpening
    framegen: str = "auto"               # Game View frame generation: auto|lsfg|afmf|smooth|builtin|off (fgmodes)             # show the original (small) under the translation on the game

    @classmethod
    def from_dict(cls, d: dict) -> "Profile":
        names = {f.name for f in fields(cls)}
        d = {k: v for k, v in (d or {}).items() if k in names}
        if isinstance(d.get("framegen"), bool):          # 1.1.x: on/off switch for the CPU interpolation
            d["framegen"] = "auto" if d["framegen"] else "off"
        if d.get("framegen") == "builtin":               # CPU interpolation removed in 1.2.3
            d["framegen"] = "auto"
        return cls(**d)


@dataclass
class AppSettings:
    language: str = "hu"                 # UI language
    port: int = 8765
    pin: str = field(default_factory=lambda: f"{secrets.randbelow(10**6):06d}")
    token: str = field(default_factory=lambda: secrets.token_urlsafe(12))
    require_pin: bool = True
    https: bool = False
    active_profile: str = "Alap"
    deepl_key: str = ""
    google_key: str = ""
    libre_url: str = ""
    libre_key: str = ""
    first_run_done: bool = False
    game_setup_done: bool = False        # confirmed the recommended in-game subtitle settings
    online_feed: bool = True             # news, slang/role packs and update notice from the project site
    theme: str = "dark"
    ocr_auto_done: bool = False          # 1.0.2: old default "tesseract" profiles moved to "auto" once
    profiles: list[dict] = field(default_factory=lambda: [asdict(Profile())])

    # ---------------------------------------------------------------- profiles
    def profile(self, name: str | None = None) -> Profile:
        name = name or self.active_profile
        for p in self.profiles:
            if p.get("name") == name:
                return Profile.from_dict(p)
        return Profile.from_dict(self.profiles[0]) if self.profiles else Profile()

    def save_profile(self, p: Profile) -> None:
        d = asdict(p)
        for i, q in enumerate(self.profiles):
            if q.get("name") == p.name:
                self.profiles[i] = d
                break
        else:
            self.profiles.append(d)

    def delete_profile(self, name: str) -> None:
        if len(self.profiles) > 1:
            self.profiles = [p for p in self.profiles if p.get("name") != name]
            if self.active_profile == name:
                self.active_profile = self.profiles[0]["name"]

    def profile_names(self) -> list[str]:
        return [p.get("name", "?") for p in self.profiles]

    # ---------------------------------------------------------------- io
    @staticmethod
    def path():
        return config_dir() / "settings.json"

    @classmethod
    def load(cls) -> "AppSettings":
        try:
            d = json.loads(cls.path().read_text(encoding="utf-8"))
            names = {f.name for f in fields(cls)}
            s = cls(**{k: v for k, v in d.items() if k in names})
        except (OSError, ValueError, TypeError):
            s = cls()
        if not s.profiles:
            s.profiles = [asdict(Profile())]
        if not s.ocr_auto_done:
            # until 1.0.1 "tesseract" was the silent default (and "windows" secretly ran Tesseract too);
            # on Windows that meant one tesseract.exe start per subtitle box -> seconds of delay
            for q in s.profiles:
                if q.get("ocr_engine") in ("tesseract", "windows", None):
                    q["ocr_engine"] = "auto"
            s.ocr_auto_done = True
        return s

    def save(self) -> None:
        p = self.path()
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(asdict(self), ensure_ascii=False, indent=2), encoding="utf-8")
        try:
            tmp.chmod(0o600)        # contains API keys
        except OSError:
            pass
        tmp.replace(p)
