from manim import FadeIn, Square


def construct(talk):
    talk.play(FadeIn(Square(1)))
    talk.beat("late")
