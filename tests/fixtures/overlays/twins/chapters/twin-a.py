from manim import DOWN, UP, FadeIn, MathTex, Text


def construct(talk):
    talk.beat("twin-a-beat")
    talk.play(FadeIn(Text("same words", font_size=40).shift(UP)), FadeIn(MathTex(r"x^2 + y^2 = r^2").shift(DOWN)))
