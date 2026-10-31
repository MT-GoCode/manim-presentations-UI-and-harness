from manim import DecimalNumber, FadeIn


def construct(talk):
    talk.beat("counter")
    talk.play(FadeIn(DecimalNumber(3.14, font_size=24)))
