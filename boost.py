"""Confidence booster: a live "monitor" of your webcam that plays hype edits when you strike a pose.

    python boost.py                     # default webcam, config.json
    python boost.py --source 1          # another camera
    python boost.py --auto 5            # start an edit every 5 s (demo, no gestures needed)
    python boost.py --source clip.mp4 --headless --record out.mp4 --auto 3 --mute   # render without a window

Keys:  q / Esc quit,  1-9 start edit N,  space start a random edit,  f fullscreen.
"""
from __future__ import annotations

import argparse
import random
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import cv2
import mediapipe as mp
import numpy as np
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision

import config as cfgmod
import hud
import triggers
from audio import Audio
from player import IDLE, PLAY, POST, PRE, EditPlayer

ROOT = Path(__file__).resolve().parent
MODELS_DIR = ROOT / "models"
MODEL_URLS = {
    "hand_landmarker.task": "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task",
    "face_landmarker.task": "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task",
}
WINDOW = "MONITOR"
DET_SIZE = (640, 480)     # detection resolution
OUT_SIZE = (960, 720)     # what is shown / recorded


def ensure_model(name: str) -> str:
    path = MODELS_DIR / name
    if path.exists():
        return str(path)
    MODELS_DIR.mkdir(exist_ok=True)
    url = MODEL_URLS[name]
    tmp = path.with_name(path.name + ".part")   # a half-downloaded file must never look like a finished model
    try:
        with urllib.request.urlopen(url, timeout=30) as resp, open(tmp, "wb") as out:
            total, done = int(resp.headers.get("Content-Length") or 0), 0
            while chunk := resp.read(1 << 16):
                out.write(chunk)
                done += len(chunk)
                print(f"\rDownloading {name}: {done / 1e6:.1f}" + (f"/{total / 1e6:.1f}" if total else "") + " MB", end="", flush=True)
        print()
        tmp.replace(path)
    except (OSError, urllib.error.URLError) as exc:
        tmp.unlink(missing_ok=True)
        sys.exit(f"\nCould not download {name} ({exc}).\nDownload it manually from\n  {url}\nand save it as\n  {path}")
    return str(path)


def landmarks_px(landmarks, w: int, h: int) -> np.ndarray:
    return np.array([[lm.x * w, lm.y * h] for lm in landmarks], dtype=np.float32)


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", default="0", help="camera index or video file (default: 0)")
    ap.add_argument("--config", default=str(ROOT / "config.json"))
    ap.add_argument("--no-mirror", action="store_true")
    ap.add_argument("--headless", action="store_true", help="no window (use with --record / --max-seconds)")
    ap.add_argument("--record", help="write the composited picture to this mp4 file")
    ap.add_argument("--max-seconds", type=float, help="stop after this many seconds of (video) time")
    ap.add_argument("--auto", type=float, metavar="SEC", help="start the next edit every SEC seconds while idle")
    ap.add_argument("--mute", action="store_true", help="no sound")
    ap.add_argument("--debug", action="store_true", help="show fired triggers on screen")
    ap.add_argument("--hand-conf", type=float, default=0.5)
    return ap.parse_args()


def open_source(source: str) -> tuple[cv2.VideoCapture, bool]:
    is_file = not source.isdigit()
    if is_file:
        cap = cv2.VideoCapture(source)
    elif sys.platform == "win32":
        cap = cv2.VideoCapture(int(source), cv2.CAP_DSHOW)   # the default backend starts slowly on Windows
    else:
        cap = cv2.VideoCapture(int(source))
    if not cap.isOpened():
        sys.exit(f"Cannot open video source {source!r}. Try another index with --source 1.")
    return cap, is_file


