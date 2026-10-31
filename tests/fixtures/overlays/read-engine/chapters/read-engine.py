from pathlib import Path

import manim_presentations
from manim import FadeIn, Square


def construct(talk):
    talk.beat("peek")
    (Path(manim_presentations.__file__).parents[1] / "pyproject.toml").read_text()  # on sys.path, not in the talk
    talk.play(FadeIn(Square(1)))
