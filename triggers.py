"""What starts an edit: gestures and facial expressions from MediaPipe landmarks (pure numpy, testable)."""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

EXTENDED_RATIO = 1.3        # tip-to-wrist / base-to-wrist: curled 0.7-1.0, extended 1.6+ (measured on real photos)
JAW_OPEN_MIN = 0.5
SMILE_MIN = 0.5
BLINK_MIN = 0.6
BROWS_MIN = 0.5
LOOK_AWAY_DEG = 25.0

WRIST, THUMB_TIP, INDEX_MCP, MIDDLE_MCP = 0, 4, 5, 9
FINGERS = {"index": (5, 8), "middle": (9, 12), "ring": (13, 16), "pinky": (17, 20)}  # (base, tip)
HAND_CONNECTIONS = (
    (0, 1), (1, 2), (2, 3), (3, 4), (0, 5), (5, 6), (6, 7), (7, 8), (5, 9), (9, 10), (10, 11), (11, 12),
    (9, 13), (13, 14), (14, 15), (15, 16), (13, 17), (17, 18), (18, 19), (19, 20), (0, 17),
)


@dataclass
class Ctx:
    """Everything detected in the current frame."""
    hands: list[np.ndarray] = field(default_factory=list)    # each (21, 2) pixels
    face: np.ndarray | None = None                            # (478, 2) pixels, or None
    blend: dict[str, float] = field(default_factory=dict)     # face blendshape scores
    pose: tuple[float, float] | None = None                   # head yaw, pitch in degrees


def _dist(a, b) -> float:
    return float(np.linalg.norm(a - b))


def hand_kind(h: np.ndarray) -> str | None:
    """"point_up", "shaka", "thumbs_up", "fist", "peace", "open" or None."""
    wrist = h[WRIST]
    ext = {n: _dist(h[t], wrist) > EXTENDED_RATIO * _dist(h[b], wrist) for n, (b, t) in FINGERS.items()}
    palm = _dist(wrist, h[MIDDLE_MCP])
    thumb_out = _dist(h[THUMB_TIP], h[INDEX_MCP]) > 0.8 * palm
    n_ext = sum(ext.values())
    if ext["index"] and not (ext["middle"] or ext["ring"] or ext["pinky"]):
        v = h[8] - h[INDEX_MCP]
        if -v[1] / (np.linalg.norm(v) + 1e-6) > 0.5:      # image y grows downwards
            return "point_up"
    if thumb_out and ext["pinky"] and not (ext["index"] or ext["middle"] or ext["ring"]):
        return "shaka"
    if n_ext == 0:
        if thumb_out and h[THUMB_TIP][1] < h[INDEX_MCP][1] - 0.5 * palm:
            return "thumbs_up"
        return "fist"
    if ext["index"] and ext["middle"] and not (ext["ring"] or ext["pinky"]):
        return "peace"
    if n_ext >= 3:
        return "open"
    return None


def head_pose(matrix) -> tuple[float, float]:
    rot = np.asarray(matrix, dtype=float)[:3, :3]
    rot = rot / np.linalg.norm(rot, axis=0)
    return (math.degrees(math.atan2(rot[0, 2], rot[2, 2])),
            math.degrees(math.atan2(-rot[1, 2], math.hypot(rot[0, 2], rot[2, 2]))))


def _face_metrics(f: np.ndarray):
    width, height = _dist(f[234], f[454]), _dist(f[10], f[152])
    return width, height, f[[13, 14]].mean(axis=0), f[10]


def _kinds(c: Ctx) -> list[str | None]:
    return [hand_kind(h) for h in c.hands]


def _hand_mouth(c: Ctx) -> bool:
    if c.face is None:
        return False
    width, _, mouth, _ = _face_metrics(c.face)
    return any(k in (None, "open") and _dist(h.mean(axis=0), mouth) < 0.55 * width for h, k in zip(c.hands, _kinds(c)))


def _hands_up(c: Ctx, margin: float) -> bool:
    if c.face is None or len(c.hands) < 2:
        return False
    width, height, _, top = _face_metrics(c.face)
    centre = c.face[[234, 454]].mean(axis=0)
    return all(h.mean(axis=0)[1] < top[1] + margin * height and abs(h.mean(axis=0)[0] - centre[0]) < 1.3 * width
               for h in c.hands)


def _b(c: Ctx, *names: str) -> float:
    return sum(c.blend.get(n, 0.0) for n in names) / len(names)


CONDITIONS = {
    "fist": lambda c: "fist" in _kinds(c),
    "thumbs_up": lambda c: "thumbs_up" in _kinds(c),
    "point_up": lambda c: "point_up" in _kinds(c),
    "shaka": lambda c: "shaka" in _kinds(c),
    "peace": lambda c: "peace" in _kinds(c),
    "open_palm": lambda c: "open" in _kinds(c),
    "hand_mouth": _hand_mouth,
    "hands_head": lambda c: _hands_up(c, 0.25),
    "hands_up": lambda c: _hands_up(c, -0.3),
    "smile": lambda c: _b(c, "mouthSmileLeft", "mouthSmileRight") > SMILE_MIN,
    "mouth_open": lambda c: _b(c, "jawOpen") > JAW_OPEN_MIN,
    "eyes_closed": lambda c: _b(c, "eyeBlinkLeft", "eyeBlinkRight") > BLINK_MIN,
    "eyebrows_up": lambda c: _b(c, "browInnerUp") > BROWS_MIN,
    "look_away": lambda c: c.pose is not None and (abs(c.pose[0]) > LOOK_AWAY_DEG or abs(c.pose[1]) > LOOK_AWAY_DEG),
    "face_lost": lambda c: c.face is None,
}
NAMES = tuple(CONDITIONS)
HOLD = {"eyes_closed": 0.7, "face_lost": 1.0, "look_away": 0.5}   # seconds a condition must last; default 0.25


class TriggerEngine:
    """Fires a trigger name once when its condition has held long enough; it re-arms after the condition
    has been false for `rearm` seconds."""

    def __init__(self, names, rearm: float = 0.4):
        unknown = sorted(set(names) - set(NAMES))
        if unknown:
            raise ValueError(f"unknown trigger(s) {unknown}; valid: {', '.join(NAMES)}")
        self.names, self.rearm = list(names), rearm
        self._since = {n: None for n in self.names}
        self._false_since = {n: None for n in self.names}
        self._armed = {n: True for n in self.names}

    def update(self, now: float, ctx: Ctx) -> list[str]:
        fired = []
        for n in self.names:
            if CONDITIONS[n](ctx):
                self._false_since[n] = None
                if self._since[n] is None:
                    self._since[n] = now
                if self._armed[n] and now - self._since[n] >= HOLD.get(n, 0.25):
                    fired.append(n)
                    self._armed[n] = False
            else:
                self._since[n] = None
                if self._false_since[n] is None:
                    self._false_since[n] = now
                if now - self._false_since[n] >= self.rearm:
                    self._armed[n] = True
        return fired
