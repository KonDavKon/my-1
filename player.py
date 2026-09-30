"""The edit state machine: WAITING -> (pre sound, "incoming") -> clip plays -> post sound -> WAITING.

All times are passed in (`now`, seconds), so it is easy to test and works the same for a live camera and
for a video file used as the camera.
"""
from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from audio import Audio
from config import Config, Edit

IDLE, PRE, PLAY, POST = "idle", "pre", "play", "post"
POST_DURATION = 0.6
IMPACT_DURATION = 0.5


@dataclass
class View:
    state: str
    edit: Edit | None = None
    frame: np.ndarray | None = None   # current clip frame while playing
    progress: float = 0.0             # 0..1 through the "incoming" phase
    impact: float = 0.0               # 1 -> 0 right after trigger_time (drives flash / shake / caption pop)
    impacted: bool = False            # trigger_time has been reached (the caption shows from then on)
    t: float = 0.0                    # seconds since the clip / effect started
    play_id: int = 0                  # changes with every playback (effects use it to grab their first frame)


class EditPlayer:
    def __init__(self, cfg: Config, audio: Audio):
        self.cfg, self.audio = cfg, audio
        self.state, self.edit = IDLE, None
        self._t_state = 0.0
        self._cooldown_until = 0.0
        self._cap: cv2.VideoCapture | None = None
        self._fps, self._frame_idx, self._last_frame = 30.0, 0, None
        self._impact_t: float | None = None
        self._impact_done = False
        self._play_id = 0

    @property
    def busy(self) -> bool:
        return self.state != IDLE

    def start(self, edit: Edit, now: float) -> bool:
        if self.busy or now < self._cooldown_until:
            return False
        self.edit, self.state, self._t_state = edit, PRE, now
        self.audio.play(self.cfg.pre_edit_sound)
        return True

    def _begin_play(self, now: float) -> None:
        e = self.edit
        self._last_frame = None
        if e.file is not None:
            self._cap = cv2.VideoCapture(str(e.file))
            self._fps = self._cap.get(cv2.CAP_PROP_FPS) or 30.0
            if e.start > 0:
                self._cap.set(cv2.CAP_PROP_POS_MSEC, e.start * 1000)
            self._frame_idx = int(e.start * self._fps)
        self._impact_t, self._impact_done = None, False
        self._play_id += 1
        self.state, self._t_state = PLAY, now
        if e.sound is not None:
            self.audio.play(e.sound)
        elif e.file is not None:
            self.audio.play(self.audio.clip_audio(e.file, e.start, e.end))

    def _finish_play(self, now: float) -> None:
        if self._cap is not None:
            self._cap.release()
            self._cap = None
        self.audio.play(self.cfg.post_edit_sound)
        self.state, self._t_state = POST, now

    def update(self, now: float) -> View:
        if self.state == PRE and now - self._t_state >= self.cfg.pre_edit_duration:
            self._begin_play(now)
        if self.state == PLAY:
            e = self.edit
            clip_time = e.start + (now - self._t_state)
            if not self._impact_done and clip_time >= e.trigger_time:
                self._impact_done, self._impact_t = True, now
                self.audio.play(self.cfg.impact_sound)
            end = e.end
            if end is not None and clip_time >= end:
                self._finish_play(now)
            elif self._cap is not None:
                wanted = int(clip_time * self._fps)
                while self._frame_idx <= wanted:
                    ok, frame = self._cap.read()
                    if not ok:
                        break
                    self._frame_idx += 1
                    self._last_frame = frame
                else:
                    ok = True
                if not ok:
                    self._finish_play(now)
        if self.state == POST and now - self._t_state >= POST_DURATION:
            self.state = IDLE
            self._cooldown_until = now + self.edit.cooldown

        impact = 0.0
        if self._impact_t is not None and self.state in (PLAY, POST):
            impact = max(0.0, 1.0 - (now - self._impact_t) / IMPACT_DURATION)
        if self.state == IDLE:
            return View(IDLE)
        if self.state == PRE:
            return View(PRE, self.edit, progress=min(1.0, (now - self._t_state) / max(self.cfg.pre_edit_duration, 1e-6)))
        t = now - self._t_state if self.state == PLAY else (self.edit.end or 0.0) - self.edit.start
        return View(self.state, self.edit, frame=self._last_frame, impact=impact, impacted=self._impact_done,
                    t=t, play_id=self._play_id)
