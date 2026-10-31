from manim import RIGHT, Square


def construct(talk):
    talk.loop("drifts")
    box = Square(1)
    talk.add(box)
    talk.play(box.animate.shift(RIGHT * 0.5))  # never comes back: a jump at every wrap
