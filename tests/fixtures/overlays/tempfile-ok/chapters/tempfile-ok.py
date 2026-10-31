import tempfile

from manim import FadeIn, Square


def construct(talk):
    talk.beat("scratch-only")
    with tempfile.NamedTemporaryFile() as f:  # an exclusive create: nothing old can be read
        f.write(b"x")
    talk.play(FadeIn(Square(1)))
