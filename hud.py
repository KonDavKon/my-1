"""Drawing: the "monitor" look (LIVE badge, REC timecode, green face box) and the edit panel."""
from __future__ import annotations

import random

import cv2
import numpy as np

GREEN = (90, 255, 120)
RED = (40, 40, 235)
WHITE = (255, 255, 255)
DARK = (24, 22, 20)
FONT = cv2.FONT_HERSHEY_SIMPLEX
SERIF = cv2.FONT_HERSHEY_TRIPLEX


def fit_cover(img: np.ndarray, size: tuple[int, int]) -> np.ndarray:
    w, h = size
    scale = max(w / img.shape[1], h / img.shape[0])
    resized = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA if scale < 1 else cv2.INTER_LINEAR)
    y0, x0 = (resized.shape[0] - h) // 2, (resized.shape[1] - w) // 2
    return resized[y0:y0 + h, x0:x0 + w]


def fmt_timecode(t: float, fps: int = 30) -> str:
    whole = int(t)
    return f"{whole // 3600:02d}:{whole // 60 % 60:02d}:{whole % 60:02d}:{int((t - whole) * fps):02d}"


def _text(img, s, org, scale, color, thick=1, font=FONT, outline=None):
    if outline is not None:
        cv2.putText(img, s, org, font, scale, outline, thick + 3, cv2.LINE_AA)
    cv2.putText(img, s, org, font, scale, color, thick, cv2.LINE_AA)


def _centered(img, s, cx, cy, scale, color, thick=1, font=FONT, outline=None):
    (w, h), _ = cv2.getTextSize(s, font, scale, thick)
    _text(img, s, (int(cx - w / 2), int(cy + h / 2)), scale, color, thick, font, outline)


def _brackets(img, rect, color, length=14, thick=2):
    x0, y0, x1, y1 = rect
    for (x, y, dx, dy) in ((x0, y0, 1, 1), (x1, y0, -1, 1), (x0, y1, 1, -1), (x1, y1, -1, -1)):
        cv2.line(img, (x, y), (x + dx * length, y), color, thick, cv2.LINE_AA)
        cv2.line(img, (x, y), (x, y + dy * length), color, thick, cv2.LINE_AA)


def panel_rect(kind: str, w: int, h: int) -> tuple[int, int, int, int]:
    if kind == "large":
        pw, ph = int(w * 0.70), int(h * 0.62)
        x0 = (w - pw) // 2
        return x0, int(h * 0.14), x0 + pw, int(h * 0.14) + ph
    pw, ph = int(w * 0.31), int(h * 0.31)
    return w - pw - 24, 64, w - 24, 64 + ph


def draw_base(img: np.ndarray, t: float) -> None:
    h, w = img.shape[:2]
    if int(t * 2) % 2 == 0:
        cv2.circle(img, (30, 30), 7, RED, -1, cv2.LINE_AA)
    _text(img, "LIVE", (46, 37), 0.6, WHITE, 2, outline=DARK)
    _text(img, "CAM 01", (w - 110, 37), 0.55, GREEN, 1, outline=DARK)
    if int(t * 2) % 2 == 0:
        cv2.circle(img, (30, h - 28), 5, RED, -1, cv2.LINE_AA)
    _text(img, "REC", (44, h - 22), 0.5, GREEN, 1, outline=DARK)
    _text(img, fmt_timecode(t), (92, h - 22), 0.5, GREEN, 1, outline=DARK)
    _brackets(img, (10, 10, w - 10, h - 10), GREEN, 22, 1)


def draw_face_box(img: np.ndarray, box: tuple[float, float, float, float], label: str = "SUBJECT") -> None:
    x0, y0, x1, y1 = (int(v) for v in box)
    cv2.rectangle(img, (x0, y0), (x1, y1), GREEN, 1, cv2.LINE_AA)
    _brackets(img, (x0, y0, x1, y1), GREEN, 16, 2)
    _text(img, label, (x0 + 2, y1 + 16), 0.42, GREEN, 1, outline=DARK)


def _frame_panel(img, rect, fill=DARK):
    x0, y0, x1, y1 = rect
    cv2.rectangle(img, (x0, y0), (x1, y1), fill, -1)


def panel_idle(img: np.ndarray, rect, t: float) -> None:
    _frame_panel(img, rect)
    x0, y0, x1, y1 = rect
    cx, cy = (x0 + x1) // 2, (y0 + y1) // 2 - 8
    r = min(x1 - x0, y1 - y0) // 5
    cv2.circle(img, (cx, cy), r, GREEN, 1, cv2.LINE_AA)
    cv2.circle(img, (cx, cy), 3, GREEN, -1, cv2.LINE_AA)
    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        cv2.line(img, (cx + dx * (r - 8), cy + dy * (r - 8)), (cx + dx * (r + 10), cy + dy * (r + 10)), GREEN, 1, cv2.LINE_AA)
    _centered(img, "WAITING" + "." * (int(t * 2) % 4), cx, cy + r + 24, 0.5, GREEN, 1)
    cv2.rectangle(img, (x0, y0), (x1, y1), GREEN, 1)


def panel_pre(img: np.ndarray, rect, progress: float, t: float) -> None:
    _frame_panel(img, rect)
    x0, y0, x1, y1 = rect
    cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
    if int(t * 6) % 2 == 0:
        _centered(img, "INCOMING", cx, cy - 6, 0.8, RED, 2)
    bar_w = int((x1 - x0) * 0.6)
    bx = cx - bar_w // 2
    cv2.rectangle(img, (bx, cy + 22), (bx + bar_w, cy + 30), GREEN, 1)
    cv2.rectangle(img, (bx, cy + 22), (bx + int(bar_w * progress), cy + 30), GREEN, -1)
    cv2.rectangle(img, (x0, y0), (x1, y1), GREEN, 1)


def panel_clip(img: np.ndarray, rect, clip_frame: np.ndarray | None) -> None:
    x0, y0, x1, y1 = rect
    if clip_frame is None:
        _frame_panel(img, rect)
    else:
        img[y0:y1, x0:x1] = fit_cover(clip_frame, (x1 - x0, y1 - y0))
    cv2.rectangle(img, (x0, y0), (x1, y1), GREEN, 1)


def caption(img: np.ndarray, rect, text: str, pop: float = 0.0) -> None:
    if not text:
        return
    x0, y0, x1, y1 = rect
    scale = (0.9 + 0.5 * pop) * (x1 - x0) / 300
    _centered(img, text, (x0 + x1) / 2, y1 - (y1 - y0) * 0.22, scale, RED, 2, SERIF, outline=DARK)


def apply_impact(img: np.ndarray, intensity: float, rng=random) -> np.ndarray:
    """Screen shake + white flash that fade out with `intensity` (1 -> 0)."""
    if intensity <= 0:
        return img
    h, w = img.shape[:2]
    amp = int(14 * intensity)
    m = np.float32([[1, 0, rng.randint(-amp, amp)], [0, 1, rng.randint(-amp, amp)]])
    out = cv2.warpAffine(img, m, (w, h), borderMode=cv2.BORDER_REPLICATE)
    a = 0.55 * intensity ** 2
    return cv2.addWeighted(out, 1 - a, np.full_like(out, 255), a, 0)
