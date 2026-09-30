"""Logic tests: config, the edit player, triggers and hand shapes (synthetic data, no camera or models)."""
import json
import sys
import tempfile
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config as C  # noqa: E402
import effects as E  # noqa: E402
import make_demo_assets as demo  # noqa: E402
import player as P  # noqa: E402
import triggers as T  # noqa: E402


class FakeAudio:
    def __init__(self):
        self.played = []

    def play(self, path):
        self.played.append(Path(path).name if path else None)

    def clip_audio(self, *a):
        return Path("clip_audio.wav")


def test_parse_time():
    assert C.parse_time(2.5) == 2.5 and C.parse_time("2.5") == 2.5
    assert C.parse_time("00:22.000") == 22.0 and C.parse_time("01:02.5") == 62.5
    assert C.parse_time("1:00:00") == 3600.0


def _cfg(tmp: Path, **over) -> C.Config:
    edit = {"file": "a.mp4", "start": "00:00.500", "end": "00:02.000", "trigger_time": "00:01.000", "trigger": "fist"}
    raw = {"edits": [edit], "pre_edit_sound": "pre.wav", "post_edit_sound": "post.wav", "impact_sound": "hit.wav",
           "pre_edit_duration": 1.0, "cooldown": 3, **over}
    (tmp / "config.json").write_text(json.dumps(raw))
    return C.load(tmp / "config.json")


def test_config_load_and_validation():
    with tempfile.TemporaryDirectory() as tmp:
        cfg = _cfg(Path(tmp))
        e = cfg.edits[0]
        assert (e.start, e.end, e.trigger_time, e.triggers, e.size, e.cooldown) == (0.5, 2.0, 1.0, ["fist"], "panel", 3.0)
        assert e.file == Path(tmp).resolve() / "a.mp4" and cfg.edits_for("fist") == [e] and cfg.edits_for("smile") == []
        for bad in ({"edits": []}, {"edits": [{"file": "a", "start": 3, "end": 2}]},
                    {"edits": [{"file": "a", "start": 0, "end": 2, "trigger_time": 5}]},
                    {"edits": [{"file": "a", "size": "huge"}]}):
            Path(tmp, "bad.json").write_text(json.dumps(bad))
            try:
                C.load(Path(tmp, "bad.json"))
            except ValueError:
                continue
            raise AssertionError(f"accepted {bad}")


def test_player_timeline():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        demo.make_clip(tmp / "a.mp4", "T", 30, size=(160, 120), seconds=3.0, impact=1.0)
        cfg = _cfg(tmp)
        audio = FakeAudio()
        pl = P.EditPlayer(cfg, audio)
        e = cfg.edits[0]
        assert pl.update(0.0).state == P.IDLE
        assert pl.start(e, 10.0) and not pl.start(e, 10.1)                   # busy
        v = pl.update(10.5)
        assert v.state == P.PRE and abs(v.progress - 0.5) < 1e-6 and audio.played == ["pre.wav"]
        v = pl.update(11.0)                                                   # pre_edit_duration over -> clip plays
        assert v.state == P.PLAY and v.frame is not None and audio.played[-1] == "clip_audio.wav"
        v = pl.update(11.4)                                                   # clip time 0.9: before the impact
        assert v.impact == 0.0 and not v.impacted
        v = pl.update(11.55)                                                  # clip time 1.05: impact just hit
        assert v.impact > 0.8 and v.impacted and "hit.wav" in audio.played
        v = pl.update(11.55 + 0.6)                                            # impact faded out
        assert v.impact == 0.0
        v = pl.update(12.6)                                                   # clip time 2.1 > end 2.0
        assert v.state == P.POST and audio.played[-1] == "post.wav"
        assert pl.update(13.3).state == P.IDLE
        assert not pl.start(e, 14.0)                                          # cooldown 3 s after finishing (13.3)
        assert pl.start(e, 16.5)


def _hand(extended=(), thumb=False, direction=(0.0, -1.0)):
    bases = {"index": (85, 150), "middle": (100, 148), "ring": (115, 150), "pinky": (128, 155)}
    idx = {"index": (5, 8), "middle": (9, 12), "ring": (13, 16), "pinky": (17, 20)}
    d = np.array(direction, float)
    h = np.tile(np.array([100.0, 200.0]), (21, 1))
    for n, b in bases.items():
        h[idx[n][0]] = b
        h[idx[n][1]] = np.array(b) + (d * 70 if n in extended else -d * 15)
    h[4] = (40, 170) if thumb else (95, 160)
    return h


def test_hand_kinds():
    assert T.hand_kind(_hand({"index"})) == "point_up"
    assert T.hand_kind(_hand(set())) == "fist"
    assert T.hand_kind(_hand({"pinky"}, thumb=True)) == "shaka"
    assert T.hand_kind(_hand({"index", "middle"})) == "peace"
    assert T.hand_kind(_hand({"index", "middle", "ring", "pinky"}, thumb=True)) == "open"
    thumbs = _hand(set(), thumb=True)
    thumbs[4] = (60, 100)                       # thumb tip well above the index base
    assert T.hand_kind(thumbs) == "thumbs_up"


