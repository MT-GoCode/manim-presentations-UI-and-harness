from manim import FadeIn, Square, Text


def construct(talk):
    talk.beat("crossing")
    box = Square(1.5)
    label = Text("edge", font_size=40).move_to(box.get_top())
    talk.play(FadeIn(box), FadeIn(label))
