import contextlib
import os
import tempfile
from pathlib import Path

from manim import FadeIn, Square


def construct(talk):
    talk.beat("scratch")
    scratch = Path(tempfile.gettempdir()) / "mpres-scratch"
    scratch.write_text("x")  # writing is fine ...
    with contextlib.suppress(PermissionError):  # swallowed here, still reported
        scratch.read_text()  # ... reading it back is a read outside the talk
    os.listdir(tempfile.gettempdir())  # and so is listing the temp folder itself
    talk.play(FadeIn(Square(1)))
