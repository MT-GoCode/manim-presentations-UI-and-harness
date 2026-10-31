import fcntl
import hashlib
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

TESTS = Path(__file__).parent
FIXTURES = TESTS / "fixtures"
REPO = TESTS.parent
LEVELS = ("unit", "build", "qt", "export", "e2e")
TALKS = {  # every talk a test may copy, by name
    "hello": REPO / "examples" / "hello.manim-presentation",
    "edge": FIXTURES / "edge.manim-presentation",
    "geometry": FIXTURES / "geometry.manim-presentation",
}
TEST_SIZE = '[render]\npixel_width = 480\npixel_height = 270\norigin = "test speed"\n'
TEST_WORKERS = 2  # the smallest width that exercises concurrency
TEST_WORKERS_WIDE = 4  # enough to interleave on mac-work-2 while staying under the runner's RAM (P5)
SUBPROCESS_TIMEOUT = 600  # s: a hung build fails its test instead of hanging the suite; ~50× the slowest build test

MiB = 2**20
# Measured process-tree peaks (cores, bytes) of each level's heaviest test (`/usr/bin/time -l`, mac-work-2): unit, the
# whole in-process unit run; qt, the whole Audience run in one process (1.77 CPU-s over 6.8 s, 299 MiB); e2e, one
# setup.sh run on a repo copy; export, the frames fixture built and exported, then headless Chrome through two player
# tests (peak of the process tree's summed RSS, CPU seconds over wall time; psutil every 50 ms). Every xdist slot is sized for the heaviest, so
# slots never oversubscribe (a stated trade: a light test holds a heavy slot).
TEST_COST = {
    "unit": (0.5, 213 * MiB),
    "qt": (0.26, 299 * MiB),
    "e2e": (1.05, 245 * MiB),
    "export": (0.54, 1345 * MiB),
}
BUILD_PARENT_RSS = 191 * MiB  # the build parent's peak RSS (mac-work-2, `/usr/bin/time -l`)
PASS1_RSS_TEST = 138 * MiB  # the edge fixture's largest pass1_rss at 480×270 (index.json, mac-personal)


def build_cost() -> tuple[float, int]:
    """PLAN §3.11: the parent plus TEST_WORKERS_WIDE render workers, each its chapter's pass-1 peak plus the worker
    overhead at the test size (the render phase outweighs pass 1's TEST_WORKERS_WIDE children). 5.2 cores, 1073 MiB;
    the sampled tree peak of an edge build at --workers 4 was 4.37 cores, 803 MiB (mac-personal). Two tests build
    with no --workers, to test the default width: they may exceed their slot, but that width is sized from the idle
    cores and free RAM sampled at their start, so they shrink to the load the other slots put on the machine."""
    from manim_presentations import build

    worker_ram = PASS1_RSS_TEST + build.worker_overhead(480 * 270 / 1e6)
    return TEST_WORKERS_WIDE * build.WORKER_CORES, BUILD_PARENT_RSS + TEST_WORKERS_WIDE * worker_ram


def pytest_xdist_auto_num_workers(config: pytest.Config) -> int:
    """`-n auto`: the same 75%-of-free-headroom rule as the build, from the heaviest level's measured cost."""
    from manim_presentations import headroom

    costs = [*TEST_COST.values(), build_cost()]
    cores = max(c for c, _ in costs)
    ram = max(r for _, r in costs)
    jobs = os.cpu_count()
    assert jobs is not None
    match headroom.width(headroom.sample(headroom.MIN_SAMPLE_WINDOW), cores, ram, jobs):
        case headroom.Width(n):
            return n
        case headroom.RamExceeded(per_job, available):
            raise pytest.UsageError(
                f"one test needs {per_job / 2**30:.1f} GB, more than 75% of the "
                f"{available / 2**30:.1f} GB free; pass -n 1 to run anyway"
            )


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """A test's level is the folder it lives in, so every test carries exactly one marker."""
    for item in items:
        level = Path(item.fspath).relative_to(TESTS).parts[0]
        assert level in LEVELS, f"{item.nodeid}: tests live under tests/<{'|'.join(LEVELS)}>/"
        item.add_marker(getattr(pytest.mark, level))


def mpres(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    """The engine of the clone under test (this venv's interpreter), never `mpres` from PATH, which points at
    whichever clone setup last linked."""
    return subprocess.run(
        [sys.executable, "-P", "-m", "manim_presentations.cli", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=SUBPROCESS_TIMEOUT,
    )


def render_peak(r: subprocess.CompletedProcess[str]) -> int:
    """Peak alive in a build's render phase alone (pass 1's line reports its own)."""
    m = re.search(r"^render: \d+ beats .* · peak alive (\d+) ", r.stdout, re.M)
    assert m, r.stdout
    return int(m[1])


def copy_talk(tmp_path: Path, name: str, overlay: str | None = None) -> Path:
    """A talk copied into tmp_path, plus at most one overlay (its chapters and the script.md lines it adds).
    examples/hello copies get the test render size, since the template itself ships with the defaults."""
    root = tmp_path / f"{name}.manim-presentation"
    shutil.copytree(TALKS[name], root, ignore=shutil.ignore_patterns("build", "__pycache__"))
    if not (root / "talk.toml").exists():
        (root / "talk.toml").write_text(TEST_SIZE)
    if overlay:
        o = FIXTURES / "overlays" / overlay
        shutil.copytree(o / "chapters", root / "chapters", dirs_exist_ok=True)
        with (root / "script.md").open("a") as f:
            f.write((o / "script.append").read_text())
    return root


def tree_digest(root: Path) -> str:
    h = hashlib.sha256()
    for p in sorted(root.rglob("*")):
        if p.is_file() and p.name != ".complete":
            h.update(str(p.relative_to(root)).encode() + p.read_bytes())
    return h.hexdigest()


@pytest.fixture(scope="session")
def warm_cache(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """One warm TeX/text cache per session (xdist's documented recipe: one writer under a lock, the others read)."""
    # One per session: under xdist every worker's basetemp sits in the session's directory; without it, basetemp is.
    base = tmp_path_factory.getbasetemp()
    shared = base.parent if os.environ.get("PYTEST_XDIST_WORKER") else base
    done = shared / "warm-cache"
    with (shared / "warm-cache.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if not (done / ".complete").exists():
            shutil.rmtree(shared / "warm-src", ignore_errors=True)
            root = copy_talk(shared / "warm-src", "edge", "twins")
            r = mpres("build", str(root), "--workers", str(TEST_WORKERS_WIDE))
            assert r.returncode == 0, r.stdout + r.stderr
            shutil.copytree(root / "build" / ".cache", done, dirs_exist_ok=True)
            (done / ".complete").write_text(tree_digest(done))
    return done


@pytest.fixture
def talk(tmp_path: Path, warm_cache: Path):
    """Factory: talk(name, overlay=None, cold=False) → a copy whose build/.cache is seeded from (a real copy of) the
    warm cache. On teardown, the warm cache must be exactly as it was: no test's build may write to it."""

    def make(name: str, overlay: str | None = None, cold: bool = False) -> Path:
        root = copy_talk(tmp_path, name, overlay)
        if not cold:
            shutil.copytree(warm_cache, root / "build" / ".cache", ignore=shutil.ignore_patterns(".complete"))
        return root

    yield make
    assert tree_digest(warm_cache) == (warm_cache / ".complete").read_text(), "a test's build wrote the warm cache"
