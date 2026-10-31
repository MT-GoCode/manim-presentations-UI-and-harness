"""Fixtures for the export tests (loaded through `pytest_plugins`, never imported): the frames talk built once per
session, and a private copy of it per test."""

import fcntl
import os
import shutil
from pathlib import Path

import pytest
from conftest import TEST_WORKERS, mpres
from frames import FRAMES, PAGE_JS, Player, manifest
from playwright.sync_api import sync_playwright


@pytest.fixture(scope="session")
def built(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """The frames talk built once per session (one writer under a lock, the others read); tests copy it."""
    base = tmp_path_factory.getbasetemp()
    shared = base.parent if os.environ.get("PYTEST_XDIST_WORKER") else base
    root = shared / "frames-built" / FRAMES.name
    with (shared / "frames-built.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if not (root.parent / ".complete").exists():
            shutil.rmtree(root.parent, ignore_errors=True)
            shutil.copytree(FRAMES, root, ignore=shutil.ignore_patterns("build", "__pycache__"))
            r = mpres("build", str(root), "--workers", str(TEST_WORKERS))
            assert r.returncode == 0, r.stdout + r.stderr
            (root.parent / ".complete").touch()
    return root


@pytest.fixture
def frames_talk(built: Path, tmp_path: Path) -> Path:
    """A private copy of the built frames talk, build/ included, for tests that change or lock it."""
    root = tmp_path / FRAMES.name
    shutil.copytree(built, root, symlinks=True)
    return root


@pytest.fixture(scope="session")
def exported(built: Path):
    """exported(transcript) → the built frames talk exported once per session with that --transcript; read-only."""

    def make(transcript: str) -> Path:
        out = built.parent / f"frames-{transcript}.html"
        with (built.parent / "export.lock").open("w") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            if not out.exists():
                r = mpres(
                    "export", str(built), "--out", str(out), "--transcript", transcript, "--workers", str(TEST_WORKERS)
                )
                assert r.returncode == 0, r.stdout + r.stderr
        return out

    return make


# Per module, not per session: pytest closes module fixtures at the module's end, so a test elsewhere (the e2e chain)
# can start its own Playwright in the same worker; two live sync Playwrights in one thread refuse to run.
@pytest.fixture(scope="module")
def playwright():
    with sync_playwright() as pw:
        yield pw


@pytest.fixture(scope="module", params=["webkit", "chrome"])
def browser(request: pytest.FixtureRequest, playwright):
    """Headless WebKit, and the stock Chrome (it has the H.264 decoder bundled Chromium lacks)."""
    b = playwright.webkit.launch() if request.param == "webkit" else playwright.chromium.launch(channel="chrome")
    yield b
    b.close()


@pytest.fixture
def open_player(browser, exported):
    """open_player(transcript, viewport) → the exported page, offline: every request that is not the file itself or a
    Blob is aborted and recorded, and must not happen; neither may a page error."""
    opened = []

    def make(transcript: str = "none", viewport: tuple[int, int] = (960, 600), file: Path | None = None) -> Player:
        """`file`: a page of the test's own instead of the session's export."""
        context = browser.new_context(viewport={"width": viewport[0], "height": viewport[1]})
        aborted: list[str] = []
        errors: list[str] = []

        def route(r) -> None:
            if r.request.url.startswith(("file:", "blob:")):
                r.continue_()
            else:
                aborted.append(r.request.url)
                r.abort()

        context.route("**/*", route)
        context.add_init_script(PAGE_JS)
        page = context.new_page()
        page.on("pageerror", lambda e: errors.append(str(e)))
        opened.append((context, aborted, errors))  # errors is the Player's list: a test may take the ones it expects
        page.goto((file or exported(transcript)).as_uri())
        page.evaluate("T.watch()")
        p = Player(page, errors)
        p.settle(0, 0)  # Before: beat 0's first frame
        return p

    yield make
    for context, aborted, errors in opened:
        context.close()
        assert aborted == [] and errors == []


@pytest.fixture
def player(open_player) -> Player:
    return open_player()


@pytest.fixture
def frames(exported):
    beats = manifest(exported("none").read_text())["beats"]
    assert [b["kind"] for b in beats] == ["beat", "beat", "loop", "beat"]
    return [b["frames"] for b in beats]
