from manim import DOWN, UP, FadeIn, MathTex, Text, Write


def construct(talk):
    talk.beat("words")
    talk.play(Write(Text("Edge", font_size=48).shift(UP)))
    talk.play(FadeIn(MathTex(r"e^{i\pi} + 1 = 0", font_size=48).shift(DOWN)))
