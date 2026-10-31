import textwrap

from manim import (
    DOWN,
    LEFT,
    RIGHT,
    UP,
    Arrow,
    Circle,
    Create,
    FadeIn,
    Line,
    Rectangle,
    VGroup,
    config,
)

from manim_presenters.scene import TalkSlide
from manim_presenters.transcript import Transcript

from .speedup import bump
from .visuals import CPU, DOCK, DOCK_SCALE, GPU, HOLD, INK, MOVE, QUIET, counter, label


def step(kind, phase, text):
    """One flow step: a GPU rectangle or CPU circle icon beside its phase and description."""
    color = GPU if kind == "gpu" else CPU
    if kind == "gpu":
        icon = Rectangle(width=0.6, height=0.42, color=color, fill_color=color, fill_opacity=0.2, stroke_width=3)
    else:
        icon = Circle(radius=0.23, color=color, fill_color=color, fill_opacity=0.2, stroke_width=3)
    words = VGroup(
        label(phase, 22, color), *(label(line, 25, INK) for line in textwrap.wrap(text, 30))
    ).arrange(DOWN, aligned_edge=LEFT, buff=0.08)
    cell = VGroup(Rectangle(width=0.6, height=0.46, stroke_width=0, fill_opacity=0), icon)
    return VGroup(cell, words).arrange(RIGHT, buff=0.35, aligned_edge=UP)


def flow(header, entries, left):
    rows = VGroup(*(step(*entry.split("|")) for entry in entries)).arrange(DOWN, aligned_edge=LEFT, buff=0.55)
    rows.move_to([0, 2.7, 0], aligned_edge=UP).shift(RIGHT * (left - rows.get_left()[0]))
    arrows = VGroup(
        *(Arrow(a[0].get_bottom(), b[0].get_top(), buff=0.12, color=QUIET, stroke_width=3) for a, b in zip(rows, rows[1:]))
    )
    head = label(header, 36, INK).move_to([0, 3.4, 0]).align_to(rows, LEFT)
    return head, rows, arrows


class Kernels(TalkSlide):
    chapter_id = "05"

    def construct(self):
        content = Transcript.load(self.presentation_path / "transcript.json").by_id
        speed = counter("1.44x")
        self.add(speed)
        self.beat("05.1")
        self.wait(1 / config.frame_rate)
        title, normal_header, *normal_steps = content["05.1"].screen
        heading = label(title, 36).move_to([-1.3, 4.35, 0])
        head, rows, arrows = flow(normal_header, normal_steps, -7.3)
        self.play(
            FadeIn(heading),
            FadeIn(head),
            speed.animate.scale(DOCK_SCALE).move_to(DOCK),
            run_time=MOVE,
        )
        for i, row in enumerate(rows):
            self.play(FadeIn(row, shift=RIGHT * 0.2), *([Create(arrows[i - 1])] if i else []), run_time=MOVE)
        self.wait(HOLD)

        self.beat("05.2")
        quack_header, *quack_steps = content["05.2"].screen
        divider = Line([-0.25, 3.7, 0], [-0.25, -4.6, 0], color=QUIET, stroke_width=2)
        head2, rows2, arrows2 = flow(quack_header, quack_steps, 0.35)
        self.play(Create(divider), FadeIn(head2), run_time=MOVE)
        for i, row in enumerate(rows2):
            self.play(FadeIn(row, shift=RIGHT * 0.2), *([Create(arrows2[i - 1])] if i else []), run_time=MOVE)
        self.wait(HOLD)

        self.beat("05.3")
        bump(
            self,
            speed,
            "Speedup due to better training kernel & forward/backward compilation",
            "1.44x",
            "2x",
            return_to_side=False,
        )
        self.wait(HOLD)
