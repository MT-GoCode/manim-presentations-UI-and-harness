from manim import FadeIn, Table


def construct(talk):
    talk.beat("grid")
    talk.play(FadeIn(Table([["1", "2"], ["3", "4"]]).scale(0.3)))
