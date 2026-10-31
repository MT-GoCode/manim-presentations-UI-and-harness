import subprocess
import sys

import pytest

from manim_presentations.cli import BoundaryError, talk_root


def make(tmp_path, name="t.manim-presentation", script="script.md"):
    root = tmp_path / name
    root.mkdir()
    (root / script).write_text("T\n")
    return root


def with_cfg(root):
    (root / "manim.cfg").write_text("")
    return root


def test_a_valid_talk_resolves(tmp_path):
    root = make(tmp_path)
    assert talk_root(str(root / ".." / root.name)) == root.resolve()


@pytest.mark.parametrize(
    "setup,message",
    [
        (lambda t: make(t, name="t"), "ends in .manim-presentation"),
        (lambda t: t / "missing.manim-presentation", "no such folder"),
        (lambda t: make(t, script="SCRIPT.md"), "no script.md"),
        (lambda t: with_cfg(make(t)), "use talk.toml"),
    ],
)
def test_boundary_refusals_say_what_is_wrong(tmp_path, setup, message):
    with pytest.raises(BoundaryError, match=message):
        talk_root(str(setup(tmp_path)))


def test_help_imports_no_manim():
    code = (
        "import sys, contextlib, io\nfrom manim_presentations import cli\n"
        "with contextlib.suppress(SystemExit), contextlib.redirect_stdout(io.StringIO()):\n"
        "    cli.main(['--help'])\nprint('manim' in sys.modules)"
    )
    out = subprocess.run([sys.executable, "-P", "-c", code], capture_output=True, text=True, check=True).stdout
    assert out.strip() == "False"


def test_import_contracts_hold():
    result = subprocess.run([sys.executable, "-m", "importlinter.cli", "lint"], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
