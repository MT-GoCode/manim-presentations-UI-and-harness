"""The CLI chain a user runs: build, then shots, then export."""

import json
import re

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


def test_build_then_shots_then_export_plays_the_template_talk_offline_to_its_end(tmp_path):
    from playwright.sync_api import sync_playwright

    root = built(tmp_path)
    assert mpres("shots", str(root), "--out", str(tmp_path / "shots"), "--workers", str(TEST_WORKERS)).returncode == 0
    out = tmp_path / "hello.html"
    r = mpres("export", str(root), "--out", str(out), "--transcript", "full", "--workers", str(TEST_WORKERS))
    assert r.returncode == 0 and "export: height 270 · width 480 · crf 28" in r.stdout, r.stderr
    beats = json.loads((root / "build" / "index.json").read_text())["beats"]
    page_beats = json.loads(re.search(r'id="manifest">(.*?)</script>', out.read_text(), re.S)[1])["beats"]
    assert [b["slug"] for b in page_beats] == [b["slug"] for b in beats]
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="chrome")
        context = browser.new_context()
        requests: list[str] = []
        context.route("**/*", lambda rt: (requests.append(rt.request.url), rt.continue_()))
        page = context.new_page()
        errors: list[str] = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(out.as_uri())
        front = """() => { const s = document.getElementById('stage').getBoundingClientRect();
            const v = document.elementFromPoint(s.x + s.width / 2, s.y + s.height / 2);  // the video the viewer sees
            return v instanceof HTMLVideoElement && v.readyState >= 2 && v; }"""
        page.wait_for_function(front)
        for _ in beats:  # every Next raises a new, decodable video, until the last beat plays
            old = page.evaluate_handle(front)
            page.keyboard.press("ArrowDown")
            page.wait_for_function(f"(old) => {{ const v = ({front})(); return v && v !== old; }}", arg=old)
        page.wait_for_function(f"() => {{ const v = ({front})(); return v.ended || v.loop; }}")
        browser.close()
    assert errors == [] and all(u.startswith(("file:", "blob:")) for u in requests), (errors, requests)
