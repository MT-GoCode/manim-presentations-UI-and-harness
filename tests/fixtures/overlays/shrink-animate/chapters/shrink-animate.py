from manim import Text, Transform


def construct(talk):
    talk.beat("shrinks")
    t = Text("big", font_size=16)
    talk.add(t)
    talk.play(Transform(t, Text("big", font_size=60)))
    talk.play(t.animate.scale(0.2))  # 60 · 0.2 = 12
