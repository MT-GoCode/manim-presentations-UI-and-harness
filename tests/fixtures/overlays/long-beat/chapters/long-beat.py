from manim import Circle, FadeIn, Square


def construct(talk):
    talk.beat("many")  # twelve one-second plays: with a small enough CHUNK_COST, one beat spans several chunks
    box = Square(1)
    talk.add(box)
    for i in range(12):
        talk.play(box.animate.rotate(0.2).shift([0.05 * (-1) ** i, 0, 0]))
    talk.play(FadeIn(Circle(0.3)))
