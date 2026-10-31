from manim import FadeIn, Square


def construct(talk):
    talk.beat("only-adds")
    talk.add(Square(1))
    talk.beat("plays")
    talk.play(FadeIn(Square(0.5)))
