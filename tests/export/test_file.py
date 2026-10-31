"""The exported file: its clips are the build's frames, re-encoded at the asked size; the flags' bounds; the routing
of refusals; and the export's place in the clip lock protocol."""

import json
import math
import os
import re
import shutil
import signal
import subprocess
import sys
from pathlib import Path

from conftest import SUBPROCESS_TIMEOUT, TEST_WORKERS, mpres
from frames import clips, decoded, manifest, run

import manim_presentations

pytest_plugins = ["frames_plugin"]  # the session's built frames talk and its per-test copies


def export(root: Path, out: Path, *flags: str) -> subprocess.CompletedProcess[str]:
    return mpres("export", str(root), "--out", str(out), *flags)


def index(root: Path) -> dict:
    return json.loads((root / "build" / "index.json").read_text())


def test_every_frame_of_every_beat_is_the_builds_frame_at_the_asked_size(frames_talk, tmp_path):
    for flags, (w, h) in (((), (480, 270)), (("--height", "180"), (320, 180))):
        out = tmp_path / f"{h}.html"
        r = export(frames_talk, out, *flags, "--workers", str(TEST_WORKERS))
        assert r.returncode == 0, r.stderr
        assert f"export: height {h} · width {w} · crf 28" in r.stdout
        html = out.read_text()
        beats = index(frames_talk)["beats"]
        assert [b["slug"] for b in manifest(html)["beats"]] == [b["slug"] for b in beats]
        for i, (clip, beat) in enumerate(zip(clips(html), beats, strict=True), 1):
            facts, codes = decoded(clip)
            assert facts == (w, h, 30)
            assert codes == [i << 8 | k for k in range(beat["frames"])], beat["slug"]


def test_height_defaults_to_the_source_and_refuses_above_it(frames_talk, tmp_path):
    r = export(frames_talk, tmp_path / "a.html", "--height", "272")
    assert r.returncode == 1 and "--height 272 is above the source height 270" in r.stderr
    assert not (tmp_path / "a.html").exists()
    assert export(frames_talk, tmp_path / "b.html", "--height", "270").returncode == 0


def test_odd_height_and_crf_outside_0_51_are_refused_at_the_command_line(frames_talk, tmp_path):
    for flags, message in (
        (("--height", "181"), "needs an even height"),
        (("--crf", "52"), "x264 takes 0-51"),
        (("--crf", "-1"), "x264 takes 0-51"),
    ):
        r = export(frames_talk, tmp_path / "x.html", *flags)
        assert r.returncode == 2 and message in r.stderr, flags
    assert export(frames_talk, tmp_path / "y.html", "--crf", "51", "--height", "2").returncode == 0


def test_a_higher_crf_makes_smaller_clips(frames_talk, tmp_path):
    sizes = []
    for crf in ("10", "40"):
        out = tmp_path / f"{crf}.html"
        assert export(frames_talk, out, "--crf", crf).returncode == 0
        sizes.append(sum(len(c) for c in clips(out.read_text())))
    assert sizes[1] < sizes[0]  # equal encodes are byte-identical, so an ignored --crf ties


def test_a_stale_or_unbuilt_talk_is_refused(frames_talk, tmp_path):
    chapter = frames_talk / "chapters" / "one.py"
    chapter.write_text(chapter.read_text() + "\n")
    r = export(frames_talk, tmp_path / "x.html")
    assert r.returncode == 1 and "chapters/one.py" in r.stderr and "run: mpres build" in r.stderr
    shutil.rmtree(frames_talk / "build")
    r = export(frames_talk, tmp_path / "x.html")
    assert r.returncode == 1 and "was never built" in r.stderr
    assert not (tmp_path / "x.html").exists()


