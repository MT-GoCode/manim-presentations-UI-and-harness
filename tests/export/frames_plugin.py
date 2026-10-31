"""Fixtures for the export tests (loaded through `pytest_plugins`, never imported): the frames talk built once per
session, and a private copy of it per test."""

import fcntl
import os
import shutil
from pathlib import Path

import pytest
from conftest import TEST_WORKERS, mpres
from frames import FRAMES, PAGE_JS, Player
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
def page_file(built: Path) -> Path:
    """The built frames talk exported once per session with the defaults; read-only for every test."""
    out = built.parent / "frames.html"
    with (built.parent / "export.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if not out.exists():
            r = mpres("export", str(built), "--out", str(out), "--workers", str(TEST_WORKERS))
            assert r.returncode == 0, r.stdout + r.stderr
    return out


@pytest.fixture(scope="session")
def playwright():
    with sync_playwright() as pw:
        yield pw


@pytest.fixture(scope="session", params=["webkit", "chrome"])
def browser(request: pytest.FixtureRequest, playwright):
    """Headless WebKit, and the stock Chrome (it has the H.264 decoder bundled Chromium lacks)."""
    b = playwright.webkit.launch() if request.param == "webkit" else playwright.chromium.launch(channel="chrome")
    yield b
    b.close()


@pytest.fixture
def player(browser, page_file: Path):
    """The exported page, offline: every request that is not the file itself or a Blob is aborted and recorded, and
    must not happen; neither may a page error."""
    context = browser.new_context(viewport={"width": 960, "height": 600})
    aborted: list[str] = []

    def route(r) -> None:
        if r.request.url.startswith(("file:", "blob:")):
            r.continue_()
        else:
            aborted.append(r.request.url)
            r.abort()

    context.route("**/*", route)
    context.add_init_script(PAGE_JS)
    page = context.new_page()
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(page_file.as_uri())
    page.evaluate("T.watch()")
    p = Player(page, aborted)
    p.settle(0, 0)  # Before: beat 0's first frame
    yield p
    context.close()
    assert aborted == [] and errors == []
