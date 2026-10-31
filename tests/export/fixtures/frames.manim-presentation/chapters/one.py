from helpers.code import FrameCode
from manim import LEFT, RIGHT, Dot


def construct(talk):
    code = FrameCode(talk)
    dot = Dot().shift(LEFT * 3)
    code.start(1)
    talk.beat("a")
    code.play(dot.animate.shift(RIGHT * 2), run_time=1)

    code.start(2)
    talk.beat("b")
    code.play(dot.animate.shift(RIGHT * 2), run_time=1.5)
