from helpers.stage import chapter_card, fixed_title
from manim import BLUE, LEFT, RIGHT, Dot, FadeIn, VGroup


def construct(talk):
    talk.beat("title-card")
    chapter_card(talk)

    talk.beat("the-idea")
    title = fixed_title("One idea per beat")
    dots = VGroup(*[Dot(color=BLUE).shift(LEFT * 2 + RIGHT * i) for i in range(5)])
    talk.play(FadeIn(title))
    talk.play(FadeIn(dots, lag_ratio=0.2))
