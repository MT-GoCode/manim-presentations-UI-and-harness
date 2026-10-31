from manim import YELLOW, Dot, FadeIn, Square


def construct(talk):
    talk.beat("first")
    talk.play(FadeIn(Square(1)))
    talk.beat("second")
    talk.play(FadeIn(talk.transient(Dot(color=YELLOW).shift([2, 0, 0]))))
