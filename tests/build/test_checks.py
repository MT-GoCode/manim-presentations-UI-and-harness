"""Pass 1 and the checks, through real `mpres build` subprocesses on fixture copies."""

import fcntl
import os
import re
import signal
import subprocess
import sys
import time

import pytest
from conftest import SUBPROCESS_TIMEOUT, TEST_WORKERS, TEST_WORKERS_WIDE, mpres


def build(root, *extra):
    return mpres("build", str(root), "--workers", str(TEST_WORKERS), *extra)


def test_edge_and_hello_build_clean(talk):
    for name in ("edge", "hello"):
        r = build(talk(name))
        assert r.returncode == 0, r.stdout + r.stderr
        assert "checks passed" in r.stdout


@pytest.mark.parametrize(
    "overlay,expected",
    [
        (
            "overlap",
            r"error: crossing · chapters/overlap\.py:7 · Text at \(.+\) × Square at \(.+\) "
            r"\(chapters/overlap\.py:6\) · move Text by \(.+\)",
        ),
        (
            "off-frame",
            r"error: too-far · chapters/off-frame\.py:6 · Square at \(.+\) is off frame by \d+\.\d\d \(right\)",
        ),
        ("mismatch", r'error: script\.md:\d+ has "## named-as" but chapters/mismatch\.py has no talk\.beat/loop'),
        ("early-play", r"error: chapters/early-play\.py:5: play or wait before the chapter's first talk\.beat"),
        ("empty-beat", r'error: chapters/empty-beat\.py:5 beat "only-adds" has no animation'),
        ("unnamed", r"error: chapters/stray\.py is not named by any `# stray` in script\.md"),
        ("reads-outside", r"error: chapters/reads-outside\.py read /private/tmp/x, outside the talk folder"),
        # the talk's fourth chapter: a beat's index for transient marks is its index in its own chapter
        (
            "late-transient",
            r"error: second · chapters/late-transient\.py:8 · Dot at \(.+\) was made transient in this beat",
        ),
        ("repeat-beat", r'error: chapters/repeat-beat\.py:7: beat "again" was already started in this chapter'),
    ],
)
def test_each_authoring_error_is_named_at_its_line(talk, overlay, expected):
    r = build(talk("edge", overlay))
    assert r.returncode == 1, r.stdout + r.stderr
    assert re.search(expected, r.stderr), r.stderr
    assert "Traceback" not in r.stderr


def test_failure_counts_per_kind(talk):
    r = build(talk("edge", "overlap"))
    assert r.stderr.splitlines()[-1] == "checks failed: overlap 1"


def test_a_bad_slug_in_script_md_is_one_line_not_a_traceback(talk):
    root = talk("edge")
    (root / "script.md").write_text((root / "script.md").read_text() + "\n## Bad Slug\n")
    r = build(root)
    assert r.returncode == 1 and "Traceback" not in r.stderr
    assert re.search(r"error: script\.md:\d+ bad slug 'Bad Slug'", r.stderr), r.stderr


@pytest.mark.parametrize("overlay", ["imports", "twins"])
def test_legal_imports_and_identical_text_in_two_chapters_pass(talk, overlay):
    r = build(talk("edge", overlay, cold=True))
    assert r.returncode == 0, r.stdout + r.stderr


def test_two_consecutive_builds_pass_the_allow_list(talk):
    root = talk("edge")
    for _ in range(2):
        r = build(root)
        assert r.returncode == 0, r.stdout + r.stderr


def test_workers_1_runs_one_pass1_child_at_a_time(talk):
    r = mpres("build", str(talk("edge")), "--workers", "1")
    assert r.returncode == 0, r.stderr
    assert "peak alive 1" in r.stdout


@pytest.mark.parametrize("n", ["0", "-2"])
def test_workers_below_one_is_refused_at_the_boundary(talk, n):
    r = mpres("build", str(talk("edge")), "--workers", n)
    assert r.returncode == 2 and "at least 1" in r.stderr


def test_a_concurrent_build_exits_3(talk):
    root = talk("edge")
    fd = os.open(root / "build" / ".build.lock", os.O_RDWR | os.O_CREAT)
    fcntl.flock(fd, fcntl.LOCK_EX)
    try:
        r = build(root)
    finally:
        os.close(fd)
    assert r.returncode == 3
    assert "a build is running" in r.stderr


def test_the_build_lock_outlives_a_killed_parent_until_its_children_exit(talk):
    """SIGKILL to the build parent alone: its pass-1 children inherited the lock fd, so the lock stays held until they
    notice the dead parent and exit; then a build succeeds."""
    root = talk("edge", "slow")
    argv = [sys.executable, "-P", "-m", "manim_presentations.cli", "build", str(root), "--workers"]
    parent = subprocess.Popen([*argv, str(TEST_WORKERS_WIDE)], stdout=subprocess.PIPE, text=True)
    assert parent.stdout is not None
    for line in parent.stdout:  # the build's own phase line: pass 1 is spawned right after it
        if line.startswith("pass-1 width"):
            break
    time.sleep(1)  # the slow chapter sleeps 6 s; its children are alive by now
    parent.send_signal(signal.SIGKILL)
    parent.wait()
    fd = os.open(root / "build" / ".build.lock", os.O_RDWR)
    try:  # probed in microseconds, well inside the children's 1 s parent-death poll
        with pytest.raises(BlockingIOError):
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    finally:
        os.close(fd)
    deadline = time.monotonic() + SUBPROCESS_TIMEOUT
    while (r := build(root)).returncode == 3 and time.monotonic() < deadline:
        time.sleep(0.5)
    assert r.returncode == 0, r.stdout + r.stderr
