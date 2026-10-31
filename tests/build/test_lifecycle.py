"""The build's guards across processes and builds: pins, a killed render's leftovers, edits during a build, worker
hygiene, the width seeds, one beat cut into chunks, and what scene processes may import from."""

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from conftest import REPO, SUBPROCESS_TIMEOUT, TEST_WORKERS, TEST_WORKERS_WIDE

from manim_presentations.deck import Deck, Layout


def build(root, workers=TEST_WORKERS, env=None, cwd=None):
    cmd = [sys.executable, "-P", "-m", "manim_presentations.cli", "build", str(root)]
    cmd += ["--workers", str(workers)] if workers else []
    return subprocess.run(cmd, capture_output=True, text=True, env=env, cwd=cwd, timeout=SUBPROCESS_TIMEOUT)


def ok(r):
    assert r.returncode == 0, r.stdout + r.stderr
    return r


def rendered(r) -> list[str]:
    return [m[1] for m in re.finditer(r"^\s*\d+\s+(\S+)\s.*\srendered\s", r.stdout, re.M)]


def index(root: Path) -> dict:
    return json.loads((root / "build" / "index.json").read_text())


def clip_of(root: Path, slug: str) -> Path:
    sha = next(b["clip"] for b in index(root)["beats"] if b["slug"] == slug)
    return root / "build" / "clips" / f"{sha}.mp4"


def edit(path: Path, old: str, new: str) -> None:
    text = path.read_text()
    assert old in text
    path.write_text(text.replace(old, new))


def engine_copy(tmp_path: Path) -> Path:
    pkg = tmp_path / "engine"
    shutil.copytree(
        REPO / "manim_presentations", pkg / "manim_presentations", ignore=shutil.ignore_patterns("__pycache__")
    )
    (pkg / ".tinytex").symlink_to(REPO / ".tinytex")
    return pkg


def test_a_pinned_clip_survives_two_builds(talk):
    """A live Presenter (it holds the presenter lock) pins the clip it shows; two builds later it still exists."""
    root = talk("edge")
    ok(build(root))
    shown = clip_of(root, "words")
    layout = Layout(root)
    fd = layout.presenter_lock()
    try:
        layout.write_pins({shown.stem})
        for old, new in (("Edge", "Edgy"), ("Edgy", "Edges")):  # two builds that each replace the shown clip
            edit(root / "chapters" / "text.py", f'Text("{old}"', f'Text("{new}"')
            ok(build(root))
        assert shown.exists()
    finally:
        os.close(fd)
    ok(build(root))
    assert not shown.exists()  # unpinned and two indexes old: collected


def test_a_presenter_that_has_not_pinned_yet_does_not_break_a_commit(talk):
    root = talk("edge")
    fd = Layout(root).presenter_lock()  # lock taken, no .presenter.json yet: the Presenter's startup window
    try:
        ok(build(root))
    finally:
        os.close(fd)


def test_a_killed_renders_leftovers_are_wiped(talk):
    root = talk("edge")
    stale = root / "build" / ".media" / "chunk-0" / "media" / "videos"
    stale.mkdir(parents=True)
    (stale / "uncached_00000.mp4").write_bytes(b"a killed render's partial file")
    ok(build(root))


def test_an_edit_during_a_build_does_not_reach_its_clips(talk, tmp_path):
    root = talk("edge")
    reference = tmp_path / "ref" / "edge.manim-presentation"
    shutil.copytree(root, reference)
    ok(build(reference))
    cmd = [sys.executable, "-P", "-m", "manim_presentations.cli", "build", str(root), "--workers", str(TEST_WORKERS)]
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    assert p.stdout is not None
    for line in p.stdout:  # the build's own phase line: the snapshot is taken
        if line.startswith("snapshot:"):
            edit(root / "chapters" / "text.py", 'Text("Edge"', 'Text("Edited"')
            break
    out = p.communicate(timeout=SUBPROCESS_TIMEOUT)[0]
    assert p.returncode == 0, out
    assert clip_of(root, "words").read_bytes() == clip_of(reference, "words").read_bytes()
    assert Deck.open(root).stale == ("chapters/text.py",)  # and the next look at the deck names the edit


