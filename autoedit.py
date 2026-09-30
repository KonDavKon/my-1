"""Self-made edits: the camera is recorded into a rolling buffer, and edits are cut from YOUR recent footage.

Recorder keeps the last seconds of camera frames (plus the face position and the events seen, like a smile
or a hand at the mouth). When an edit starts, `build()` snapshots the frames it needs and returns an object
whose `render(t)` gives the edit picture at time t.

Templates:
    replay         slow-motion replay of a moment, then a freeze with a punch-in; a caption label on top
    freeze_wasted  slow-mo to a grey freeze frame, WASTED, then the picture breaks up and fades to black
    montage        your moment full-size plus two other moments as insets; the caption drops word by word
    rewind         the last seconds played backwards, VHS style, then a freeze and the caption
"""
from __future__ import annotations

import bisect
import random
from collections import deque
from dataclasses import dataclass, field
from functools import lru_cache

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

REC_SIZE = (400, 300)
REC_FPS = 15.0
BUFFER_SECONDS = 20.0
RED = (40, 40, 235)

TEMPLATES = ("replay", "freeze_wasted", "montage", "rewind")


# ---------------------------------------------------------------- recording

@dataclass
class Shot:
    t: float
    frame: np.ndarray
    face: tuple[float, float] | None


@dataclass
class Recorder:
    seconds: float = BUFFER_SECONDS
    fps: float = REC_FPS
    shots: deque = field(default_factory=deque)
    events: list = field(default_factory=list)       # [time, name, used]

    def add(self, t: float, frame: np.ndarray, face=None) -> None:
        if self.shots and t - self.shots[-1].t < 1.0 / self.fps - 1e-6:
            return
        h, w = frame.shape[:2]
        small = cv2.resize(frame, REC_SIZE, interpolation=cv2.INTER_AREA)
        if face is not None:
            face = (face[0] * REC_SIZE[0] / w, face[1] * REC_SIZE[1] / h)
        self.shots.append(Shot(t, small, face))
        while self.shots and self.shots[0].t < t - self.seconds:
            self.shots.popleft()
        self.events = [e for e in self.events if e[0] >= t - self.seconds]

    def mark(self, t: float, name: str) -> None:
        self.events.append([t, name, False])

    def span(self) -> float:
        return self.shots[-1].t - self.shots[0].t if len(self.shots) > 1 else 0.0

    def segment(self, t0: float, t1: float) -> list[Shot]:
        seg = [s for s in self.shots if t0 <= s.t <= t1]
        if not seg and self.shots:                   # nothing in range: the closest frame
            seg = [min(self.shots, key=lambda s: abs(s.t - (t0 + t1) / 2))]
        return seg

    def take_event(self) -> tuple[float, str] | None:
        """The newest event not used for an edit yet (and mark it used)."""
        for e in reversed(self.events):
            if not e[2]:
                e[2] = True
                return e[0], e[1]
        return None

    def random_moments(self, k: int, gap: float, rng=random) -> list[float]:
        if not self.shots:
            return []
        t0, t1 = self.shots[0].t + 1.0, self.shots[-1].t - 0.5
        picks: list[float] = []
        for _ in range(50):
            if len(picks) == k:
                break
            m = rng.uniform(t0, max(t0, t1))
            if all(abs(m - p) >= gap for p in picks):
                picks.append(m)
        return picks


# ---------------------------------------------------------------- drawing helpers

FONTS = {
    "sans": ("arialbd.ttf", "segoeuib.ttf", "DejaVuSans-Bold.ttf", "LiberationSans-Bold.ttf"),
    "serif": ("timesbd.ttf", "georgiab.ttf", "DejaVuSerif-Bold.ttf", "LiberationSerif-Bold.ttf"),
}


@lru_cache(maxsize=64)
def font(kind: str, size: int):
    for name in FONTS[kind]:
        for path in (name, f"C:/Windows/Fonts/{name}", f"/usr/share/fonts/truetype/dejavu/{name}",
                     f"/usr/share/fonts/truetype/liberation/{name}"):
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                continue
    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # Pillow < 10.1
        return ImageFont.load_default()


