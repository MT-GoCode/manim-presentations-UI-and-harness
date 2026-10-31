from manim import FadeIn, Square


def construct(talk):
    talk.loop("idle")
    talk.add(Square(1))
    talk.beat("after")
    talk.play(FadeIn(Square(0.5)))
