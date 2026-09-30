"""config.json loading. Times accept seconds (2.5) or "MM:SS.mmm" / "HH:MM:SS.mmm" strings."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from autoedit import TEMPLATES
from effects import EFFECTS

ALL_EFFECTS = (*TEMPLATES, *EFFECTS)

SIZES = ("panel", "large")


def parse_time(value) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    parts = str(value).strip().split(":")
    if not 1 <= len(parts) <= 3:
        raise ValueError(f"bad time {value!r}: use seconds or MM:SS.mmm")
    seconds = 0.0
    for part in parts:
        seconds = seconds * 60 + float(part)
    return seconds


@dataclass
class Edit:
    name: str
    file: Path | None      # a video clip ...
    effect: str | None     # ... or a live effect made from the camera (effects.py); exactly one of the two
    sound: Path | None     # optional sound played when the edit starts (a clip's own audio plays otherwise)
    start: float
    end: float | None      # None: until the end of the clip
    trigger_time: float    # moment inside the clip where the "impact" hits (flash, shake, impact sound)
    triggers: list[str]    # gestures / expressions that start this edit
    caption: str
    size: str              # "panel" (corner) or "large" (centre)
    cooldown: float        # seconds before any edit can start again after this one


@dataclass
class Config:
    edits: list[Edit]
    pre_edit_sound: Path | None
    post_edit_sound: Path | None
    impact_sound: Path | None
    pre_edit_duration: float
    cooldown: float
    base_dir: Path
    auto_every: tuple[float, float] = (10.0, 20.0)   # self-made edits start every min..max seconds
    captions: dict[str, list[str]] = field(default_factory=dict)   # event name / "generic" -> caption choices

    def auto_edits(self) -> list[Edit]:
        return [e for e in self.edits if "auto" in e.triggers]

    def caption_for(self, event: str | None, rng=None) -> str:
        import random
        choices = self.captions.get(event or "", []) or self.captions.get("generic", [])
        return (rng or random).choice(choices) if choices else ""

    def edits_for(self, trigger: str) -> list[Edit]:
        return [e for e in self.edits if trigger in e.triggers]

    def all_triggers(self) -> set[str]:
        return {t for e in self.edits for t in e.triggers}


def _path(base: Path, value) -> Path | None:
    return (base / value) if value else None


def load(path: str | Path) -> Config:
    path = Path(path)
    raw = json.loads(path.read_text(encoding="utf-8"))
    base = path.resolve().parent
    default_cooldown = float(raw.get("cooldown", 6.0))
    edits = []
    for i, e in enumerate(raw.get("edits", []), 1):
        where = f"edit #{i} ({e.get('name', e.get('file', e.get('effect', '?')))})"
        if ("file" in e) == ("effect" in e):
            raise ValueError(f"{where}: give either \"file\" (a video) or \"effect\" (one of {', '.join(ALL_EFFECTS)})")
        if "effect" in e and e["effect"] not in ALL_EFFECTS:
            raise ValueError(f"{where}: unknown effect {e['effect']!r}; valid: {', '.join(ALL_EFFECTS)}")
        start = parse_time(e.get("start", 0))
        end = parse_time(e["end"]) if e.get("end") is not None else (start + 3.0 if "effect" in e else None)
        trigger_time = parse_time(e.get("trigger_time", start + 1.2 if "effect" in e else start))
        if end is not None and end <= start:
            raise ValueError(f"{where}: \"end\" must be after \"start\"")
        if trigger_time < start or (end is not None and trigger_time > end):
            raise ValueError(f"{where}: \"trigger_time\" must lie between start and end")
        size = e.get("size", "panel")
        if size not in SIZES:
            raise ValueError(f"{where}: \"size\" must be one of {SIZES}")
        trig = e.get("trigger", [])
        edits.append(Edit(
            name=e.get("name", Path(e["file"]).stem if "file" in e else e["effect"]),
            file=base / e["file"] if "file" in e else None, effect=e.get("effect"),
            sound=_path(base, e.get("sound")), start=start, end=end,
            trigger_time=trigger_time, triggers=[trig] if isinstance(trig, str) else list(trig),
            caption=e.get("caption", ""), size=size, cooldown=float(e.get("cooldown", default_cooldown)),
        ))
    if not edits:
        raise ValueError("config has no edits")
    return Config(
        edits=edits,
        pre_edit_sound=_path(base, raw.get("pre_edit_sound")),
        post_edit_sound=_path(base, raw.get("post_edit_sound")),
        impact_sound=_path(base, raw.get("impact_sound")),
        pre_edit_duration=float(raw.get("pre_edit_duration", 1.0)),
        cooldown=default_cooldown,
        base_dir=base,
        auto_every=_auto_every(raw.get("auto_every", [10, 20])),
        captions={k: [v] if isinstance(v, str) else list(v) for k, v in raw.get("captions", {}).items()},
    )


def _auto_every(value) -> tuple[float, float]:
    lo, hi = (value, value) if isinstance(value, (int, float)) else (value[0], value[-1])
    if not 0 < float(lo) <= float(hi):
        raise ValueError("\"auto_every\" must be seconds or [min, max] with 0 < min <= max")
    return float(lo), float(hi)