def test_width_is_the_flag_or_75_percent_of_free_headroom(frames_talk, tmp_path):
    r = export(frames_talk, tmp_path / "a.html", "--workers", "3")
    assert r.returncode == 0 and "export width: 3 (--workers)" in r.stdout
    r = export(frames_talk, tmp_path / "b.html")
    assert r.returncode == 0, r.stderr
    m = re.search(
        r"machine: phase=export idle_cores=(\S+) available_ram=(\d+) per_job_cores=(\S+) per_job_ram=(\d+) jobs=(\d+)",
        r.stdout,
    )
    i, ram, c, m_ram, jobs = float(m[1]), int(m[2]), float(m[3]), int(m[4]), int(m[5])
    assert jobs == 4
    assert f"export width: {max(1, min(math.floor(0.75 * i / c), math.floor(0.75 * ram / m_ram), jobs))} (" in r.stdout


def engine_copy(tmp_path: Path, old: str, new: str) -> dict[str, str]:
    """The engine-edit pattern: a package copy with one edit, importable through PYTHONPATH."""
    pkg = tmp_path / "pkg"
    shutil.copytree(Path(manim_presentations.__file__).parent, pkg / "manim_presentations")
    f = pkg / "manim_presentations" / "export.py"
    text = f.read_text()
    assert text.count(old) == 1
    f.write_text(text.replace(old, new))
    return {**os.environ, "PYTHONPATH": str(pkg)}


def test_an_encode_job_too_big_for_free_ram_is_refused_unless_workers_is_given(frames_talk, tmp_path):
    env = engine_copy(tmp_path, "* out_mp) * MiB)", "* out_mp) * MiB * 10**6)")
    out = tmp_path / "x.html"
    r = run("export", str(frames_talk), "--out", str(out), env=env)
    assert r.returncode == 1 and "pass --workers 1 to run it anyway" in r.stderr, r.stdout + r.stderr
    assert not out.exists()
    r = run("export", str(frames_talk), "--out", str(out), "--workers", "1", env=env)
    assert r.returncode == 0 and out.exists(), r.stderr


def test_a_failed_encode_leaves_no_file_and_no_scratch(frames_talk, tmp_path):
    clip = frames_talk / "build" / "clips" / f"{index(frames_talk)['beats'][2]['clip']}.mp4"
    clip.write_bytes(clip.read_bytes()[:2000])
    out = tmp_path / "x.html"
    r = export(frames_talk, out)
    assert r.returncode != 0
    assert not out.exists() and not list(out.parent.glob(".*.tmp"))
    assert list((frames_talk / "build" / ".export").iterdir()) == []


def lines_until(proc: subprocess.Popen[str], text: str) -> bool:
    """Read the process's stdout until a line contains `text` (True) or the stream ends (False)."""
    assert proc.stdout is not None
    return any(text in line for line in proc.stdout)


def test_a_build_during_export_renders_waits_at_commit_then_commits(frames_talk, tmp_path):
    cli = [sys.executable, "-P", "-m", "manim_presentations.cli"]
    pipes = {"stdout": subprocess.PIPE, "stderr": subprocess.STDOUT, "text": True}
    exporting = subprocess.Popen(
        [*cli, "export", str(frames_talk), "--out", str(tmp_path / "x.html"), "--workers", "1"], **pipes
    )
    building = None
    try:
        assert lines_until(exporting, "export width:")  # printed inside the clips lock
        exporting.send_signal(signal.SIGSTOP)
        before = (frames_talk / "build" / "index.json").read_bytes()
        chapter = frames_talk / "chapters" / "one.py"
        chapter.write_text(chapter.read_text().replace("RIGHT * 2), run_time=1)", "RIGHT * 3), run_time=1)"))
        building = subprocess.Popen([*cli, "build", str(frames_talk), "--workers", str(TEST_WORKERS)], **pipes)
        assert lines_until(building, "commit: waiting for shots/export to finish")
        assert (frames_talk / "build" / "index.json").read_bytes() == before
        exporting.send_signal(signal.SIGCONT)
        assert exporting.wait(SUBPROCESS_TIMEOUT) == 0
        assert building.wait(SUBPROCESS_TIMEOUT) == 0
        assert index(frames_talk)["build_id"] != json.loads(before)["build_id"]
    finally:
        exporting.send_signal(signal.SIGCONT)
        for p in (exporting, building):
            if p is not None and p.poll() is None:
                p.kill()
