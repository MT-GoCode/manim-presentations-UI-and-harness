from manim import Square, Text, Transform


def construct(talk):
    talk.beat("sprouts")
    sq = Square(0.5)
    talk.add(sq)
    talk.play(Transform(sq, Text("tiny", font_size=8)))  # the square ends holding the text's glyphs
