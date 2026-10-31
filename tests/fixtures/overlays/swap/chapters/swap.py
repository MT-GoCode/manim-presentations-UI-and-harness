from manim import RIGHT, Square, Text, Transform, VGroup


def construct(talk):
    talk.beat("trade")
    pair = VGroup(Text("a", font_size=40), Square(0.5)).arrange(RIGHT, buff=1)
    talk.add(pair)
    talk.play(Transform(pair, VGroup(Square(0.5), Text("tiny", font_size=8)).arrange(RIGHT, buff=1)))  # equal counts
