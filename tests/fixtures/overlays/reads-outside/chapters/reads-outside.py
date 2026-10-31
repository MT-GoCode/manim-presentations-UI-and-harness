from manim import FadeIn, Square


def construct(talk):
    talk.beat("peek")
    try:
        open("/etc/hosts").read()  # outside the talk; swallowing the error must not hide it
    except OSError:
        pass
    talk.play(FadeIn(Square(1)))
