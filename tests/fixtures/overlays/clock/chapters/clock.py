import time

from manim import FadeIn, Square


def construct(talk):
    talk.beat("ticks")
    talk.play(FadeIn(Square(1 + (time.time_ns() % 1000) / 1e4)))  # a clock read shapes the frames: nondeterministic
