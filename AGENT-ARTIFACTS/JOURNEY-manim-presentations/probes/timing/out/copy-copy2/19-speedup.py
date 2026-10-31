import textwrap

from manim import (
    DOWN,
    ORIGIN,
    UP,
    Arrow,
    FadeIn,
    FadeOut,
    GrowArrow,
    Rectangle,
    ReplacementTransform,
    Transform,
    VGroup,
)

from .visuals import (
    CODE,
    CPU,
    DOCK,
    DOCK_SCALE,
    EVAL,
    HOLD,
    INK,
    MATH,
    MOVE,
    PANEL,
    TRAIN,
    WEB,
    counter,
    elbow,
    label,
)


def expand(scene, speed):
    scene.play(
        *(FadeOut(m) for m in scene.mobjects if m is not speed),
        speed.animate.scale(1 / DOCK_SCALE).move_to(ORIGIN),
        run_time=MOVE,
    )


def dock(scene, speed):
    scene.play(speed.animate.scale(DOCK_SCALE).move_to(DOCK), run_time=MOVE)


def bump(scene, speed, caption, old, new, *, return_to_side=True):
    """Expand the counter, show old then new, squish to the new value, and optionally dock."""
    expand(scene, speed)
    box, head, number = speed
    wide = Rectangle(width=10, height=3.2, color=CPU, fill_color=PANEL, fill_opacity=1)
    wide_head = label("Speedup Counter", 30, CPU).move_to(wide.get_top() + DOWN * 0.45)
    title = VGroup(*(label(line, 38, INK) for line in textwrap.wrap(caption, 34))).arrange(DOWN, buff=0.12)
    title.next_to(wide, UP, buff=0.4)
    first = label(old, 84, EVAL).move_to([-3.3, -0.3, 0])
    second = label(new, 84, EVAL).move_to([3.3, -0.3, 0])
    arrow = Arrow([-1.2, -0.3, 0], [1.2, -0.3, 0], color=INK, buff=0)
    scene.play(
        Transform(box, wide),
        Transform(head, wide_head),
        ReplacementTransform(number, first),
        FadeIn(title),
        run_time=MOVE,
    )
    scene.play(GrowArrow(arrow), FadeIn(second), run_time=MOVE)
    scene.wait(HOLD)
    target = counter(new)
    scene.play(
        FadeOut(title),
        FadeOut(first),
        FadeOut(arrow),
        Transform(box, target[0]),
        Transform(head, target[1]),
        ReplacementTransform(second, target[2]),
        run_time=MOVE,
    )
    speed = VGroup(box, head, target[2])
    scene.remove(box, head, target[2])
    scene.add(speed)
    if return_to_side:
        scene.wait(HOLD)
        dock(scene, speed)
    return speed


def money_shot(scene, speed, title_text, arms):
    title = label(title_text, 42, INK).move_to([0, 3.7, 0])
    scene.play(FadeIn(title), run_time=MOVE)
    box = speed[0]
    placements = ((-1, 2.0), (-1, -2.0), (1, 2.0), (1, -2.0))
    for text, color, (side, y) in zip(arms, (WEB, CODE, MATH, TRAIN), placements, strict=True):
        card = VGroup(*(label(line, 32, color) for line in textwrap.wrap(text, 17))).arrange(DOWN, buff=0.1)
        card.move_to([side * 5.1, y, 0])
        edge = card.get_left() if side > 0 else card.get_right()
        start = box.get_right() if side > 0 else box.get_left()
        link = elbow(start, [side * 2.6, start[1], 0], [side * 2.6, y, 0], edge + [side * -0.2, 0, 0], color=color)
        scene.play(FadeIn(card), FadeIn(link), run_time=MOVE)
    return title


def final_zoom_parts(caption, value):
    """The expanded counter, built identically where a chapter ends on it and where the next starts from it."""
    wide = Rectangle(width=10, height=3.2, color=CPU, fill_color=PANEL, fill_opacity=1)
    head = label("Speedup Counter", 30, CPU).move_to(wide.get_top() + DOWN * 0.45)
    top = label(caption, 40).next_to(wide, UP, buff=0.4)
    number = label(value, 84, EVAL).move_to([0, -0.3, 0])
    return wide, head, top, number


SWARM_VALUE = "4x + A LOT"