def draw_title(img: np.ndarray, text: str, y_rel: float, size_rel: float, color=RED, kind="serif") -> np.ndarray:
    """Big centred text with a dark outline (supports Cyrillic)."""
    if not text:
        return img
    h, w = img.shape[:2]
    size = max(10, int(h * size_rel))
    f = font(kind, size)
    while size > 10 and f.getbbox(text)[2] > w * 0.94:
        size = int(size * 0.9)
        f = font(kind, size)
    pil = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
    d = ImageDraw.Draw(pil)
    rgb = (color[2], color[1], color[0])
    d.text((w / 2, h * y_rel), text, font=f, fill=rgb, anchor="mm", stroke_width=max(1, size // 18), stroke_fill=(15, 12, 10))
    return cv2.cvtColor(np.asarray(pil), cv2.COLOR_RGB2BGR)


def draw_label(img: np.ndarray, text: str) -> np.ndarray:
    """A white bar across the top with dark text, like a story caption."""
    if not text:
        return img
    h, w = img.shape[:2]
    bar = int(h * 0.13)
    out = img.copy()
    out[:bar] = (245, 245, 245)
    pil = Image.fromarray(cv2.cvtColor(out, cv2.COLOR_BGR2RGB))
    ImageDraw.Draw(pil).text((w / 2, bar / 2), text, font=font("sans", int(bar * 0.55)), fill=(70, 70, 70), anchor="mm")
    return cv2.cvtColor(np.asarray(pil), cv2.COLOR_RGB2BGR)


def word_at(caption: str, t: float, start: float, step: float = 0.4) -> str:
    """Reveal a caption one word at a time from `start` (the last word stays)."""
    words = caption.split()
    if not words or t < start:
        return ""
    return words[min(int((t - start) / step), len(words) - 1)]


def zoom(img: np.ndarray, centre, factor: float) -> np.ndarray:
    if factor <= 1.0:
        return img
    h, w = img.shape[:2]
    cx, cy = centre if centre is not None else (w / 2, h / 2)
    cw, ch = w / factor, h / factor
    x0 = int(min(max(cx - cw / 2, 0), w - cw))
    y0 = int(min(max(cy - ch / 2, 0), h - ch))
    return cv2.resize(img[y0:y0 + int(ch), x0:x0 + int(cw)], (w, h))


def grey(img, amount):
    g = cv2.cvtColor(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), cv2.COLOR_GRAY2BGR)
    return cv2.addWeighted(img, 1 - amount, g, amount, 0)


def pixelate(img, block: int):
    if block <= 1:
        return img
    h, w = img.shape[:2]
    small = cv2.resize(img, (max(1, w // block), max(1, h // block)), interpolation=cv2.INTER_AREA)
    return cv2.resize(small, (w, h), interpolation=cv2.INTER_NEAREST)


def _ease(x):
    x = min(max(x, 0.0), 1.0)
    return x * x * (3 - 2 * x)


class Clip:
    """Frames of a recorded segment, sampled by time."""

    def __init__(self, shots: list[Shot]):
        self.shots = shots or [Shot(0.0, np.zeros((REC_SIZE[1], REC_SIZE[0], 3), np.uint8), None)]
        self.times = [s.t for s in self.shots]
        self.t0, self.length = self.times[0], self.times[-1] - self.times[0]

    def at(self, offset: float, loop: bool = False) -> Shot:
        if loop and self.length > 0:
            offset %= self.length
        i = bisect.bisect_left(self.times, self.t0 + offset)
        return self.shots[min(max(i, 0), len(self.shots) - 1)]

    def face(self):
        faces = [s.face for s in self.shots if s.face is not None]
        return faces[len(faces) // 2] if faces else None


# ---------------------------------------------------------------- templates

class AutoEdit:
    def __init__(self, template: str, clips: list[Clip], trig: float, dur: float, caption: str):
        self.template, self.clips, self.trig, self.dur, self.caption = template, clips, trig, dur, caption

    def render(self, t: float) -> np.ndarray:
        return getattr(self, "_" + self.template)(t)

    def _replay(self, t):
        c = self.clips[0]
        speed = c.length / max(self.trig, 1e-6) if c.length else 0.0        # the whole moment, slowed to fill trig
        shot = c.at(min(t, self.trig) * speed)
        img = shot.frame
        if t >= self.trig:
            img = zoom(img, shot.face or c.face(), 1.0 + 0.35 * _ease((t - self.trig) / 0.3))
            img = cv2.convertScaleAbs(img, alpha=1.15, beta=-10)
        return draw_label(img, self.caption)

    def _freeze_wasted(self, t):
        c = self.clips[0]
        speed = c.length / max(self.trig, 1e-6) if c.length else 0.0
        shot = c.at(min(t, self.trig) * speed)
        img = zoom(shot.frame, shot.face or c.face(), 1.0 + 0.15 * t / max(self.dur, 1e-6))
        img = grey(img, _ease(t / max(self.trig, 1e-6)))
        if t < self.trig:
            return img
        img = cv2.addWeighted(img, 0.75, np.full_like(img, (30, 30, 50)), 0.25, 0)
        breakup = _ease((t - self.trig - 1.0) / max(self.dur - self.trig - 1.0, 1e-6))
        if breakup > 0:
            img = pixelate(img, 1 + int(18 * breakup))
            img = (img * (1 - 0.85 * breakup)).astype(np.uint8)
        if breakup < 0.6:
            img = draw_title(img, self.caption or "WASTED", 0.5, 0.16, RED, "sans")
        return img

    def _montage(self, t):
        main = self.clips[0].at(t, loop=True).frame
        img = cv2.convertScaleAbs(main, alpha=1.1, beta=25)                  # washed-out, bright
        h, w = img.shape[:2]
        iw, ih = int(w * 0.3), int(h * 0.3)
        for k, clip in enumerate(self.clips[1:3]):
            x = int(w * 0.04) if k == 0 else w - iw - int(w * 0.04)
            y = int(h * 0.3) + k * int(h * 0.08)
            img[y:y + ih, x:x + iw] = cv2.resize(clip.at(t, loop=True).frame, (iw, ih))
            cv2.rectangle(img, (x, y), (x + iw - 1, y + ih - 1), (255, 255, 255), 1)
        return draw_title(img, word_at(self.caption, t, self.trig), 0.72, 0.2, RED, "serif")

    def _rewind(self, t):
        c = self.clips[0]
        if t < self.trig:
            speed = c.length / max(self.trig, 1e-6) if c.length else 0.0
            shot = c.at(c.length - t * speed)
            b, g, r = cv2.split(shot.frame)
            img = cv2.merge([np.roll(b, -4, axis=1), g, np.roll(r, 4, axis=1)])
            img[::2] = (img[::2] * 0.7).astype(np.uint8)
            y = int((t * 90) % img.shape[0])
            img[y:y + 6] = np.roll(img[y:y + 6], 25, axis=1)
            cv2.putText(img, "<< REWIND", (12, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2, cv2.LINE_AA)
            return img
        shot = c.at(0.0)
        img = zoom(shot.frame, shot.face or c.face(), 1.15)
        img = cv2.convertScaleAbs(img, alpha=1.2, beta=-15)
        return draw_title(img, word_at(self.caption, t, self.trig), 0.75, 0.2, RED, "serif")


def build(template: str, rec: Recorder, moment: float, trig: float, dur: float, caption: str, rng=random) -> AutoEdit:
    """Snapshot the footage for `template` around `moment` (seconds on the recorder clock)."""
    if template == "replay":
        clips = [Clip(rec.segment(moment - 2.0, moment + 0.8))]
    elif template == "freeze_wasted":
        clips = [Clip(rec.segment(moment - 1.2, moment + 0.3))]
    elif template == "rewind":
        clips = [Clip(rec.segment(moment - 3.0, moment))]
    elif template == "montage":
        others = [m for m in rec.random_moments(4, 1.5, rng) if abs(m - moment) >= 1.5][:2]
        clips = [Clip(rec.segment(m - 1.2, m + 1.2)) for m in [moment, *others]]
    else:
        raise ValueError(f"unknown template {template!r}")
    return AutoEdit(template, clips, trig, dur, caption)
