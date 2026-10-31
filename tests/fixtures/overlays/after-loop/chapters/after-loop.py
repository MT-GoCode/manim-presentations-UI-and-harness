from manim import BLUE, Circle, FadeIn


def construct(talk):
    talk.beat("wrap-up")  # a beat after hello's loop, so Next can leave a running loop
    talk.play(FadeIn(Circle(1.0, color=BLUE)))