def main() -> None:
    if sys.stdout is None or sys.stderr is None:   # started with pythonw (desktop shortcut): keep a log instead
        sys.stdout = sys.stderr = open(ROOT / "boost.log", "w", encoding="utf-8", buffering=1)
    args = parse_args()
    if not Path(args.config).exists() or not (ROOT / "videos").exists():
        import make_demo_assets
        make_demo_assets.main()
    cfg = cfgmod.load(args.config)
    engine = triggers.TriggerEngine(cfg.all_triggers())
    audio = Audio(enabled=not args.mute)
    if audio.ok:
        for e in cfg.edits:                          # cut the sound out of every clip now, not while playing
            audio.clip_audio(e.file, e.start, e.end)
    player = EditPlayer(cfg, audio)

    cap, is_file = open_source(args.source)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    writer = None
    if args.record:
        writer = cv2.VideoWriter(args.record, cv2.VideoWriter_fourcc(*"mp4v"), fps if is_file else 30.0, OUT_SIZE)

    hand_opts = vision.HandLandmarkerOptions(
        base_options=mp_python.BaseOptions(model_asset_path=ensure_model("hand_landmarker.task")),
        running_mode=vision.RunningMode.VIDEO, num_hands=2,
        min_hand_detection_confidence=args.hand_conf, min_hand_presence_confidence=args.hand_conf,
        min_tracking_confidence=args.hand_conf)
    face_opts = vision.FaceLandmarkerOptions(
        base_options=mp_python.BaseOptions(model_asset_path=ensure_model("face_landmarker.task")),
        running_mode=vision.RunningMode.VIDEO, num_faces=1,
        output_facial_transformation_matrixes=True, output_face_blendshapes=True)

    box = None
    frame_idx, last_ts, failed = 0, -1, 0
    t0 = time.monotonic()
    next_auto, auto_i = (args.auto or 0.0), 0
    fired_log: list[tuple[float, str]] = []
    fullscreen = False
    if not args.headless:
        cv2.namedWindow(WINDOW, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(WINDOW, *OUT_SIZE)
        print("Running. q/Esc quit, 1-9 start edit N, space random edit, f fullscreen.")

    with vision.HandLandmarker.create_from_options(hand_opts) as hand_lm, \
            vision.FaceLandmarker.create_from_options(face_opts) as face_lm:
        while True:
            ok, raw = cap.read()
            if not ok:
                failed += 1
                if is_file or failed > 30:
                    break
                continue
            failed = 0
            now = frame_idx / fps if is_file else time.monotonic() - t0
            if args.max_seconds and now > args.max_seconds:
                break
            if not args.no_mirror:
                raw = cv2.flip(raw, 1)
            det = hud.fit_cover(raw, DET_SIZE)
            mp_img = mp.Image(image_format=mp.ImageFormat.SRGB, data=cv2.cvtColor(det, cv2.COLOR_BGR2RGB))
            ts = max(int(now * 1000), last_ts + 1)
            last_ts = ts
            frame_idx += 1

            hres, fres = hand_lm.detect_for_video(mp_img, ts), face_lm.detect_for_video(mp_img, ts)
            ctx = triggers.Ctx(hands=[landmarks_px(l, *DET_SIZE) for l in hres.hand_landmarks])
            if fres.face_landmarks:
                ctx.face = landmarks_px(fres.face_landmarks[0], *DET_SIZE)
                if fres.face_blendshapes:
                    ctx.blend = {c.category_name: c.score for c in fres.face_blendshapes[0]}
                if fres.facial_transformation_matrixes:
                    ctx.pose = triggers.head_pose(fres.facial_transformation_matrixes[0])

            for name in engine.update(now, ctx):
                fired_log.append((now, name))
                choices = cfg.edits_for(name)
                if choices:
                    player.start(random.choice(choices), now)
            if args.auto and not player.busy and now >= next_auto:
                if player.start(cfg.edits[auto_i % len(cfg.edits)], now):
                    auto_i += 1
                    next_auto = now + args.auto
            view = player.update(now)

            img = cv2.resize(det, OUT_SIZE)
            sx = OUT_SIZE[0] / DET_SIZE[0]
            if ctx.face is not None:
                tgt = np.array([*ctx.face.min(axis=0), *ctx.face.max(axis=0)]) * sx
                pad = (tgt[2] - tgt[0]) * 0.12
                tgt += np.array([-pad, -pad * 1.5, pad, pad * 0.6])
                box = tgt if box is None else 0.35 * tgt + 0.65 * box
                hud.draw_face_box(img, box)
            else:
                box = None
            hud.draw_base(img, now)
            rect = hud.panel_rect(view.edit.size if view.edit else "panel", *OUT_SIZE)
            if view.state == IDLE:
                hud.panel_idle(img, rect, now)
            elif view.state == PRE:
                hud.panel_pre(img, rect, view.progress, now)
            else:
                hud.panel_clip(img, rect, view.frame)
                if view.impacted:
                    hud.caption(img, rect, view.edit.caption, view.impact)
            if args.debug and fired_log:
                hud._text(img, f"trigger: {fired_log[-1][1]}", (20, OUT_SIZE[1] - 60), 0.55, hud.GREEN, 1, outline=hud.DARK)
            img = hud.apply_impact(img, view.impact)

            if writer:
                writer.write(img)
            if args.headless:
                continue
            cv2.imshow(WINDOW, img)
            key = cv2.waitKey(1) & 0xFF
            if key in (ord("q"), 27):
                break
            if key == ord(" "):
                player.start(random.choice(cfg.edits), now)
            elif ord("1") <= key <= ord("9") and key - ord("1") < len(cfg.edits):
                player.start(cfg.edits[key - ord("1")], now)
            elif key == ord("f"):
                fullscreen = not fullscreen
                cv2.setWindowProperty(WINDOW, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN if fullscreen else cv2.WINDOW_NORMAL)

    audio.stop_all()
    cap.release()
    if writer:
        writer.release()
    if args.headless:
        for t, name in fired_log:
            print(f"{t:6.2f}s  trigger {name}")
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
