from manim import RIGHT, FadeIn, Square


def construct(talk):
    talk.beat("too-far")
    talk.play(FadeIn(Square(1).shift(RIGHT * 7.5)))
