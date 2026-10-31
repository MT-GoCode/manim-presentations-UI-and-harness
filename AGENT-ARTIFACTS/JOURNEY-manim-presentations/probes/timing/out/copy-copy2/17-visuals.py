import textwrap

import numpy as np
from manim import (
    DOWN,
    LEFT,
    RIGHT,
    UP,
    Arc,
    Arrow,
    Circle,
    Line,
    Rectangle,
    SurroundingRectangle,
    Text,
    VGroup,
    VMobject,
)

INK = "#FFFFFF"
QUIET = "#989EAA"
CPU = "#FFE500"
GPU = "#A86BFF"
WEB = "#00F5B5"
CODE = "#FF38BD"
MATH = "#FF9B00"
TRAIN = "#00D9FF"
EVAL = "#B8FF32"
OVERHEAD = "#FF3348"
PANEL = "#000000"

# Canvas dimensions, colors and pacing are projection design decisions.
MOVE = 0.6
HOLD = 0.25


def label(value, size=32, color=INK):
    return Text(value, font="Avenir Next", font_size=size, color=color)


class CpuJob(VGroup):
    def __init__(self, radius=0.56):
        self.shape = Circle(
            radius=radius, color=CPU, stroke_width=3, fill_color=CPU, fill_opacity=0.06
        )
        self.loading = Arc(
            radius=radius * 0.78,
            start_angle=np.pi / 5,
            angle=np.pi * 1.35,
            color=CPU,
            stroke_width=3,
        )
        self.cores = VGroup(
            *(
                Rectangle(
                    width=radius * 0.22,
                    height=radius * 0.22,
                    stroke_width=0,
                    fill_color=CPU,
                    fill_opacity=0.9,
                )
                for _ in range(4)
            )
        ).arrange_in_grid(rows=2, cols=2, buff=radius * 0.1)
        super().__init__(
            self.shape,
            self.loading,
            self.cores,
            label("CPU", 22, CPU).next_to(self.shape, DOWN, buff=0.14),
        )


class GpuJob(VGroup):
    def __init__(self, *lines, width=3.3, height=1.6, size=32):
        self.shape = Rectangle(
            width=width,
            height=height,
            color=GPU,
            stroke_width=3,
            fill_color=GPU,
            fill_opacity=0.04,
        )
        words = (
            VGroup(*(label(line, size) for line in lines))
            .arrange(DOWN, buff=0.12)
            .shift(UP * height * 0.1)
        )
        self.activity = (
            VGroup(
                *(
                    Rectangle(
                        width=width * 0.075,
                        height=height * 0.11,
                        stroke_width=0,
                        fill_color=color,
                        fill_opacity=0.75,
                    )
                    for color in (TRAIN, WEB, GPU, TRAIN, WEB, GPU, TRAIN, WEB)
                )
            )
            .arrange(RIGHT, buff=width * 0.025)
            .shift(DOWN * height * 0.33)
        )
        super().__init__(self.shape, VGroup(words, self.activity))


class GpuTimeline(VGroup):
    def __init__(self, name, useful_color):
        self.shape = Rectangle(width=3.3, height=1.2, color=GPU, stroke_width=3)
        self.phases = VGroup()
        left = -1.65
        # Illustrative phase widths preserve readable labels, not measured durations.
        for width, words, color, size, text_color in (
            (0.9, ("Startup",), OVERHEAD, 18, INK),
            (1.5, tuple(name.split()), useful_color, 20, PANEL),
            (0.9, ("Export",), OVERHEAD, 18, INK),
        ):
            band = Rectangle(
                width=width,
                height=1.2,
                stroke_width=0,
                fill_color=color,
                fill_opacity=0.9,
            )
            text = VGroup(*(label(word, size, text_color) for word in words)).arrange(
                DOWN, buff=0.1
            )
            phase = VGroup(band, text).move_to([left + width / 2, 0, 0])
            self.phases.add(phase)
            left += width
        super().__init__(self.shape, self.phases)


class BenefitCard(VGroup):
    """Stacked text rows: each (text, color) pair wraps to its own lines."""

    def __init__(self, *rows, wrap=26, size=26):
        blocks = VGroup(
            *(
                VGroup(
                    *(label(line, size, color) for line in textwrap.wrap(text, wrap))
                ).arrange(DOWN, buff=0.1)
                for text, color in rows
            )
        ).arrange(DOWN, buff=0.2)
        super().__init__(blocks)


def elbow(*points, color=QUIET, tip=False):
    """Right-angle connector through the given points, ending in an arrow tip if asked."""
    if not tip:
        return VMobject(color=color, stroke_width=3).set_points_as_corners(
            [np.array(point, dtype=float) for point in points]
        )
    return VGroup(
        VMobject(color=color, stroke_width=3).set_points_as_corners(
            [np.array(point, dtype=float) for point in points[:-1]]
        ),
        Arrow(points[-2], points[-1], color=color, buff=0, stroke_width=3),
    )


class MixCard(VGroup):
    def __init__(self, name, proportions):
        self.shape = Rectangle(
            width=2.4, height=1.1, color=QUIET, fill_color=PANEL, fill_opacity=1
        )
        self.bar = (
            VGroup(
                *(
                    Rectangle(
                        width=2 * fraction,
                        height=0.25,
                        stroke_width=0,
                        fill_color=color,
                        fill_opacity=1,
                    )
                    for fraction, color in zip(
                        proportions, (WEB, CODE, MATH), strict=True
                    )
                )
            )
            .arrange(RIGHT, buff=0)
            .shift(DOWN * 0.25)
        )
        super().__init__(self.shape, label(name, 28).shift(UP * 0.18), self.bar)


