from manim import Text, VGroup

NAMES = {"alpha", "bravo", "charlie", "delta", "echo", "foxtrot", "golf", "hotel"}


def badges():
    """Draw order follows a set's iteration order: equal only if every process hashes strings the same way."""
    return VGroup(*[Text(n, font_size=32) for n in NAMES]).arrange_in_grid(2, 4, buff=0.3)
