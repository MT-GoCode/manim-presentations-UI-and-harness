import fcntl
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

TESTS = Path(__file__).parent
FIXTURES = TESTS / "fixtures"
REPO = TESTS.parent
LEVELS = ("unit", "build", "qt", "export", "e2e")
TEST_SIZE = '[render]\npixel_width = 480\npixel_height = 270\norigin = "test speed"\n'


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
        [sys.executable, "-P", "-m", "manim_presentations.cli", *args], cwd=cwd, capture_output=True, text=True
    )


def copy_talk(tmp_path: Path, fixture: str, overlay: str | None = None) -> Path:
    """A fixture copied into tmp_path, plus at most one overlay (its chapters and the script.md lines it adds).
    examples/hello copies get the test render size, since the template itself ships with the defaults."""
    src = REPO / "examples" / f"{fixture}.manim-presentation"
    if not src.exists():
        src = FIXTURES / f"{fixture}.manim-presentation"
    root = tmp_path / f"{fixture}.manim-presentation"
    shutil.copytree(src, root, ignore=shutil.ignore_patterns("build", "__pycache__"))
    if not (root / "talk.toml").exists():
        (root / "talk.toml").write_text(TEST_SIZE)
    if overlay:
        o = FIXTURES / "overlays" / overlay
        shutil.copytree(o / "chapters", root / "chapters", dirs_exist_ok=True)
        with (root / "script.md").open("a") as f:
            f.write((o / "script.append").read_text())
    return root


@pytest.fixture(scope="session")
def warm_cache(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """One warm TeX/text cache per session (xdist's documented recipe: one writer under a lock, the others read)."""
    shared = tmp_path_factory.getbasetemp().parent
    done = shared / "warm-cache"
    with (shared / "warm-cache.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if not (done / ".complete").exists():
            root = copy_talk(shared / "warm-src", "edge", "twins") if not (shared / "warm-src").exists() else None
            root = root or shared / "warm-src" / "edge.manim-presentation"
            r = mpres("build", str(root), "--workers", "4")
            assert r.returncode == 0, r.stdout + r.stderr
            shutil.copytree(root / "build" / ".cache", done, dirs_exist_ok=True)
            (done / ".complete").touch()
    return done


@pytest.fixture
def talk(tmp_path: Path, warm_cache: Path):
    """Factory: talk(fixture, overlay=None) → a copy whose build/.cache is seeded from the warm cache."""

    def make(fixture: str, overlay: str | None = None, cold: bool = False) -> Path:
        root = copy_talk(tmp_path, fixture, overlay)
        if not cold:
            shutil.copytree(warm_cache, root / "build" / ".cache", ignore=shutil.ignore_patterns(".complete"))
        return root

    return make
