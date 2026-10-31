"""Incremental pass 1: a chapter's pass 1 runs again exactly when something it read changed (its file, a helper, an
asset, a folder it listed), or the settings, titles or engine; otherwise its stored record is reused, and the build's
result equals a full build's."""

import json
import shutil
from pathlib import Path

from conftest import REPO, TEST_WORKERS, mpres

from manim_presentations.deck import Layout

CHAPTERS = ("closures", "helpers-made", "loops", "marks", "motion", "paths", "sizes", "text")


def build(root: Path, env: dict[str, str] | None = None) -> None:
    r = mpres("build", str(root), "--workers", str(TEST_WORKERS), env=env)
    assert r.returncode == 0, r.stdout + r.stderr


def stores(root: Path) -> dict[str, int]:
    """Each chapter's stored record, by identity: a chapter whose pass 1 ran gets a new store."""
    return {c: (Layout(root).pass1_store(c) / "records.json").stat().st_ino for c in CHAPTERS}


def ran(root: Path, change, env: dict[str, str] | None = None) -> set[str]:
    before = stores(root)
    change(root)
    build(root, env)
    after = stores(root)
    return {c for c in CHAPTERS if after[c] != before[c]}


def append(rel: str, text: str = "\n"):
    return lambda root: (root / rel).write_text((root / rel).read_text() + text)


def test_a_rebuild_runs_no_chapter(prebuilt):
    assert ran(prebuilt("edge"), lambda root: None) == set()


def test_a_chapter_edit_runs_that_chapter_only(prebuilt):
    assert ran(prebuilt("edge"), append("chapters/text.py")) == {"text"}


def test_a_helper_edit_runs_the_chapters_that_import_it(prebuilt):
    root = prebuilt("edge")
    assert ran(root, append("helpers/shapes.py")) == {"helpers-made"}
    assert ran(root, append("helpers/order.py")) == {"paths"}


def test_an_asset_edit_runs_the_chapter_that_reads_it(prebuilt):
    def touch(root):
        (root / "assets" / "backdrop.png").write_bytes((root / "assets" / "backdrop.png").read_bytes() + b"\0")

    assert ran(prebuilt("edge"), touch) == {"paths"}


def test_a_new_file_in_a_listed_folder_runs_the_chapters_that_listed_it(prebuilt):
    """Importing from helpers/ lists it: a new module there can change what an import resolves to."""
    assert ran(prebuilt("edge"), lambda root: (root / "helpers" / "extra.py").write_text("X = 1\n")) == {
        "helpers-made",
        "paths",
    }


def test_settings_titles_and_the_engine_run_every_chapter(prebuilt, tmp_path):
    root = prebuilt("edge")
    toml = root / "talk.toml"
    assert ran(root, lambda r: toml.write_text(toml.read_text().replace("480", "640").replace("270", "360"))) == set(
        CHAPTERS
    )
    script = root / "script.md"
    lines = script.read_text().split("\n")
    assert ran(root, lambda r: script.write_text("\n".join([lines[0] + " (renamed)", *lines[1:]]))) == set(CHAPTERS)
    pkg = tmp_path / "engine" / "manim_presentations"
    shutil.copytree(REPO / "manim_presentations", pkg, ignore=shutil.ignore_patterns("__pycache__"))
    (pkg.parent / ".tinytex").symlink_to(REPO / ".tinytex")  # the engine finds its TeX beside its package
    (pkg / "talk.py").write_text((pkg / "talk.py").read_text() + "\n# an engine edit\n")
    assert ran(root, lambda r: None, env={"PYTHONPATH": str(pkg.parent)}) == set(CHAPTERS)


def test_a_removed_chapter_loses_its_store(prebuilt):
    root = prebuilt("edge")
    (root / "chapters" / "text.py").unlink()
    script = root / "script.md"
    text = script.read_text()
    start = text.index("\n# text")
    end = text.find("\n# ", start + 1)
    script.write_text(text[:start] + (text[end:] if end != -1 else "\n"))
    build(root)
    assert not Layout(root).pass1_store("text").exists()


def test_an_incremental_build_equals_a_full_one(prebuilt, tmp_path):
    """After a helper edit, the reused records and the re-run ones give exactly the beats a cold build gives."""
    root = prebuilt("edge")
    append("helpers/order.py", "\n# changed\n")(root)
    cold = tmp_path / "cold" / root.name
    shutil.copytree(root, cold, ignore=shutil.ignore_patterns("build"))
    build(root)
    build(cold)

    def beats(talk):
        return [
            (b["chapter"], b["slug"], b["fingerprint"])
            for b in json.loads(Layout(talk).index_path.read_text())["beats"]
        ]

    assert beats(root) == beats(cold)
