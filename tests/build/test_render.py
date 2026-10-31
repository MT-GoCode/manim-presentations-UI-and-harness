"""Verified render, reuse and commit, through real `mpres build` subprocesses on fixture copies."""

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import av
import numpy as np
from conftest import REPO, SUBPROCESS_TIMEOUT, TEST_WORKERS, TEST_WORKERS_WIDE, render_peak

from manim_presentations.script import load


def build(root, workers=TEST_WORKERS, env=None, cwd=None):
    cmd = [sys.executable, "-P", "-m", "manim_presentations.cli", "build", str(root), "--workers", str(workers)]
    return subprocess.run(cmd, capture_output=True, text=True, env=env, cwd=cwd, timeout=SUBPROCESS_TIMEOUT)


def ok(r):
    assert r.returncode == 0, r.stdout + r.stderr
    return r


def rendered(r) -> list[str]:
    """The slugs the build's per-beat table marks as rendered (this run), in talk order."""
    return [m[1] for m in re.finditer(r"^\s*\d+\s+(\S+)\s.*\srendered\s", r.stdout, re.M)]


def index(root: Path) -> dict:
    return json.loads((root / "build" / "index.json").read_text())


def clips(root: Path) -> dict[str, bytes]:
    return {b["slug"]: (root / "build" / "clips" / f"{b['clip']}.mp4").read_bytes() for b in index(root)["beats"]}


def edit(path: Path, old: str, new: str) -> None:
    text = path.read_text()
    assert old in text, f"{old!r} not in {path}"
    path.write_text(text.replace(old, new))


def test_a_full_build_commits_every_beat_and_a_rebuild_renders_nothing(talk):
    root = talk("edge")
    r = ok(build(root))
    assert len(rendered(r)) == len(index(root)["beats"]) == sum(len(c.beats) for c in load(root / "script.md").chapters)
    assert "digests verified" in r.stdout
    r2 = ok(build(root))  # pass 1 runs again in fresh processes: the set-ordered helper draws in the same order
    assert rendered(r2) == [] and "render: 0 beats" in r2.stdout


def test_a_narration_edit_renders_nothing(prebuilt):
    root = prebuilt("edge")
    edit(root / "script.md", "## spin\n", "## spin\n\nWatch it turn.\n\n> slow down here\n")
    assert rendered(ok(build(root))) == []


def test_editing_one_beat_renders_exactly_that_beat(prebuilt):
    root = prebuilt("edge")
    edit(root / "chapters" / "closures.py", 'total["ticks"] * 0.001', 'total["ticks"] * 0.002')
    assert rendered(ok(build(root))) == ["after-again"]


def test_editing_a_helper_renders_only_the_beats_whose_frames_changed(prebuilt):
    root = prebuilt("edge")
    edit(root / "helpers" / "order.py", "buff=0.3", "buff=0.4")
    assert rendered(ok(build(root))) == ["ordered"]


def test_a_late_beat_edit_fast_forwards_exactly_through_accumulated_state(prebuilt):
    """The chunk for `after-accumulate` starts mid-chapter, after an UpdateFromFunc closure and a non-time updater
    have accumulated state; its frames verify against pass 1 only if fast-forward replayed every frame's update."""
    root = prebuilt("edge")
    edit(root / "chapters" / "closures.py", "dot.animate.shift(UP * total", "dot.animate.shift(UP * 1.1 * total")
    r = ok(build(root))
    assert rendered(r) == ["after-accumulate", "after-again"]  # the dot moved, so the next beat's frames did too
    assert "digests verified" in r.stdout


def test_workers_1_and_wide_give_byte_identical_clips(talk, tmp_path):
    one, wide = talk("edge"), tmp_path / "wide" / "edge.manim-presentation"
    shutil.copytree(one, wide)
    ok(build(one, 1))
    r = ok(build(wide, TEST_WORKERS_WIDE))
    assert render_peak(r) == TEST_WORKERS_WIDE  # real concurrency, not just the flag
    assert clips(one) == clips(wide)
    for root in (one, wide):  # and an edit spanning four chapters, rendered concurrently again
        edit(root / "chapters" / "marks.py", "Square(1.5)", "Square(1.6)")
        edit(root / "chapters" / "text.py", 'Text("Edge"', 'Text("Edges"')
        edit(root / "chapters" / "motion.py", "rotate(0.3)", "rotate(0.4)")
        edit(root / "chapters" / "closures.py", "run_time=1)", "run_time=1.2)")
    ok(build(one, 1))
    r = ok(build(wide, TEST_WORKERS_WIDE))
    assert render_peak(r) == TEST_WORKERS_WIDE
    assert clips(one) == clips(wide)


def frames(path: Path) -> list[np.ndarray]:
    with av.open(str(path)) as f:
        return [fr.to_ndarray(format="rgb24") for fr in f.decode(video=0)]


