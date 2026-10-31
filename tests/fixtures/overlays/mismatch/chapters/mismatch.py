from manim import FadeIn, Square


def construct(talk):
    talk.beat("written-as")
    talk.play(FadeIn(Square(1)))
