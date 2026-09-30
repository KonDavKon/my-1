"""Optional sound: pygame plays wav files; the audio track of an edit is cut out with ffmpeg first."""
from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

CACHE = Path(__file__).resolve().parent / ".cache"


class Audio:
    def __init__(self, enabled: bool = True):
        self.ok = False
        self._sounds: dict[str, object] = {}
        if not enabled:
            return
        try:
            import pygame
            pygame.mixer.init()
            self._pg = pygame
            self.ok = True
        except Exception as exc:  # no pygame, or no audio device
            print(f"Sound is off ({exc}).", file=sys.stderr)

    def play(self, path: Path | None) -> None:
        if not (self.ok and path and Path(path).exists()):
            return
        key = str(path)
        if key not in self._sounds:
            self._sounds[key] = self._pg.mixer.Sound(key)
        self._sounds[key].play()

    def stop_all(self) -> None:
        if self.ok:
            self._pg.mixer.stop()

    def clip_audio(self, video: Path, start: float, end: float | None) -> Path | None:
        """The audio of video[start:end] as a wav in .cache (None if the clip has no sound)."""
        if not video.exists():
            return None
        stamp = f"{video.resolve()}|{video.stat().st_mtime_ns}|{start}|{end}"
        out = CACHE / (hashlib.sha1(stamp.encode()).hexdigest()[:16] + ".wav")
        if out.exists():
            return out if out.stat().st_size > 1000 else None
        try:
            import imageio_ffmpeg
            CACHE.mkdir(exist_ok=True)
            cmd = [imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-loglevel", "error", "-ss", str(start)]
            if end is not None:
                cmd += ["-to", str(end)]
            cmd += ["-i", str(video), "-vn", "-ac", "2", "-ar", "44100", str(out)]
            subprocess.run(cmd, capture_output=True, timeout=120, check=True)
        except Exception:
            out.write_bytes(b"")     # remember that there is nothing to play
            return None
        return out if out.stat().st_size > 1000 else None
