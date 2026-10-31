"""The built talk as data: Deck.open's hard failures, what makes a build stale, and the structure check."""

import json
import re

import pytest
from conftest import TEST_WORKERS, mpres

from manim_presentations.deck import Deck, IncompatibleBuild, Layout, Stale, require_fresh


def built(talk, name="edge"):
    root = talk(name)
    r = mpres("build", str(root), "--workers", str(TEST_WORKERS))
    assert r.returncode == 0, r.stdout + r.stderr
    return root


def test_never_built_is_incompatible(talk):
    with pytest.raises(IncompatibleBuild, match="never built; run: mpres build"):
        Deck.open(talk("edge"))


def test_another_schema_is_incompatible(talk):
    root = built(talk)
    index = root / "build" / "index.json"
    raw = json.loads(index.read_text())
    raw["schema"] = 0
    index.write_text(json.dumps(raw))
    with pytest.raises(IncompatibleBuild, match="index schema 0, this engine reads 1"):
        Deck.open(root)


@pytest.mark.parametrize("lost", ["clip", "first_png"])
def test_a_lost_file_is_incompatible(talk, lost):
    root = built(talk)
    beat = json.loads((root / "build" / "index.json").read_text())["beats"][0]
    gone = Layout(root).clip(beat["clip"]) if lost == "clip" else root / "build" / beat["first_png"]
    gone.unlink()
    with pytest.raises(IncompatibleBuild, match="the build lost"):
        Deck.open(root)


def test_a_fresh_build_is_not_stale_and_carries_its_render_settings(talk):
    deck = Deck.open(built(talk))
    assert deck.stale == () and not deck.structure_mismatch
    assert (deck.render.pixel_width, deck.render.pixel_height, deck.render.fps) == (480, 270, 30)
    require_fresh(deck)


def test_narration_readme_and_ds_store_leave_it_fresh(talk):
    root = built(talk)
    script = root / "script.md"
    script.write_text(script.read_text().replace("## spin\n", "## spin\n\nIt turns.\n\n> breathe\n"))
    (root / "README.md").write_text("notes about this talk")
    (root / ".DS_Store").write_bytes(b"\0")
    deck = Deck.open(root)
    assert deck.stale == () and not deck.structure_mismatch


@pytest.mark.parametrize(
    "change,named",
    [
        (lambda r: (r / "talk.toml").write_text((r / "talk.toml").read_text().replace("480", "640")), "talk.toml"),
        (lambda r: (r / "assets" / "new.png").write_bytes(b"x"), "assets/new.png"),
        (
            lambda r: (r / "helpers" / "order.py").write_text((r / "helpers" / "order.py").read_text() + "\n"),
            "helpers/order.py",
        ),
    ],
    ids=["talk.toml", "new asset", "helper"],
)
def test_a_changed_input_makes_it_stale_naming_the_file(talk, change, named):
    root = built(talk)
    mpres("build", str(root), "--workers", str(TEST_WORKERS))  # a warm second build: no bytecode left behind
    change(root)
    deck = Deck.open(root)
    assert deck.stale == (named,)
    with pytest.raises(Stale, match=re.escape(named)):
        require_fresh(deck)


def test_a_title_edit_is_a_structure_change_and_rebuilds_only_the_card(talk):
    root = built(talk, "hello")
    script = root / "script.md"
    script.write_text(script.read_text().replace("# working: How a beat works", "# working: How beats work"))
    deck = Deck.open(root)
    assert deck.stale == () and deck.structure_mismatch
    with pytest.raises(Stale, match="script.md headings"):
        require_fresh(deck)
    r = mpres("build", str(root), "--workers", str(TEST_WORKERS))
    rendered = [m[1] for m in re.finditer(r"^\s*\d+\s+(\S+)\s.*\srendered\s", r.stdout, re.M)]
    assert rendered == ["working-card"]  # only the chapter card draws talk.title


def test_the_export_scratch_folder_survives_a_build(talk):
    root = built(talk)
    scratch = Layout(root).export_tmp
    scratch.mkdir()
    (scratch / "in-progress.mp4").write_bytes(b"an export's re-encode")
    mpres("build", str(root), "--workers", str(TEST_WORKERS))
    assert (scratch / "in-progress.mp4").exists()
