"""Pass 1 and the checks, through real `mpres build` subprocesses on fixture copies."""

import contextlib
import fcntl
import os
import re
import signal
import subprocess
import sys
import time

import psutil
import pytest
from conftest import TEST_WORKERS, TEST_WORKERS_WIDE, mpres


def build(root, *extra):
    return mpres("build", str(root), "--workers", str(TEST_WORKERS), *extra)


def test_edge_and_hello_build_clean(talk):
    for name in ("edge", "hello"):
        r = build(talk(name))
        assert r.returncode == 0, r.stdout + r.stderr
        assert r.stdout.splitlines()[-1].startswith("built ")


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
        ("read-tempdir", r"error: chapters/read-tempdir\.py read /private/var/folders/\S+/mpres-scratch, outside"),
        ("read-engine", r"error: chapters/read-engine\.py read \S+/pyproject\.toml, outside the talk folder"),
        (
            "swapped",
            r'error: chapters/swapped\.py:5 order differs at beat 1 of "swapped": script\.md "## b", chapter "a"',
        ),
        ("no-construct", r"error: chapters/no-construct\.py defines no construct\(talk\)"),
        ("no-beat", r"error: chapters/no-beat\.py: no talk\.beat\(\) in the chapter"),
        (
            "unclosed",
            r'error: chapters/unclosed\.py:5 loop "drifts" does not close: its end state differs from its first frame in \d+ pixels',
        ),
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


@pytest.mark.parametrize("overlay", ["imports", "twins", "tempfile-ok"])
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
    notice the dead parent (their 1 s watch) and exit; the slow chapter sleeps far longer, so only the watch frees
    the lock in time."""
    root = talk("edge", "slow")
    argv = [sys.executable, "-P", "-m", "manim_presentations.cli", "build", str(root), "--workers"]
    parent = subprocess.Popen([*argv, str(TEST_WORKERS_WIDE)], stdout=subprocess.PIPE, text=True)
    assert parent.stdout is not None
    for line in parent.stdout:  # the build's own phase line: pass 1 is spawned right after it
        if line.startswith("pass-1 width"):
            break
    time.sleep(1)  # the children are alive by now
    parent.send_signal(signal.SIGKILL)
    parent.wait()
    fd = os.open(root / "build" / ".build.lock", os.O_RDWR)
    try:  # probed in microseconds, well inside the children's 1 s parent-death poll
        with pytest.raises(BlockingIOError):
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        deadline = time.monotonic() + WATCH_BOUND
        while time.monotonic() < deadline:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                time.sleep(0.1)
        else:
            pytest.fail(f"the orphans still hold the build lock {WATCH_BOUND} s after their parent died")
    finally:
        os.close(fd)


WATCH_BOUND = 5  # s: the children's 1 s parent-death poll, plus exit and margin; the slow chapter sleeps 600 s


def test_the_first_failure_kills_the_other_children(talk):
    root = talk("edge", "slow-and-early")
    r = mpres("build", str(root), "--workers", str(TEST_WORKERS_WIDE))
    assert r.returncode == 1 and "play or wait before the chapter's first talk.beat" in r.stderr, r.stderr
    alive = []
    for p in psutil.process_iter():
        with contextlib.suppress(psutil.Error):  # processes we may not inspect, or that ended mid-scan
            if any(str(root) in arg for arg in p.cmdline()):
                alive.append(p)
    assert alive == [], alive


def test_new_cache_entries_are_merged_kept_and_reused(talk):
    root = talk("edge", cold=True)
    r = build(root)
    m = re.search(r"(\d+) new cache entries", r.stdout)
    assert r.returncode == 0 and m and int(m[1]) > 0, r.stdout + r.stderr
    caches = list((root / "build" / ".cache").iterdir())
    assert len(caches) == 1 and any((caches[0] / "text").iterdir())  # merged, and kept by the post-commit prune
    assert "0 new cache entries" in build(root).stdout  # the second build finds them warm
