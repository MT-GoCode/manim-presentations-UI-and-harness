from manim import FadeIn

from helpers.shapes import labelled_box


def construct(talk):
    talk.beat("from-helper")
    talk.play(FadeIn(labelled_box(talk, "ok")))
