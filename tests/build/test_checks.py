"""Pass 1 and the checks, through real `mpres build` subprocesses on fixture copies."""

import re

import pytest
from conftest import mpres

W = "2"  # TEST_WORKERS: the smallest width that exercises concurrency


def build(root, *extra):
    return mpres("build", str(root), "--workers", W, *extra)


def test_edge_and_hello_build_clean(talk):
    for fixture in ("edge", "hello"):
        r = build(talk(fixture))
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
        ("reads-outside", r"error: chapters/reads-outside\.py read /private/etc/hosts, outside the talk folder"),
    ],
)
def test_each_authoring_error_is_named_at_its_line(talk, overlay, expected):
    r = build(talk("edge", overlay))
    assert r.returncode == 1, r.stdout + r.stderr
    assert re.search(expected, r.stderr), r.stderr


def test_failure_counts_per_kind(talk):
    r = build(talk("edge", "overlap"))
    assert "checks failed: overlap 1" in r.stderr


@pytest.mark.parametrize("overlay", ["imports", "twins"])
def test_legal_imports_and_identical_text_in_two_chapters_pass(talk, overlay):
    """twins: two chapters create the same Text and MathTex on a cold cache, so a shared cache would collide on
    Manim's fixed-name temp SVG every run."""
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


def test_a_concurrent_build_exits_3(talk):
    import fcntl
    import os

    root = talk("edge")
    (root / "build").mkdir(exist_ok=True)
    fd = os.open(root / "build" / ".build.lock", os.O_RDWR | os.O_CREAT)
    fcntl.flock(fd, fcntl.LOCK_EX)
    try:
        r = build(root)
    finally:
        os.close(fd)
    assert r.returncode == 3
    assert "a build is running" in r.stderr
