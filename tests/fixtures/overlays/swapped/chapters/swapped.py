from manim import FadeIn, Square


def construct(talk):
    talk.beat("a")
    talk.play(FadeIn(Square(1)))
    talk.beat("b")
    talk.play(FadeIn(Square(0.5)))
