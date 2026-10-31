import tempfile
from pathlib import Path

from manim import FadeIn, Square


def construct(talk):
    talk.beat("scratch")
    scratch = Path(tempfile.gettempdir()) / "mpres-scratch"
    scratch.write_text("x")  # writing is fine ...
    scratch.read_text()  # ... reading it back is a read outside the talk
    talk.play(FadeIn(Square(1)))
