from manim import RIGHT, Square, Text, Transform, VGroup


def construct(talk):
    talk.beat("morphs-back")
    g = VGroup(Text("a", font_size=40), Text("b", font_size=40)).arrange(RIGHT, buff=1)
    talk.add(g)
    talk.play(Transform(g, VGroup(Text("c", font_size=40), Square(0.5)).arrange(RIGHT, buff=1)))
    talk.play(Transform(g, VGroup(Text("d", font_size=40), Text("e", font_size=40)).arrange(RIGHT, buff=1)))
