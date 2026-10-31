from helpers.code import FrameCode
from manim import DOWN, LEFT, RIGHT, Dot


def construct(talk):
    code = FrameCode(talk)
    dot = Dot()
    code.start(3, period=30)  # the loop's two plays move the counter 0 → 15 → 30 ≡ 0
    talk.loop("c")
    code.play(dot.animate.shift(RIGHT), run_time=0.5)
    code.play(dot.animate.shift(LEFT), run_time=0.5)

    code.start(4)
    talk.beat("d")
    code.play(dot.animate.shift(DOWN), run_time=1)
