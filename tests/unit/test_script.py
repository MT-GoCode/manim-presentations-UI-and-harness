import pytest

from manim_presentations.script import load, parse, save_beat

SCRIPT = """Demo Talk

# intro: Introduction

> chapter note

## first: The First Beat

Hello **world**.

> private

```
# not a heading
```

## second

Two.

# outro

## third

Three.
"""


def test_structure_and_text():
    script = parse(SCRIPT)
    assert script.title == "Demo Talk"
    assert script.structure == (
        ("intro", "Introduction", (("first", "The First Beat"), ("second", None))),
        ("outro", None, (("third", None),)),
    )
    assert script.beat("second").text == "Two."
    assert "# not a heading" in script.beat("first").text
    assert script.beat("third").line == 23


def test_notes_are_split_from_narration():
    beat = parse(SCRIPT).beat("first")
    assert beat.notes == "private"
    assert "private" not in beat.narration
    assert beat.narration.startswith("Hello **world**.")


def test_title_grammar():
    script = parse("T\n\n# a-1:   Spaced  Title  \n\n## b:x\n\n## c\n")
    assert script.chapters[0].title == "Spaced  Title"
    assert [(b.slug, b.title) for b in script.chapters[0].beats] == [("b", "x"), ("c", None)]


def test_headings_inside_blockquote_and_list_are_text():
    script = parse("T\n\n# a\n\n## b\n\n> ## c\n\n- ## d\n")
    assert script.structure == (("a", None, (("b", None),)),)


@pytest.mark.parametrize(
    "bad,message",
    [
        ("T\n\n# Bad Slug\n", "bad slug"),
        ("T\n\n# a: ok\n\n## Bad: no\n", "bad slug"),
        ("T\n\n# a\n\n# a\n", "duplicate"),
        ("T\n\n## a\n", "before any"),
        ("# a\n", "title"),
    ],
)
def test_errors_name_the_problem(bad, message):
    with pytest.raises(ValueError, match=message):
        parse(bad)


def test_save_changes_only_that_beat(tmp_path):
    path = tmp_path / "script.md"
    path.write_text(SCRIPT)
    save_beat(path, "second", "Two changed.")
    assert path.read_text() == SCRIPT.replace("Two.", "Two changed.")
    assert load(path).beat("second").text == "Two changed."


def test_save_keeps_external_edit_to_another_beat(tmp_path):
    path = tmp_path / "script.md"
    path.write_text(SCRIPT)
    path.write_text(SCRIPT.replace("Three.", "Edited elsewhere."))
    save_beat(path, "first", "New first.")
    assert load(path).beat("third").text == "Edited elsewhere."


@pytest.mark.parametrize("typed", ["x\n\n## sneaky", "x\n# sneaky", "x\nTitle\n===", "x\n\n# chapter"])
def test_save_refuses_headings(tmp_path, typed):
    path = tmp_path / "script.md"
    path.write_text(SCRIPT)
    with pytest.raises(ValueError, match="headings belong"):
        save_beat(path, "first", typed)
    assert path.read_text() == SCRIPT


def test_save_refuses_a_title_edit_smuggled_through_the_last_beat(tmp_path):
    """The last beat's text runs to the end of the file, so a typed `## third: New` would retitle nothing but add
    a beat; a typed heading that duplicates an existing slug with a new title must be refused the same way."""
    path = tmp_path / "script.md"
    path.write_text(SCRIPT)
    with pytest.raises(ValueError):
        save_beat(path, "third", "Three.\n\n## third: Retitled")
    assert path.read_text() == SCRIPT


def test_save_into_empty_beat(tmp_path):
    path = tmp_path / "script.md"
    path.write_text("T\n\n# a\n\n## b\n\n## c\n\nx\n")
    save_beat(path, "b", "filled")
    assert load(path).beat("b").text == "filled"
    assert load(path).beat("c").text == "x"


def test_unicode_line_separators_do_not_shift_lines(tmp_path):
    path = tmp_path / "script.md"
    path.write_text("T\n\n# a\n\n## one\n\nhello world\x0cform\n\n## two\n\nsecond\n")
    assert load(path).beat("two").line == 9
    save_beat(path, "two", "NEW")
    assert load(path).beat("two").text == "NEW"
    assert "hello world\x0cform" in load(path).beat("one").text


def test_save_unknown_beat_is_value_error(tmp_path):
    path = tmp_path / "script.md"
    path.write_text("T\n\n# a\n\n## b\n\nx\n")
    with pytest.raises(ValueError, match="not in script.md"):
        save_beat(path, "gone", "x")
