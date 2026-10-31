import time

from manim import FadeIn, Square


def construct(talk):
    talk.beat("waits")
    time.sleep(600)  # far longer than any test waits: only the parent-death watch or a kill ends it
    talk.play(FadeIn(Square(1)))