PLAIN = """
import sys
from pathlib import Path
from manim import config
from manim_presentations import clip
from manim_presentations.settings import Settings, load
from manim_presentations.talk import Talk

class Plain(clip.RecordContext):  # records nothing, patches nothing: plain Manim drawing
    def __init__(self, scene): pass
    def play_digest(self): return ("", 0)

root, out = Path(sys.argv[1]), Path(sys.argv[2])
clip.render_config(load(root))
config.media_dir = str(out)
scene = Talk(root / "chapters" / "paths.py", root, "t", Plain)
scene.render()
print("\\n".join(p for p in scene.renderer.file_writer.partial_movie_files if p))
"""


def test_tee_renders_the_same_pixels_as_plain_manim(talk, tmp_path):
    """Images, point clouds and background images bypass Cairo; the tee must forward every recorded call."""
    root = talk("edge")
    ok(build(root))
    script = tmp_path / "plain.py"
    script.write_text(PLAIN)
    r = subprocess.run(
        [sys.executable, "-P", str(script), str(root), str(tmp_path / "plain")],
        env={**os.environ, "PYTHONHASHSEED": "0"},
        capture_output=True,
        text=True,
        cwd=root,
        timeout=SUBPROCESS_TIMEOUT,
    )
    assert r.returncode == 0, r.stderr
    plain = [f for p in r.stdout.split() for f in frames(Path(p))]
    beats = [b for b in index(root)["beats"] if b["chapter"] == "paths"]
    built = [f for b in beats for f in frames(root / "build" / "clips" / f"{b['clip']}.mp4")]
    assert len(plain) == len(built)
    assert all(np.array_equal(a, b) for a, b in zip(plain, built, strict=True))


def test_a_clock_read_fails_tee_verification_naming_its_line(talk):
    r = build(talk("edge", "clock"))
    assert r.returncode == 1
    assert re.search(
        r"chapters/clock\.py:\d+ beat ticks: animation 0 drew different frames in its worker than in "
        r"pass 1: the chapter is nondeterministic",
        r.stderr,
    ), r.stderr


def test_a_hostile_cwd_and_user_config_change_nothing(prebuilt, tmp_path):
    root = prebuilt("edge")
    reference = clips(root)
    shutil.rmtree(root / "build" / "clips")
    (root / "build" / "index.json").unlink()
    cwd = tmp_path / "cwd"
    (cwd / "helpers").mkdir(parents=True)
    (cwd / "manim.cfg").write_text("[CLI]\nframe_rate = 7\n")
    (cwd / "numpy.py").write_text("raise ImportError('the cwd shadowed numpy')\n")
    (cwd / "helpers" / "__init__.py").write_text("raise ImportError('the cwd shadowed helpers')\n")
    home = tmp_path / "home"
    (home / ".config" / "manim").mkdir(parents=True)
    (home / ".config" / "manim" / "manim.cfg").write_text("[CLI]\nframe_rate = 7\npixel_width = 100\n")
    ok(build(root, env={**os.environ, "HOME": str(home)}, cwd=cwd))
    assert clips(root) == reference


def test_a_schema_mismatch_rebuilds_everything_and_leaves_no_old_clips(prebuilt):
    root = prebuilt("edge")
    old = set(os.listdir(root / "build" / "clips"))
    raw = index(root)
    raw["schema"] = 0
    (root / "build" / "index.json").write_text(json.dumps(raw))
    edit(root / "chapters" / "text.py", 'Text("Edge"', 'Text("Edged"')
    r = ok(build(root))
    assert "previous build: none (schema 0≠1)" in r.stdout
    assert len(rendered(r)) == len(index(root)["beats"])
    new = {b["clip"] for b in index(root)["beats"]}
    assert {f.split(".")[0] for f in os.listdir(root / "build" / "clips")} == new  # nothing of the old build left
    assert old - set(os.listdir(root / "build" / "clips"))  # the edited beat's old clip went


def test_a_build_waits_for_a_reader_before_it_commits(prebuilt):
    import fcntl

    root = prebuilt("edge")
    before = index(root)
    edit(root / "chapters" / "text.py", 'Text("Edge"', 'Text("Edges"')
    fd = os.open(root / "build" / ".clips.lock", os.O_RDWR | os.O_CREAT)
    fcntl.flock(fd, fcntl.LOCK_SH)  # what shots/export hold while they read clips
    cmd = [sys.executable, "-P", "-m", "manim_presentations.cli", "build", str(root), "--workers", str(TEST_WORKERS)]
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    assert p.stdout is not None
    seen = []
    for line in p.stdout:  # the build's own phase line, not a sleep
        seen.append(line)
        if line.startswith("commit: waiting for shots/export"):
            break
    try:  # nothing of the new build is committed, and nothing of the old one is collected, while a reader holds on
        assert index(root) == before
        assert all((root / "build" / "clips" / f"{b['clip']}.mp4").exists() for b in before["beats"])
    finally:
        os.close(fd)
    out = p.communicate(timeout=SUBPROCESS_TIMEOUT)[0]
    assert p.returncode == 0, "".join(seen) + out
    assert index(root)["build_id"] != before["build_id"]