class TitleView(VGroup):
    def __init__(self, screen):
        self.heading = (
            label(screen[0], 90)
            .set_color_by_gradient(WEB, CODE, GPU, MATH)
            .move_to([0, 1.3, 0])
        )
        first, second = screen[1].split(" in production ", maxsplit=1)
        self.subtitle = (
            VGroup(label(first, 32), label("in production " + second, 32))
            .arrange(DOWN, buff=0.22)
            .move_to([0, -0.6, 0])
        )
        self.job = GpuJob("GPU", width=2.4, height=1.1, size=28).move_to([0, -2.8, 0])
        super().__init__(self.heading, self.subtitle, self.job)


class ContextView(VGroup):
    def __init__(self, screen, *, highlighted=False):
        self.heading = label("Context", 58).move_to([0, 4.2, 0])
        # A three-row crop of the original Doc graph, with illustrative mix weights.
        ys = (2, 0, -2)
        self.cards = VGroup(
            *(
                MixCard(screen[0], weights).move_to([-6.25, y, 0])
                for weights, y in zip(
                    ((0.5, 0.3, 0.2), (0.25, 0.6, 0.15), (0.2, 0.25, 0.55)),
                    ys,
                    strict=True,
                )
            )
        )
        self.cpu = CpuJob(radius=0.42).move_to([-4.35, 0, 0])
        self.model_cpus = VGroup(
            *(
                CpuJob(radius=0.38).move_to([x, y, 0])
                for x, y in zip((-2.9, -2.65, -2.6), ys, strict=True)
            )
        )
        self.trains = VGroup(
            *(
                GpuTimeline(screen[2], TRAIN).move_to([x, y, 0])
                for x, y in zip((-0.2, 0.4, 0.1), ys, strict=True)
            )
        )
        self.evaluations = VGroup(
            *(
                GpuTimeline(screen[3], EVAL).move_to([x, y, 0])
                for x, y in zip((3.5, 4.1, 3.8), ys, strict=True)
            )
        )
        self.train, self.evaluate = self.trains[0], self.evaluations[0]
        self.row_cpu = self.model_cpus[0]
        self.other_cpus = VGroup(*self.model_cpus[1:])
        self.other_jobs = VGroup(*self.trains[1:], *self.evaluations[1:])
        links = []
        for card, cpu, train, evaluate in zip(
            self.cards, self.model_cpus, self.trains, self.evaluations, strict=True
        ):
            links.append(
                (
                    Line(
                        card.shape.get_right() + RIGHT * 0.08,
                        self.cpu.shape.get_left() + LEFT * 0.08,
                        color=QUIET,
                        stroke_width=2,
                    ),
                    VMobject(color=QUIET, stroke_width=2).set_points_as_corners(
                        [
                            self.cpu.shape.get_right(),
                            [-3.75, cpu.shape.get_y(), 0],
                            cpu.shape.get_left(),
                        ]
                    ),
                    Arrow(
                        cpu.shape.get_right(),
                        train.shape.get_left(),
                        color=QUIET,
                        buff=0.1,
                        stroke_width=2,
                    ),
                    Arrow(
                        train.shape.get_right(),
                        evaluate.shape.get_left(),
                        color=QUIET,
                        buff=0.06,
                        stroke_width=2,
                    ),
                )
            )
        # The first row's two arrows stay bright when the rest of the graph is quiet.
        self.row_links = VGroup(*links[0][2:])
        self.other_links = VGroup(
            *links[0][:2], *(link for row in links[1:] for link in row)
        )
        self.links = VGroup(self.other_links, self.row_links)
        self.return_path = VMobject(color=QUIET, stroke_width=2).set_points_as_corners(
            [[3.8, -2.6, 0], [3.8, -4, 0], [-6.25, -4, 0], [-6.25, -2.65, 0]]
        )
        self.legend = (
            VGroup(
                *(
                    label(word, 26, color)
                    for word, color in (("web", WEB), ("code", CODE), ("math", MATH))
                )
            )
            .arrange(RIGHT, buff=0.3)
            .move_to([-5.2, -4.45, 0])
        )
        self.time = VGroup(
            Arrow([-1.5, -3.25, 0], [5.5, -3.25, 0], color=QUIET, buff=0),
            label("time", 24, QUIET).move_to([1.7, -3.5, 0]),
            label("scores inform the next mix", 24, QUIET).move_to([1, -4.25, 0]),
        )
        self.scope_box = SurroundingRectangle(
            VGroup(self.row_cpu, self.train, self.evaluate), color=GPU, buff=0.25
        )
        self.scope_label = label("First project: Move to pure pytorch", 36, GPU).next_to(
            self.scope_box, UP, buff=0.2
        )
        self.scope = VGroup(self.scope_box, self.scope_label)
        self.quiet_parts = (
            self.cards,
            self.cpu,
            self.other_cpus,
            self.other_jobs,
            self.other_links,
            self.return_path,
            self.legend,
            self.time,
        )
        if highlighted:
            for part in self.quiet_parts:
                part.fade(0.65)
        super().__init__(
            self.heading,
            *self.quiet_parts,
            self.row_cpu,
            self.row_links,
            self.train,
            self.evaluate,
        )
        if highlighted:
            self.add(self.scope_box, self.scope_label)

DOCK = [6.2, 4.3, 0]
DOCK_SCALE = 0.6


def counter(value):
    number = label(value, 64 if len(value) <= 5 else 52, EVAL)
    box = Rectangle(width=max(3.6, number.width + 0.9), height=1.9, color=CPU, fill_color=PANEL, fill_opacity=1)
    return VGroup(
        box,
        label("Speedup Counter", 26, CPU).move_to(box.get_top() + DOWN * 0.4),
        number.move_to(box.get_center() + DOWN * 0.25),
    )


def docked(value):
    return counter(value).scale(DOCK_SCALE).move_to(DOCK)
