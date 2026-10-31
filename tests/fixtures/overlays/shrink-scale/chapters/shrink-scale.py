from manim import FadeIn, Square, Text, Transform


def construct(talk):
    talk.beat("shrinks-still")
    t = Text("big", font_size=16)
    talk.add(t)
    talk.play(Transform(t, Text("big", font_size=60)))
    t.scale(0.2)  # 60 · 0.2 = 12
    talk.play(FadeIn(Square(0.5).shift([3, 0, 0])))
