from pathlib import Path

from manim_presentations.deck import Layout


def test_the_talk_file_set_drops_only_the_roots_build_folder(tmp_path):
    for rel in (
        "build/index.json",
        "build/.media/src/chapters/a.py",
        "assets/build/data.txt",
        "helpers/build/x.py",
        "helpers/__pycache__/x.cpython-313.pyc",
        "assets/__pycache__/y",
        ".git/HEAD",
        "assets/.hidden",
        "README.md",
        "script.md",
        "chapters/notes.md",
        "chapters/a.py",
        "talk.toml",
    ):
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text("x")
    assert Layout(tmp_path).talk_files() == [
        Path(p)
        for p in ("assets/build/data.txt", "chapters/a.py", "chapters/notes.md", "helpers/build/x.py", "talk.toml")
    ]
