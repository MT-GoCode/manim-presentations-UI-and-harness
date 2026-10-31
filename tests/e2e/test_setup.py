"""setup.sh's PATH routing, run for real on a copy of this repo under a throwaway HOME (the copy gets its own venv
from the shared uv cache and an APFS clone of this repo's TinyTeX, so nothing is downloaded and the real
~/.local/bin is never touched)."""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).parents[2]
SKIP = {".venv", ".tinytex", "test-results", ".git", "__pycache__", ".pytest_cache", ".ruff_cache"}


@pytest.fixture
def clone(tmp_path):
    dst = tmp_path / "repo"
    shutil.copytree(REPO, dst, ignore=lambda d, names: [n for n in names if n in SKIP])
    subprocess.run(["cp", "-cR", str(REPO / ".tinytex"), str(dst / ".tinytex")], check=True)
    return dst


def run_setup(repo: Path, home: Path, path: str, shell: str = "/bin/zsh"):
    env = {
        "HOME": str(home),
        "PATH": path,
        "SHELL": shell,
        "ZDOTDIR": str(home / "zdot"),
        "UV_CACHE_DIR": os.environ.get("UV_CACHE_DIR", str(Path.home() / ".cache" / "uv")),
    }
    (home / "zdot").mkdir(parents=True, exist_ok=True)
    return subprocess.run(["./setup.sh"], cwd=repo, env=env, capture_output=True, text=True)


SYSTEM_PATH = "/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin"


def test_off_path_appends_the_rc_line_once(clone, tmp_path):
    home = tmp_path / "home"
    for _ in range(2):
        r = run_setup(clone, home, SYSTEM_PATH)
        assert r.returncode == 0, r.stdout + r.stderr
    rc = (home / "zdot" / ".zshrc").read_text().splitlines()
    assert rc.count('export PATH="$HOME/.local/bin:$PATH"') == 1
    assert os.readlink(home / ".local/bin/mpres") == str(clone / "bin/mpres")


def test_a_link_to_another_clone_is_relinked_and_reported(clone, tmp_path):
    home = tmp_path / "home"
    (home / ".local/bin").mkdir(parents=True)
    (home / ".local/bin/mpres").symlink_to("/elsewhere/bin/mpres")
    r = run_setup(clone, home, f"{home}/.local/bin:{SYSTEM_PATH}")
    assert r.returncode == 0, r.stdout + r.stderr
    assert f"relinked {home}/.local/bin/mpres: /elsewhere/bin/mpres -> {clone}/bin/mpres" in r.stdout
    assert os.readlink(home / ".local/bin/mpres") == str(clone / "bin/mpres")
    assert not (home / "zdot" / ".zshrc").exists()  # ~/.local/bin already on PATH (as CI arranges): no rc line


def test_a_shadowing_mpres_fails_naming_it(clone, tmp_path):
    home = tmp_path / "home"
    shadow = tmp_path / "shadow"
    shadow.mkdir()
    (shadow / "mpres").write_text("#!/bin/sh\n")
    (shadow / "mpres").chmod(0o755)
    r = run_setup(clone, home, f"{shadow}:{home}/.local/bin:{SYSTEM_PATH}")
    assert r.returncode == 1
    assert f"resolves to {shadow}/mpres" in r.stderr
