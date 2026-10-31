"""Fixtures for the export tests (loaded through `pytest_plugins`, never imported): the frames talk built once per
session, and a private copy of it per test."""

import fcntl
import os
import shutil
from pathlib import Path

import pytest
from conftest import TEST_WORKERS, mpres
from frames import FRAMES


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
