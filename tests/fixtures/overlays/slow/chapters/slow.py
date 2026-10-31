import time

from manim import FadeIn, Square


def construct(talk):
    talk.beat("waits")
    time.sleep(6)  # holds pass 1 open long enough for a test to kill the build parent mid-pass
    talk.play(FadeIn(Square(1)))
