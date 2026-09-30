"""Self-made edits: the rolling recorder, the templates, captions and the config fields (synthetic frames)."""
import json
import random
import sys
import tempfile
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import autoedit as A  # noqa: E402
import config as C  # noqa: E402


def _frame(v):
    return np.full((480, 640, 3), v % 256, np.uint8)


def _recorder(seconds=12.0, fps=30):
    rec = A.Recorder()
    for i in range(int(seconds * fps)):
        rec.add(i / fps, _frame(i), (320, 240))
    return rec


def test_recorder_rolls_and_samples():
    rec = A.Recorder(seconds=5.0)
    for i in range(30 * 12):
        rec.add(i / 30, _frame(i), (320, 240))
    assert 4.8 <= rec.span() <= 5.0                                 # only the last 5 s are kept
    ts = [s.t for s in rec.shots]
    assert all(b - a >= 1 / A.REC_FPS - 1e-5 for a, b in zip(ts, ts[1:]))   # thinned to REC_FPS
    s = rec.shots[-1]
    assert s.frame.shape == (A.REC_SIZE[1], A.REC_SIZE[0], 3) and s.face == (200.0, 150.0)   # face rescaled
    assert rec.segment(100, 101) and len(rec.segment(9, 10)) >= 14
    rec.mark(11.5, "smile")
    rec.mark(11.8, "fist")
    assert rec.take_event() == (11.8, "fist") and rec.take_event() == (11.5, "smile") and rec.take_event() is None
    moments = _recorder().random_moments(3, 1.5, random.Random(1))
    assert len(moments) == 3 and all(abs(a - b) >= 1.5 for a in moments for b in moments if a != b)


def test_templates_render_through_the_whole_edit():
    rec = _recorder()
    for name in A.TEMPLATES:
        ed = A.build(name, rec, 9.0, 1.5, 4.0, "BAD MFS", random.Random(2))
        for t in np.linspace(0, 4.0, 17):
            img = ed.render(float(t))
            assert img.shape == (A.REC_SIZE[1], A.REC_SIZE[0], 3) and img.dtype == np.uint8, name


def test_template_behaviour():
    rec = _recorder()
    # replay plays the recorded moment slowed down, then freezes
    ed = A.build("replay", rec, 9.0, 2.0, 3.5, "", random.Random(0))
    assert ed.render(0.0).mean() != ed.render(1.9).mean()
    assert (ed.render(2.6) == ed.render(3.4)).all()                 # frozen once the zoom settles (0.3 s)
    # wasted ends dark
    ed = A.build("freeze_wasted", rec, 9.0, 1.4, 5.0, "WASTED")
    assert ed.render(4.99).mean() < 0.3 * ed.render(1.5).mean()
    # montage uses three different moments when the buffer is long enough
    ed = A.build("montage", rec, 9.0, 1.6, 4.5, "BAD MFS", random.Random(3))
    assert len(ed.clips) == 3
    # rewind plays backwards
    ed = A.build("rewind", rec, 9.0, 2.0, 3.5, "x")
    assert ed.clips[0].at(ed.clips[0].length).t > ed.clips[0].at(0).t
    # a nearly empty recorder still renders
    tiny = A.Recorder()
    tiny.add(0.0, _frame(1))
    for name in A.TEMPLATES:
        A.build(name, tiny, 0.0, 1.0, 2.0, "x").render(1.5)


def test_word_by_word_and_text():
    assert A.word_at("BAD MFS", 0.9, 1.0) == ""
    assert A.word_at("BAD MFS", 1.1, 1.0) == "BAD" and A.word_at("BAD MFS", 1.5, 1.0) == "MFS"
    assert A.word_at("BAD MFS", 9.0, 1.0) == "MFS"
    img = np.zeros((300, 400, 3), np.uint8)
    assert (A.draw_title(img, "ПРИВЕТ", 0.5, 0.2) != 0).any()      # Cyrillic works
    assert (A.draw_label(img, "off glasses")[:10] == 245).all()
    long = A.draw_title(img, "a very very very very long caption", 0.5, 0.3)
    assert long.shape == img.shape


def test_config_auto_fields():
    with tempfile.TemporaryDirectory() as tmp:
        raw = {"edits": [{"effect": "replay", "trigger": ["auto", "smile"]}, {"effect": "zoom", "trigger": "fist"}],
               "auto_every": [5, 9], "captions": {"smile": "cute", "generic": ["a", "b"]}}
        Path(tmp, "c.json").write_text(json.dumps(raw))
        cfg = C.load(Path(tmp, "c.json"))
        assert cfg.auto_every == (5.0, 9.0) and [e.effect for e in cfg.auto_edits()] == ["replay"]
        assert cfg.caption_for("smile") == "cute" and cfg.caption_for("fist", random.Random(0)) in ("a", "b")
        assert cfg.caption_for(None, random.Random(0)) in ("a", "b")
        Path(tmp, "b.json").write_text(json.dumps({**raw, "auto_every": [9, 5]}))
        try:
            C.load(Path(tmp, "b.json"))
        except ValueError:
            pass
        else:
            raise AssertionError("auto_every min > max accepted")
    default = C.load(Path(__file__).resolve().parents[1] / "config.json")
    assert default.auto_edits() and "generic" in default.captions


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
