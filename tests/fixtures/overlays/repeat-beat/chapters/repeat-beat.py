from manim import FadeIn, Square


def construct(talk):
    talk.beat("again")
    talk.play(FadeIn(Square(1)))
    talk.beat("again")
    talk.play(FadeIn(Square(0.5)))
