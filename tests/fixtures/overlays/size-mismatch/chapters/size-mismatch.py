from manim import RIGHT, Square, Text, Transform, VGroup


def construct(talk):
    talk.beat("morph")
    pair = VGroup(Text("a", font_size=40), Square(0.5)).arrange(RIGHT, buff=1)
    talk.add(pair)
    talk.play(Transform(pair, VGroup(Square(0.5), Square(0.5)).arrange(RIGHT, buff=1)))  # its text has no text slot
