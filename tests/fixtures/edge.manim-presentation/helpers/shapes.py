from manim import BLUE, Square, Text, VGroup


def labelled_box(talk, label):
    """Used by exactly one chapter; the box and its label are made here, so errors name the calling chapter line."""
    box = Square(1.2, color=BLUE)
    text = Text(label, font_size=36).move_to(box)
    talk.attach(text, box)
    return VGroup(box, text)
