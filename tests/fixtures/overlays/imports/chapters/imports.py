import statistics

from manim import FadeIn, Square

try:
    import not_a_module  # noqa: F401
except ImportError:
    pass


def construct(talk):
    talk.beat("std")
    talk.play(FadeIn(Square(statistics.mean([1, 2]))))
