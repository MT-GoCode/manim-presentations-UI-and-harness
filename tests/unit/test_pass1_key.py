"""A chapter's pass-1 key moves with every part of what its pass 1 depends on."""

import pytest

from manim_presentations.build import pass1_base, pass1_key

PARTS = {
    "engine": "e",
    "identity": {"manim": "0.22.0"},
    "libraries": "l",
    "cache_id": "c",
    "env": {"PATH": "/usr/bin"},
    "settings": "{}",
    "title": "Chapter",
}
CHANGED = {
    "engine": "e2",
    "identity": {"manim": "0.23.0"},
    "libraries": "l2",
    "cache_id": "c2",
    "env": {"PATH": "/opt/bin"},
    "settings": '{"x": 1}',
    "title": "Renamed",
}


@pytest.mark.parametrize("part", list(PARTS))
def test_each_part_moves_the_key(part, tmp_path):
    before = pass1_key(pass1_base(**PARTS), tmp_path, ())
    after = pass1_key(pass1_base(**{**PARTS, part: CHANGED[part]}), tmp_path, ())
    assert before != after


def test_an_input_moves_the_key_by_its_content_and_its_existence(tmp_path):
    base = pass1_base(**PARTS)
    absent = pass1_key(base, tmp_path, ("assets/x",))
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "x").write_text("one")
    one = pass1_key(base, tmp_path, ("assets/x",))
    (tmp_path / "assets" / "x").write_text("two")
    assert len({absent, one, pass1_key(base, tmp_path, ("assets/x",))}) == 3
