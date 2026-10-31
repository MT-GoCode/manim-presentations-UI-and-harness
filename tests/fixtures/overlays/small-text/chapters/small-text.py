from manim import FadeIn, Text


def construct(talk):
    talk.beat("tiny")
    talk.play(FadeIn(Text("tiny", font_size=20)))
