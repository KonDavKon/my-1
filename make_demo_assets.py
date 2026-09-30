"""Generate the default sounds (sounds/) so the app runs out of the box; demo_clips() makes test videos.

Replace them with your own: put sounds in sounds/, video clips in videos/, and point config.json at them.
"""
from __future__ import annotations

import wave
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent
RATE = 44100


def _wav(path: Path, samples: np.ndarray) -> None:
    data = (np.clip(samples, -1, 1) * 32000).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(data.tobytes())


def make_sounds(folder: Path) -> None:
    folder.mkdir(exist_ok=True)
    t = np.linspace(0, 1.0, RATE, endpoint=False)                       # pre_edit: rising sweep
    _wav(folder / "pre_edit.wav", 0.5 * np.sin(2 * np.pi * (220 * t + 330 * t ** 2)) * t)
    t = np.linspace(0, 0.6, int(RATE * 0.6), endpoint=False)            # post_edit: two-note chime
    chime = np.sin(2 * np.pi * 660 * t) * np.exp(-6 * t) + np.sin(2 * np.pi * 880 * np.clip(t - 0.15, 0, None)) * (t > 0.15) * np.exp(-6 * np.clip(t - 0.15, 0, None))
    _wav(folder / "post_edit.wav", 0.5 * chime)
    t = np.linspace(0, 0.5, int(RATE * 0.5), endpoint=False)            # impact: low thump
    rng = np.random.default_rng(1)
    _wav(folder / "impact.wav", 0.8 * (np.sin(2 * np.pi * 55 * t) + 0.3 * rng.standard_normal(t.size)) * np.exp(-9 * t))


def make_clip(path: Path, title: str, hue: int, size=(480, 360), seconds=4.0, impact=2.0, fps=30) -> None:
    w, h = size
    out = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), fps, size)
    for i in range(int(seconds * fps)):
        t = i / fps
        hsv = np.zeros((h, w, 3), np.uint8)
        hsv[..., 0] = (hue + (np.arange(w)[None, :] * 40 // w) + int(t * 20)) % 180
        hsv[..., 1], hsv[..., 2] = 200, 150 + (np.arange(h)[:, None] * 80 // h)
        img = cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)
        cx, cy = int(w / 2 + 120 * np.sin(t * 3)), int(h / 2 + 60 * np.cos(t * 4))
        cv2.circle(img, (cx, cy), 46, (255, 255, 255), -1, cv2.LINE_AA)
        cv2.putText(img, title, (24, 70), cv2.FONT_HERSHEY_DUPLEX, 1.4, (255, 255, 255), 3, cv2.LINE_AA)
        cv2.putText(img, f"{t:0.1f}s  (impact at {impact:0.1f}s)", (24, h - 24), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2, cv2.LINE_AA)
        if abs(t - impact) < 0.12:
            img = cv2.addWeighted(img, 0.3, np.full_like(img, 255), 0.7, 0)
        out.write(img)
    out.release()


def main() -> None:
    make_sounds(ROOT / "sounds")
    print(f"Sounds in {ROOT / 'sounds'}")


def demo_clips() -> None:
    """Coloured test clips in videos/ (for trying "file" edits without having any real clips)."""
    (ROOT / "videos").mkdir(exist_ok=True)
    for name, title, hue in (("demo_1", "EDIT 1", 10), ("demo_2", "EDIT 2", 60)):
        make_clip(ROOT / "videos" / f"{name}.mp4", title, hue)
    print(f"Demo clips in {ROOT / 'videos'}")


if __name__ == "__main__":
    main()
