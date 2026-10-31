"""The CLI chain a user runs: build, then shots (the export step joins here from its sub-journey)."""

import json

import av
import numpy as np
from conftest import TEST_WORKERS, copy_talk, mpres
from PIL import Image


def built(tmp_path):
    root = copy_talk(tmp_path, "hello")
    r = mpres("build", str(root), "--workers", str(TEST_WORKERS))
    assert r.returncode == 0, r.stdout + r.stderr
    return root


def test_build_then_shots_writes_every_beat_and_chapter(tmp_path):
    root = built(tmp_path)
    out = tmp_path / "shots"
    r = mpres("shots", str(root), "--out", str(out), "--workers", str(TEST_WORKERS))
    assert r.returncode == 0, r.stderr
    beats = json.loads((root / "build" / "index.json").read_text())["beats"]
    want = {f"{n}-{b['slug']}-{w}.png" for n, b in enumerate(beats, 1) for w in ("first", "middle", "last")}
    want |= {"1-opening.png", "2-working.png", ".mpres-shots"}
    assert {p.name for p in out.iterdir()} == want
    assert f"shots: {len(want) - 1} images in {out}" in r.stdout


def test_the_middle_still_is_the_clips_middle_frame(tmp_path):
    root = built(tmp_path)
    out = tmp_path / "shots"
    assert mpres("shots", str(root), "--out", str(out), "--workers", str(TEST_WORKERS)).returncode == 0
    beat = json.loads((root / "build" / "index.json").read_text())["beats"][1]
    clip = root / "build" / "clips" / f"{beat['clip']}.mp4"
    with av.open(str(clip)) as f:
        middle = [fr.to_ndarray(format="rgb24") for fr in f.decode(video=0)][beat["frames"] // 2]
    assert np.array_equal(np.asarray(Image.open(out / f"2-{beat['slug']}-middle.png").convert("RGB")), middle)


def test_shots_reuses_its_own_folder_and_refuses_anyone_elses(tmp_path):
    root = built(tmp_path)
    out = tmp_path / "shots"
    for _ in range(2):  # its own folder (marker present): emptied and rewritten
        assert mpres("shots", str(root), "--out", str(out), "--workers", str(TEST_WORKERS)).returncode == 0
    other = tmp_path / "mine"
    other.mkdir()
    (other / "keep.txt").write_text("not mpres's")
    r = mpres("shots", str(root), "--out", str(other))
    assert r.returncode == 1 and "was not made by mpres shots" in r.stderr
    assert (other / "keep.txt").exists()


def test_shots_refuses_a_stale_build(tmp_path):
    root = built(tmp_path)
    (root / "chapters" / "opening.py").write_text((root / "chapters" / "opening.py").read_text() + "\n")
    r = mpres("shots", str(root), "--out", str(tmp_path / "shots"))
    assert r.returncode == 1 and "chapters/opening.py" in r.stderr and "run: mpres build" in r.stderr
