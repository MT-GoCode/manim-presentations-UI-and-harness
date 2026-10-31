import numpy as np
from manim import BLUE, GREEN, ORANGE, Circle, FadeIn, FadeOut, Square, Transform


def construct(talk):
    talk.loop("cycle")  # fade the head out, append a fresh task, shift the rest with move_to: pixel-closed
    slots = [np.array([-3.0 + 1.5 * i, 1.5, 0.0]) for i in range(4)]
    tasks = [Square(0.6, color=GREEN, fill_opacity=0.8).move_to(s) for s in slots]
    talk.add(*tasks)
    head = tasks.pop(0)
    fresh = Square(0.6, color=GREEN, fill_opacity=0.8).move_to(slots[-1])
    talk.play(FadeOut(head), run_time=0.3)
    talk.play(*(t.animate.move_to(slots[i]) for i, t in enumerate(tasks)), FadeIn(fresh), run_time=0.3)

    talk.loop("waits")
    talk.wait(0.2)
    pulse = Circle(0.3, color=BLUE).shift([0, -1.5, 0])
    talk.play(FadeIn(pulse), run_time=0.2)
    talk.play(FadeOut(pulse), run_time=0.2)
    talk.wait(0.2)

    talk.loop("hand-closed")  # the closing play animates other mobjects than the opening one
    a = Square(0.5, color=ORANGE).shift([-2, -1.5, 0])
    talk.add(a)
    b = Circle(0.25, color=ORANGE).shift([-2, -1.5, 0])
    talk.play(Transform(a, b), run_time=0.3)
    back = Square(0.5, color=ORANGE).shift([-2, -1.5, 0])
    talk.play(FadeOut(a), FadeIn(back), run_time=0.3)

    talk.loop("ticking")  # a non-time updater that runs every frame and lands where it began
    dot = Square(0.3, color=BLUE).move_to([2, -1.5, 0])
    phase = {"n": 0}

    def sway(m):
        phase["n"] += 1
        m.move_to([2 + 0.5 * np.sin(phase["n"] * np.pi / 6), -1.5, 0])

    dot.add_updater(sway)
    talk.add(dot)
    talk.wait(0.4)  # 12 frames at 30 fps: one full period of sin(n·π/6), ending exactly where it started
    dot.clear_updaters()
