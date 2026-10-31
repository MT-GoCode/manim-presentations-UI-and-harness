"""Pieces every chapter of this talk shares."""

from manim import BLACK, DOWN, UP, WHITE, FadeIn, FadeOut, Rectangle, Text


def chapter_card(talk):
    """A black card with the chapter's title from script.md, then a clean stage."""
    card = Rectangle(width=20, height=12, fill_color=BLACK, fill_opacity=1, stroke_width=0)
    title = Text(talk.title, font_size=56, color=WHITE)
    talk.attach(title, card)
    talk.play(FadeIn(card), FadeIn(title, shift=UP * 0.2))
    talk.wait(1)
    talk.play(FadeOut(title, shift=DOWN * 0.2), FadeOut(card))


def fixed_title(text):
    """The slot that stays in place and unchanged through a chapter."""
    return Text(text, font_size=40, color=WHITE).to_edge(UP)