def test_workers_write_no_bytecode(talk, tmp_path):
    root = talk("edge")
    pkg = engine_copy(tmp_path)
    edit(
        pkg / "manim_presentations" / "build.py",
        "    shutil.rmtree(layout.media, ignore_errors=True)\n    os.close(lock)",
        "    os.close(lock)",
    )  # keep this build's snapshot to inspect it
    ok(build(root, env={**os.environ, "PYTHONPATH": str(pkg)}))
    snapshot = root / "build" / ".media" / "src"
    assert (snapshot / "helpers").is_dir() and not list(snapshot.rglob("__pycache__"))


def test_a_worker_may_set_only_paths_and_the_play_range(talk, tmp_path):
    pkg = engine_copy(tmp_path)
    edit(
        pkg / "manim_presentations" / "worker.py",
        '"from_animation_number": int(first),',
        '"from_animation_number": int(first),\n        "frame_rate": 30,',
    )
    r = build(talk("edge"), env={**os.environ, "PYTHONPATH": str(pkg)})
    assert r.returncode == 1 and "a worker may only set paths and the play range" in r.stderr, r.stderr


def test_a_render_config_change_outside_clip_py_fails_the_worker(talk, tmp_path):
    pkg = engine_copy(tmp_path)
    edit(
        pkg / "manim_presentations" / "worker.py",
        "    scene.render()\n",
        "    config.frame_rate = 24\n    scene.render()\n",
    )
    r = build(talk("edge"), env={**os.environ, "PYTHONPATH": str(pkg)})
    assert r.returncode == 1 and "render config changed outside clip.py" in r.stderr, r.stderr


def test_pass1_width_comes_from_the_previous_builds_own_peaks(talk):
    root = talk("edge")
    ok(build(root))
    peaks = index(root)["chapters"]
    r = ok(build(root, workers=None))
    m = re.search(r"machine: phase=pass-1 \S+ \S+ per_job_cores=(\S+) per_job_ram=(\d+)", r.stdout)
    assert m, r.stdout
    assert int(m[2]) == max(c["pass1_rss"] for c in peaks.values())
    assert float(m[1]) == max(c["pass1_cores"] for c in peaks.values())


def test_one_long_beat_spreads_across_workers_byte_identically(talk, tmp_path):
    """A CHUNK_COST small enough to cut a twelve-play beat at 480×270 (the shipped 20 s would need ~14 min of video
    there): the beat runs as at least TEST_WORKERS_WIDE chunks at once, and its clip equals the one-worker clip."""
    pkg = engine_copy(tmp_path)
    edit(pkg / "manim_presentations" / "schedule.py", "CHUNK_COST = 20.0", "CHUNK_COST = 0.25")
    env = {**os.environ, "PYTHONPATH": str(pkg)}
    one = talk("edge", "long-beat")
    wide = tmp_path / "wide" / one.name
    shutil.copytree(one, wide)
    ok(build(one, 1, env=env))
    r = ok(build(wide, TEST_WORKERS_WIDE, env=env))
    assert f"peak alive {TEST_WORKERS_WIDE}" in r.stdout
    assert clip_of(one, "many").read_bytes() == clip_of(wide, "many").read_bytes()
    for root in (one, wide):  # and an edit to that one beat, alone
        edit(root / "chapters" / "long-beat.py", "rotate(0.2)", "rotate(0.25)")
    ok(build(one, 1, env=env))
    r = ok(build(wide, TEST_WORKERS_WIDE, env=env))
    assert rendered(r) == ["many"] and f"peak alive {TEST_WORKERS_WIDE}" in r.stdout
    assert clip_of(one, "many").read_bytes() == clip_of(wide, "many").read_bytes()


def test_scene_processes_never_import_from_the_cwd_or_the_live_talk(talk, tmp_path):
    root = talk("edge", "path-probe")
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    env = {**os.environ, "MPRES_TEST_FORBIDDEN": os.pathsep.join([str(cwd), str(root)])}
    ok(build(root, env=env, cwd=cwd))  # pass 1 and the worker both run the probe


def test_a_missing_clip_renders_exactly_its_beat_again(talk):
    root = talk("edge")
    ok(build(root))
    clip_of(root, "words").unlink()
    assert rendered(ok(build(root))) == ["words"]


def test_render_progress_streams_while_chunks_run(talk):
    r = ok(build(talk("edge"), TEST_WORKERS_WIDE))
    counts = [int(m[1]) for m in re.finditer(r"^render: (\d+)/\d+ animations", r.stdout, re.M)]
    assert counts and counts == sorted(counts) and counts[-1] > 0
