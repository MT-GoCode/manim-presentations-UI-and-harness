import time

from manim import FadeIn, Square


def construct(talk):
    talk.beat("ticks")
    talk.play(FadeIn(Square(1 + time.time() % 1)))  # a clock read shapes the frames: nondeterministic