def test_workers_peak_rss_stays_under_the_estimate(talk):
    r = ok(build(talk("edge"), TEST_WORKERS_WIDE))
    m = re.search(r"([\d.]+) GB/worker est, ([\d.]+) GB peak", r.stdout)
    assert m and float(m[2]) <= float(m[1]), r.stdout


def test_default_width_reads_idle_cores_and_available_ram(talk):
    import psutil

    busy = [subprocess.Popen([sys.executable, "-c", "while True: pass"]) for _ in range(2)]
    try:
        r = ok(
            subprocess.run(
                [sys.executable, "-P", "-m", "manim_presentations.cli", "build", str(talk("edge"))],
                capture_output=True,
                text=True,
                timeout=SUBPROCESS_TIMEOUT,
            )
        )
    finally:
        for b in busy:
            b.kill()
    m = re.search(
        r"machine: phase=pass-1 idle_cores=(\S+) available_ram=(\d+) per_job_cores=(\S+) "
        r"per_job_ram=(\d+) jobs=(\d+)",
        r.stdout,
    )
    assert m, r.stdout
    idle, avail, c, ram, jobs = float(m[1]), int(m[2]), float(m[3]), int(m[4]), int(m[5])
    assert idle <= psutil.cpu_count() - 2 + 0.5  # two busy loops: a mutant reading cpu_count goes red
    assert avail < psutil.virtual_memory().total  # available, never total
    want = max(1, min(int(0.75 * idle / c), int(0.75 * avail / ram), jobs))
    assert f"pass-1 width: {want} (idle" in r.stdout


def test_engine_edits_outside_clip_py_render_nothing_and_clip_py_renders_everything(prebuilt, tmp_path):
    root = prebuilt("edge")
    pkg = tmp_path / "engine"
    shutil.copytree(
        REPO / "manim_presentations", pkg / "manim_presentations", ignore=shutil.ignore_patterns("__pycache__")
    )
    (pkg / ".tinytex").symlink_to(REPO / ".tinytex")
    env = {**os.environ, "PYTHONPATH": str(pkg)}
    for name in ("schedule.py", "headroom.py", "worker.py", "manim_hooks.py", "stills.py"):
        with (pkg / "manim_presentations" / name).open("a") as f:
            f.write("\n# an edit\n")
        r = ok(build(root, env=env))
        assert rendered(r) == [], name
    hashes = lambda: {p.name.split(".")[1] for p in (root / "build" / "clips").glob("*.png")}  # noqa: E731
    assert len(hashes()) == 2  # the stills.py edit made new stills from the existing clips; the old ones are the
    ok(build(root, env=env))  # previous index's, so they go one build later
    assert len(hashes()) == 1
    with (pkg / "manim_presentations" / "clip.py").open("a") as f:
        f.write("\n# an edit\n")
    assert len(rendered(ok(build(root, env=env)))) == len(index(root)["beats"])


def test_a_clip_whose_stream_does_not_match_the_declared_encoding_fails(talk, tmp_path):
    """An engine edit that changes the encoder output (here, a worker merging a pixel format into the config after
    render_config) yields clips whose stream no longer matches what clip.py declares."""
    root = talk("edge")
    pkg = tmp_path / "engine"
    shutil.copytree(
        REPO / "manim_presentations", pkg / "manim_presentations", ignore=shutil.ignore_patterns("__pycache__")
    )
    (pkg / ".tinytex").symlink_to(REPO / ".tinytex")
    edit(
        pkg / "manim_presentations" / "worker.py",
        "    config.update(merged)\n",
        '    config.update(merged)\n    config.pixel_format = "yuv444p"\n    clip._applied["pixel_format"] = "yuv444p"\n',
    )
    r = build(root, env={**os.environ, "PYTHONPATH": str(pkg)})
    assert r.returncode == 1 and "stream check failed: pix_fmt yuv444p ≠ yuv420p" in r.stderr, r.stdout + r.stderr


def test_a_cache_id_change_starts_a_new_cache(prebuilt, tmp_path):
    root = prebuilt("edge")
    before = {d.name for d in (root / "build" / ".cache").iterdir()}
    pkg = tmp_path / "engine"
    shutil.copytree(
        REPO / "manim_presentations", pkg / "manim_presentations", ignore=shutil.ignore_patterns("__pycache__")
    )
    (pkg / ".tinytex").symlink_to(REPO / ".tinytex")
    edit(pkg / "manim_presentations" / "build.py", "manimpango.__version__,", 'manimpango.__version__ + "x",')
    ok(build(root, env={**os.environ, "PYTHONPATH": str(pkg)}))
    after = {d.name for d in (root / "build" / ".cache").iterdir()}
    assert len(after) == 1 and after != before  # the new identity's cache, and the old one collected
