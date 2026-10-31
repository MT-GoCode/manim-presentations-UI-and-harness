from manim import BLUE, GREEN, LEFT, RIGHT, Circle, FadeIn, Square


def construct(talk):
    talk.beat("spin")
    square = Square(1, color=BLUE).shift(LEFT * 3)
    square.add_updater(lambda m, dt: m.rotate(dt))  # a dt mobject updater
    talk.add(square)
    drift = {"x": 0.0}

    def scene_updater(dt):  # a scene-level updater
        drift["x"] += dt

    talk.add_updater(scene_updater)
    talk.play(FadeIn(Circle(0.5, color=GREEN)))

    talk.beat("spin-off")
    square.clear_updaters()  # cleared mid-talk ...
    talk.remove_updater(scene_updater)
    talk.play(square.animate.shift(RIGHT * drift["x"]))

    talk.beat("after-spin")  # ... and followed by a later cut
    talk.play(square.animate.rotate(0.3))
