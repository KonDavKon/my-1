"""Live edits made from your own camera picture, so no video files are needed.

Every effect is a function
    (cam, first, t, trig, dur, face, caption) -> BGR image
    cam      current camera frame
    first    the camera frame at the moment the edit started (for freeze frames)
    t        seconds since the edit started
    trig     the impact moment, seconds since the edit started
    dur      length of the edit in seconds
    face     (x, y) centre of the face in `cam`, or None
    caption  text from config.json ("" -> the effect's own default)
"""
from __future__ import annotations

import cv2
import numpy as np

from hud import DARK, RED, SERIF, WHITE, _centered

EFFECTS = {}
DEFAULT_CAPTION = {}


def effect(name: str, caption: str = ""):
    def register(fn):
        EFFECTS[name] = fn
        DEFAULT_CAPTION[name] = caption
        return fn
    return register


def render(name: str, cam, first, t, trig, dur, face, caption) -> np.ndarray:
    return EFFECTS[name](cam, first, t, trig, dur, face, caption or DEFAULT_CAPTION[name])


# ---------------------------------------------------------------- helpers

def _ease(x: float) -> float:
    x = min(max(x, 0.0), 1.0)
    return x * x * (3 - 2 * x)


def zoom(img: np.ndarray, centre, factor: float) -> np.ndarray:
    """Crop around `centre` by `factor` (>1 zooms in) and scale back to the original size."""
    h, w = img.shape[:2]
    if factor <= 1.0:
        return img
    cx, cy = centre if centre is not None else (w / 2, h / 2)
    cw, ch = w / factor, h / factor
    x0 = int(min(max(cx - cw / 2, 0), w - cw))
    y0 = int(min(max(cy - ch / 2, 0), h - ch))
    return cv2.resize(img[y0:y0 + int(ch), x0:x0 + int(cw)], (w, h), interpolation=cv2.INTER_LINEAR)


def grey(img: np.ndarray, amount: float) -> np.ndarray:
    g = cv2.cvtColor(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), cv2.COLOR_GRAY2BGR)
    return cv2.addWeighted(img, 1 - amount, g, amount, 0)


def tint(img: np.ndarray, bgr, amount: float) -> np.ndarray:
    return cv2.addWeighted(img, 1 - amount, np.full_like(img, bgr), amount, 0)


def contrast(img: np.ndarray, gain: float, bias: float = 0.0) -> np.ndarray:
    return cv2.convertScaleAbs(img, alpha=gain, beta=bias - 128 * (gain - 1))


def vignette(img: np.ndarray, strength: float) -> np.ndarray:
    h, w = img.shape[:2]
    y, x = np.ogrid[:h, :w]
    d = np.sqrt(((x - w / 2) / (w / 2)) ** 2 + ((y - h / 2) / (h / 2)) ** 2)
    mask = np.clip(1 - strength * d ** 2, 0, 1)[..., None]
    return (img * mask).astype(np.uint8)


def title(img: np.ndarray, text: str, y_rel: float, size_rel: float, color=RED, font=SERIF, pop: float = 0.0) -> None:
    h, w = img.shape[:2]
    scale = size_rel * w / 300 * (1 + 0.35 * pop)
    _centered(img, text, w / 2, h * y_rel, scale, color, max(2, int(scale * 2)), font, outline=DARK)


def _pop(t: float, start: float, length: float = 0.25) -> float:
    """1 -> 0 during `length` seconds after `start` (text punches in, then settles)."""
    return max(0.0, 1.0 - (t - start) / length) if t >= start else 0.0


# ---------------------------------------------------------------- effects

@effect("wasted", "WASTED")
def wasted(cam, first, t, trig, dur, face, caption):
    """Slow zoom and fade to grey; at the impact the red title drops in (GTA style)."""
    img = zoom(cam, face, 1.0 + 0.25 * t / max(dur, 1e-6))
    img = grey(img, _ease(t / max(trig, 1e-6)))
    if t >= trig:
        img = contrast(tint(img, (30, 30, 60), 0.25), 1.15, -25)
        h = img.shape[0]
        band = img.copy()
        cv2.rectangle(band, (0, int(h * 0.42)), (img.shape[1], int(h * 0.64)), (0, 0, 0), -1)
        img = cv2.addWeighted(band, 0.6, img, 0.4, 0)
        title(img, caption, 0.53, 1.1, RED, pop=_pop(t, trig))
    return img


@effect("finished", "FINISHED")
def finished(cam, first, t, trig, dur, face, caption):
    """Freeze frame bathed in red stage light, creeping zoom, title at the impact."""
    img = zoom(first, face, 1.05 + 0.2 * _ease(t / max(dur, 1e-6)))
    img = contrast(grey(img, 0.6), 1.5, -10)
    img = tint(img, (20, 20, 200), 0.35 if t < trig else 0.45)
    img = vignette(img, 0.9)
    if t >= trig:
        title(img, caption, 0.5, 1.25, (40, 40, 255), pop=_pop(t, trig))
    return img


@effect("countdown")
def countdown(cam, first, t, trig, dur, face, caption):
    """THREE / TWO / ONE with a punch-in zoom on each word, then the caption (if any) at the impact."""
    words = ["THREE", "TWO", "ONE"]
    step = max(trig, 1e-6) / len(words)
    if t < trig:
        i = min(int(t / step), len(words) - 1)
        local = (t - i * step) / step
        img = zoom(cam, face, 1.35 - 0.25 * _ease(local) + 0.15 * i)
        img = contrast(grey(img, 0.35), 1.2)
        title(img, words[i], 0.82, 1.0, RED, pop=_pop(t, i * step))
    else:
        img = zoom(cam, face, 1.8 - 0.4 * _ease((t - trig) / 0.4))
        img = contrast(img, 1.25)
        if caption:
            title(img, caption, 0.82, 1.0, RED, pop=_pop(t, trig))
    return img


@effect("zoom", "LOCKED IN")
def zoom_in(cam, first, t, trig, dur, face, caption):
    """Punch in on the face, cold teal grade, title at the impact."""
    factor = 1.0 + 0.7 * _ease(t / max(trig, 1e-6)) if t < trig else 1.9
    img = zoom(cam, face, factor)
    img = contrast(tint(img, (120, 110, 20), 0.18), 1.3)
    img = vignette(img, 0.6)
    if t >= trig:
        title(img, caption, 0.85, 0.9, WHITE, pop=_pop(t, trig))
    return img


@effect("glitch", "AURA +1000")
def glitch(cam, first, t, trig, dur, face, caption):
    """RGB split, slice shifts and scanlines that peak at the impact."""
    rng = np.random.default_rng(int(t * 30))
    near = max(0.0, 1.0 - abs(t - trig) / 0.6)
    amount = 0.25 + 0.75 * near
    img = cam.copy()
    shift = int(4 + 18 * amount)
    b, g, r = cv2.split(img)
    img = cv2.merge([np.roll(b, -shift, axis=1), g, np.roll(r, shift, axis=1)])
    h = img.shape[0]
    for _ in range(int(3 + 10 * amount)):
        y = int(rng.integers(0, h - 8))
        hh = int(rng.integers(4, max(5, h // 12)))
        img[y:y + hh] = np.roll(img[y:y + hh], int(rng.integers(-40, 40) * amount), axis=1)
    img[::3] = (img[::3] * 0.6).astype(np.uint8)
    img = contrast(img, 1.2)
    if t >= trig:
        title(img, caption, 0.5, 0.95, WHITE if int(t * 8) % 2 else RED, font=cv2.FONT_HERSHEY_DUPLEX, pop=_pop(t, trig))
    return img
