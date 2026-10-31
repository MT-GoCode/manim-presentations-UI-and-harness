from manim import FadeIn, MathTex


def construct(talk):
    talk.beat("tiny-tex")
    talk.play(FadeIn(MathTex("x", font_size=30)))
