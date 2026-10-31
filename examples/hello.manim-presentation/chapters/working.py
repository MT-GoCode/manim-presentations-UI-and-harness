import numpy as np
from helpers.stage import chapter_card, fixed_title
from manim import GREEN, YELLOW, Circle, FadeIn, FadeOut, ReplacementTransform, Square, VGroup


def construct(talk):
    talk.beat("working-card")
    chapter_card(talk)

    talk.beat("build-up")
    title = fixed_title("Three steps, one result")
    steps = VGroup(*[Square(0.8, color=GREEN) for _ in range(3)]).arrange(buff=0.8)
    result = Circle(1.0, color=YELLOW)
    talk.play(FadeIn(title), FadeIn(steps, lag_ratio=0.3))
    talk.play(ReplacementTransform(steps, result))

    talk.loop("keeps-going")
    slots = [np.array([-3.0 + 2.0 * i, -2.0, 0.0]) for i in range(4)]
    tokens = [Square(0.5, color=GREEN, fill_opacity=0.8).move_to(s) for s in slots]
    talk.add(*tokens)
    head = tokens.pop(0)
    fresh = Square(0.5, color=GREEN, fill_opacity=0.8).move_to(slots[-1])
    talk.play(FadeOut(head), run_time=0.5)
    talk.play(*(t.animate.move_to(slots[i]) for i, t in enumerate(tokens)), FadeIn(fresh), run_time=0.5)
