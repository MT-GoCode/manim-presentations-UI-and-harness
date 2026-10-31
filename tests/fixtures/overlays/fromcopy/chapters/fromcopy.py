from manim import DOWN, MathTex, TransformFromCopy


def construct(talk):
    talk.beat("copies-a-part")
    eq = MathTex("a", "+", "b", font_size=60)
    talk.add(eq)
    talk.play(TransformFromCopy(eq[2], MathTex("b", font_size=60).shift(DOWN)))
