from manim import LEFT, RIGHT, YELLOW, Create, Dot, FadeIn, FadeOut, Rectangle, Square, Text, VGroup


def construct(talk):
    talk.beat("attached")
    box = Square(1.5).shift(LEFT * 3)
    tag = VGroup(Text("on", font_size=40), Dot()).arrange().move_to(box.get_top())  # sits across the box's edge
    talk.attach(tag, box)  # marked through the group holding the text
    talk.play(Create(box), FadeIn(tag))

    talk.beat("bled")
    band = talk.bleed(Rectangle(width=20, height=0.4, fill_opacity=1, stroke_width=0).shift([0, -2.2, 0]))
    talk.play(FadeIn(band))

    talk.beat("passing")
    cursor = talk.transient(Dot(color=YELLOW).shift(RIGHT * 3))
    talk.play(FadeIn(cursor))
    talk.play(FadeOut(cursor))