def test_conditions_and_engine():
    ctx_smile = T.Ctx(blend={"mouthSmileLeft": 0.7, "mouthSmileRight": 0.6})
    ctx_talk = T.Ctx(blend={"jawOpen": 0.14, "mouthSmileLeft": 0.14, "mouthSmileRight": 0.1})
    assert T.CONDITIONS["smile"](ctx_smile) and not T.CONDITIONS["smile"](ctx_talk)
    assert not T.CONDITIONS["mouth_open"](ctx_talk)
    assert T.CONDITIONS["look_away"](T.Ctx(pose=(40.0, 0.0))) and not T.CONDITIONS["look_away"](T.Ctx(pose=(5.0, 3.0)))
    assert T.CONDITIONS["face_lost"](T.Ctx()) and not T.CONDITIONS["face_lost"](T.Ctx(face=np.zeros((478, 2))))
    eng = T.TriggerEngine(["smile"])
    fired = [eng.update(t, ctx_smile) for t in (0.0, 0.1, 0.2, 0.3, 0.4)]
    assert fired == [[], [], [], ["smile"], []]                     # must hold 0.25 s, fires once
    assert eng.update(0.5, T.Ctx()) == [] and eng.update(1.0, T.Ctx()) == []       # re-armed after 0.4 s of nothing
    assert [eng.update(t, ctx_smile) for t in (1.1, 1.4)] == [[], ["smile"]]
    try:
        T.TriggerEngine(["dance"])
    except ValueError as exc:
        assert "dance" in str(exc)
    else:
        raise AssertionError("unknown trigger accepted")


def test_hands_on_head_and_mouth():
    face = np.zeros((478, 2), np.float32)
    face[234], face[454], face[10], face[152], face[13], face[14] = (50, 100), (150, 100), (100, 40), (100, 160), (100, 130), (100, 130)
    lo, hi = _hand(set()) + (-60, -170), _hand({"index", "middle", "ring", "pinky"}, thumb=True) + (60, -170)
    assert T.CONDITIONS["hands_head"](T.Ctx(hands=[lo, hi], face=face))
    assert not T.CONDITIONS["hands_head"](T.Ctx(hands=[lo], face=face))
    open_hand = _hand({"index", "middle", "ring", "pinky"}, thumb=True) + (0, -70)
    assert T.CONDITIONS["hand_mouth"](T.Ctx(hands=[open_hand], face=face))
    assert not T.CONDITIONS["hand_mouth"](T.Ctx(hands=[_hand(set()) + (0, -70)], face=face))   # a fist is not a mouth cover


def _cam(seed):
    rng = np.random.default_rng(seed)
    img = rng.integers(0, 255, (480, 640, 3), dtype=np.uint8)
    img[:, :, 2] = 230                        # a strongly red picture, so "grey" is measurable
    return img


def test_every_effect_renders():
    cam, first = _cam(1), _cam(2)
    for name in E.EFFECTS:
        for t in (0.0, 0.5, 1.2, 2.0, 2.9):
            out = E.render(name, cam, first, t, 1.2, 3.0, (320, 240), "")
            assert out.shape == cam.shape and out.dtype == np.uint8, name
        E.render(name, cam, first, 1.0, 1.2, 3.0, None, "X")        # no face known


def test_effect_details():
    cam, first = _cam(1), _cam(2)
    # wasted fades to grey before the impact
    before, done = E.render("wasted", cam, first, 0.1, 1.5, 3.5, None, ""), E.render("wasted", cam, first, 1.4, 1.5, 3.5, None, "")
    spread = lambda im: float(np.abs(im[:, :, 2].astype(int) - im[:, :, 0].astype(int)).mean())   # noqa: E731
    assert spread(done) < 0.2 * spread(before)
    # finished is a freeze frame: the live camera does not matter
    a = E.render("finished", cam, first, 0.5, 1.0, 3.0, None, "")
    b = E.render("finished", _cam(3), first, 0.5, 1.0, 3.0, None, "")
    assert (a == b).all()
    # captions only appear from the impact on, and the default caption is used when empty
    assert (E.render("zoom", cam, first, 0.9, 1.0, 3.0, None, "") != E.render("zoom", cam, first, 0.9, 1.0, 3.0, None, "A")).sum() == 0
    assert E.DEFAULT_CAPTION["wasted"] == "WASTED"


def test_effect_edits_in_config_and_player():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        raw = {"edits": [{"effect": "wasted", "trigger": "fist", "sound": "boom.wav"}], "impact_sound": "hit.wav"}
        (tmp / "c.json").write_text(json.dumps(raw))
        cfg = C.load(tmp / "c.json")
        e = cfg.edits[0]
        assert (e.file, e.effect, e.start, e.end, e.trigger_time, e.name) == (None, "wasted", 0.0, 3.0, 1.2, "wasted")
        assert e.sound == tmp.resolve() / "boom.wav"
        for bad in ({"effect": "nope"}, {"effect": "wasted", "file": "a.mp4"}, {"trigger": "fist"}):
            (tmp / "b.json").write_text(json.dumps({"edits": [bad]}))
            try:
                C.load(tmp / "b.json")
            except ValueError:
                continue
            raise AssertionError(f"accepted {bad}")
        audio = FakeAudio()
        pl = P.EditPlayer(cfg, audio)
        pl.start(e, 0.0)
        v = pl.update(1.0)                                            # pre over -> effect plays, its own sound
        assert v.state == P.PLAY and v.frame is None and v.t == 0.0 and audio.played[-1] == "boom.wav"
        first_id = v.play_id
        v = pl.update(2.3)
        assert abs(v.t - 1.3) < 1e-9 and v.impacted and "hit.wav" in audio.played
        assert pl.update(4.0).state == P.POST                        # 3.0 s effect is over
        assert pl.update(5.0).state == P.IDLE
        pl._cooldown_until = 0
        assert pl.start(e, 5.0)
        assert pl.update(6.0).play_id != first_id                    # a new playback gets a new id


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
