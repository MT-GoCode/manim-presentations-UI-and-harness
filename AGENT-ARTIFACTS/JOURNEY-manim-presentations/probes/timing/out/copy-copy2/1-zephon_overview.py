import json
from itertools import pairwise

from manim import (
    Arrow,
    Circle,
    FadeIn,
    FadeOut,
    Indicate,
    Line,
    Rectangle,
    ReplacementTransform,
    SurroundingRectangle,
    VGroup,
    config,
)

from manim_presenters.scene import TalkSlide
from manim_presenters.transcript import Transcript

from .speedup import bump, money_shot
from .visuals import (
    DOCK,
    DOCK_SCALE,
    counter,
    HOLD,
    INK,
    MOVE,
    QUIET,
    label,
)

LIVE = "#4BE0D0"
TOKENS = "#82B9FF"
FOCUS = "#FFC273"
SURFACE = "#10202A"
PANEL_SURFACE = "#0A1118"


class PipelineNode(VGroup):
    def __init__(self, words, width, x, y):
        self.shell = Rectangle(
            width=width,
            height=0.68,
            color=INK,
            stroke_width=2,
            fill_color=SURFACE,
            fill_opacity=1,
        )
        self.words = label(words, 20)
        if self.words.width > width - 0.12:
            self.words.scale_to_fit_width(width - 0.12)
        super().__init__(self.shell, self.words)
        self.move_to([x, y, 0])


class Pipeline(VGroup):
    def __init__(self):
        xs = (-6.35, -4.22, -1.88, 0.53, 3.08, 6.08)
        widths = (1.55, 1.3, 1.8, 1.55, 1.6, 1.2)
        raw_words = ("raw shards", "fetch", "tokenizer", "pack", "queue", "GPU")
        token_words = ("token IDs", "fetch", "pack", "queue", "GPU")
        self.raw = VGroup(
            *(
                PipelineNode(word, width, x, 2.72)
                for i, (word, width, x) in enumerate(
                    zip(raw_words, widths, xs, strict=True)
                )
            )
        )
        self.tokens = VGroup(
            *(
                PipelineNode(word, widths[i], xs[i], 1.46)
                for word, i in zip(
                    token_words,
                    (0, 1, 3, 4, 5),
                    strict=True,
                )
            )
        )
        self.links = VGroup(
            *(
                Arrow(
                    a.get_right(), b.get_left(), color=color, stroke_width=2, buff=0.07
                )
                for lane, color in ((self.raw, LIVE), (self.tokens, TOKENS))
                for a, b in pairwise(lane)
            )
        )
        self.lane_labels = VGroup(
            label("LIVE TEXT", 17, LIVE).move_to([-6.35, 3.18, 0]),
            label("PRETOKENIZED", 16, TOKENS).move_to([-6.35, 0.85, 0]),
        )
        self.bypass = label("tokenizer bypass", 17, TOKENS).move_to([-1.8, 1.97, 0])
        super().__init__(
            self.links, self.raw, self.tokens, self.lane_labels, self.bypass
        )


class RateRow(VGroup):
    def __init__(self, row, color, center_x, y, ceiling):
        self.identity = row["id"]
        self.values = tuple(row["values"])
        display_label = "ready ceiling" if row["id"] == "ceiling" else row["label"]
        self.words = label(display_label, 19, color)
        self.words.move_to([center_x - 1.55 + self.words.width / 2, y + 0.24, 0])
        self.numbers = label(
            f"{self.values[0]:.2f} / {self.values[1]:.2f}", 19, color
        ).move_to([center_x + 1.13, y + 0.24, 0])
        self.baselines = VGroup()
        self.bars = VGroup()
        for index, value in enumerate(self.values):
            bar_y = y - 0.07 - index * 0.22
            self.baselines.add(
                Line(
                    [center_x - 1.55, bar_y, 0],
                    [center_x + 1.55, bar_y, 0],
                    color=QUIET,
                    stroke_width=5,
                ).set_opacity(0.4)
            )
            self.bars.add(
                Line(
                    [center_x - 1.55, bar_y, 0],
                    [center_x - 1.55 + 3.1 * value / ceiling, bar_y, 0],
                    color=color,
                    stroke_width=5,
                )
            )
        super().__init__(self.baselines, self.bars, self.words, self.numbers)


class RatePanel(VGroup):
    def __init__(self, plot, center_x, rows, colors, row_centers, footer=None):
        self.frame = Rectangle(
            width=4.7,
            height=5.25,
            color=INK,
            stroke_width=2,
            fill_color=PANEL_SURFACE,
            fill_opacity=1,
        ).move_to([center_x, -2.0, 0])
        self.heading = label(f"{plot['workload']} · MTok/s", 23).move_to(
            [center_x, 0.16, 0]
        )
        by_id = {row["id"]: row for row in plot["rows"]}
        ceiling = max(by_id["ceiling"]["values"])
        self.rows = VGroup(
            *(
                RateRow(by_id[identity], color, center_x, y, ceiling)
                for identity, color, y in zip(rows, colors, row_centers, strict=True)
            )
        )
        self.footer = (
            label(footer, 18, QUIET).move_to([center_x, -3.85, 0])
            if footer
            else VGroup()
        )
        super().__init__(self.frame, self.heading, self.rows, self.footer)


class FeatureCard(VGroup):
    def __init__(self, lines, x, y, subtitle=None):
        self.shell = Rectangle(
            width=2.18,
            height=1.55,
            color=INK,
            stroke_width=2,
            fill_color=SURFACE,
            fill_opacity=1,
        ).move_to([x, y, 0])
        self.icon = Circle(
            radius=0.11,
            color=LIVE,
            stroke_width=2,
            fill_color=LIVE,
            fill_opacity=1,
        ).move_to([x - 0.78, y + 0.48, 0])
        self.words = VGroup(*(label(line, 20) for line in lines))
        self.words.arrange(direction=[0, -1, 0], buff=0.045)
        self.words.move_to([x, y + (0.03 if subtitle else 0), 0])
        self.subtitle = (
            label(subtitle, 16, QUIET).move_to([x, y - 0.51, 0])
            if subtitle
            else VGroup()
        )
        super().__init__(self.shell, self.icon, self.words, self.subtitle)


class ZephonOverview(VGroup):
    def __init__(self, evidence):
        self.title = label("Optimization 3: Make Zephon live tokenization go brrr", 36)
        self.title.move_to([-1.6, 4.38, 0])
        self.context = label("Text++ / double stream · 4 × H100", 20, QUIET)
        self.context.move_to([0, 3.72, 0])
        self.pipeline = Pipeline()
        self.text_rates = RatePanel(
            evidence["plots"]["text_plus_plus"],
            -5.2,
            ("ceiling", "hf", "v1"),
            (QUIET, TOKENS, LIVE),
            (-0.75, -1.75, -2.75),
            "Text++ trainer throughput",
        )
        self.mechanism_frame = Rectangle(
            width=4.7,
            height=5.25,
            color=INK,
            stroke_width=2,
            fill_color=PANEL_SURFACE,
            fill_opacity=1,
        ).move_to([0, -2.0, 0])
        self.mechanism_heading = label("Remove the stalls", 23).move_to([0, 0.16, 0])
        self.feature_cards = VGroup(
            FeatureCard(("Freeze hub", "objects"), -1.17, -1.3),
            FeatureCard(("int64", "positions"), 1.17, -1.3),
            FeatureCard(
                ("Cache hits", "concurrent"),
                -1.17,
                -3.15,
                subtitle="coordinate misses",
            ),
            FeatureCard(("One encode", "per text"), 1.17, -3.15),
        )
        self.double_rates = RatePanel(
            evidence["plots"]["double_stream"],
            5.2,
            ("ceiling", "pretokenized", "live_lock", "live_lock_free"),
            (QUIET, TOKENS, FOCUS, LIVE),
            (-0.75, -1.65, -2.55, -3.45),
        )
        super().__init__(
            self.title,
            self.context,
            self.pipeline,
            self.text_rates,
            self.mechanism_frame,
            self.mechanism_heading,
            self.feature_cards,
            self.double_rates,
        )


class ZephonSingle(TalkSlide):
    chapter_id = "06"

    def hold(self, *parts):
        self.remove(*self.mobjects)
        self.add(*parts, self.speed)
        self.wait(HOLD)

    def construct(self):
        content = Transcript.load(self.presentation_path / "transcript.json").by_id
        evidence = json.loads((self.presentation_path / "evidence.json").read_text())[
            "zephon"
        ]
        self.speed = counter("2x")
        self.add(self.speed)
        view = ZephonOverview(evidence)
        view.text_rates.remove(view.text_rates.rows)
        view.remove(view.feature_cards)
        view.double_rates.remove(view.double_rates.rows)

        self.beat("06.1")
        self.wait(1 / config.frame_rate)
        self.play(
            FadeIn(view),
            self.speed.animate.scale(DOCK_SCALE).move_to(DOCK),
            run_time=MOVE,
        )
        self.hold(view)

        self.beat("06.2")
        waiting = label("GPU waiting", 18, FOCUS).move_to([4.63, 3.18, 0])
        queue_focus = SurroundingRectangle(view.pipeline.raw[4], color=FOCUS, buff=0.12)
        self.play(FadeIn(waiting), FadeIn(queue_focus), run_time=MOVE)
        self.hold(view, waiting, queue_focus)

        self.beat("06.3")
        view.text_rates.add(view.text_rates.rows[0], view.text_rates.rows[1])
        self.play(
            FadeIn(view.text_rates.rows[0]),
            FadeIn(view.text_rates.rows[1]),
            run_time=MOVE,
        )
        self.hold(view, waiting, queue_focus)

        self.beat("06.4")
        pack_focus = SurroundingRectangle(view.pipeline.raw[3], color=FOCUS, buff=0.12)
        self.play(
            FadeOut(waiting),
            ReplacementTransform(queue_focus, pack_focus),
            Indicate(view.pipeline.raw[2].shell, color=LIVE),
            run_time=MOVE,
        )
        self.hold(view, pack_focus)

        self.beat("06.5")
        view.text_rates.add(view.text_rates.rows[2])
        self.play(FadeIn(view.text_rates.rows[2]), run_time=MOVE)
        self.hold(view, pack_focus)

        self.beat("06.6")
        comparison = SurroundingRectangle(
            VGroup(view.text_rates.rows[1], view.text_rates.rows[2]),
            color=LIVE,
            buff=0.08,
        )
        self.play(FadeOut(pack_focus), FadeIn(comparison), run_time=MOVE)
        self.hold(view, comparison)

        self.beat("06.7")
        gc = evidence["gc_pause_context"]
        gc_note = (
            VGroup(
                label("single stream · median full-GC pause", 16, FOCUS),
                label(f"{gc['before']} → {gc['after']} ms", 19),
            )
            .arrange(direction=[0, -1, 0], buff=0.04)
            .move_to([0, -0.22, 0])
        )
        view.add(view.feature_cards[0])
        self.play(
            FadeOut(comparison),
            FadeIn(view.feature_cards[0]),
            FadeIn(gc_note),
            run_time=MOVE,
        )
        self.hold(view, gc_note)

        self.beat("06.8")
        view.add(view.feature_cards[1])
        self.play(
            FadeOut(gc_note),
            FadeIn(view.feature_cards[1]),
            run_time=MOVE,
        )
        self.hold(view)

        self.beat("06.9")
        view.add(view.feature_cards[2])
        self.play(FadeIn(view.feature_cards[2]), run_time=MOVE)
        self.hold(view)

        self.beat("06.10")
        view.add(view.feature_cards[3])
        self.play(FadeIn(view.feature_cards[3]), run_time=MOVE)
        self.hold(view)

        self.beat("06.11")
        view.double_rates.add(*view.double_rates.rows)
        self.play(*(FadeIn(row) for row in view.double_rates.rows), run_time=MOVE)
        self.hold(view)

        self.beat("06.12")
        selector = view.pipeline.raw[2]
        changed = label("new tokenizer", 18, LIVE)
        if changed.width > selector.shell.width - 0.12:
            changed.scale_to_fit_width(selector.shell.width - 0.12)
        changed.move_to(selector.words)
        self.play(ReplacementTransform(selector.words, changed), run_time=MOVE)
        selector.remove(selector.words)
        selector.words = changed
        selector.add(changed)
        self.hold(view)

        self.beat("06.13")
        self.speed = bump(
            self,
            self.speed,
            "Speedup due to live tokenization",
            "2x",
            "4x",
            return_to_side=False,
        )
        self.wait(HOLD)

        self.beat("06.14")
        title, *arms = content["06.14"].screen
        money_shot(self, self.speed, title, arms)
        self.wait(HOLD)

        self.beat("06.15")
        self.play(
            *(FadeOut(m) for m in self.mobjects if m is not self.speed),
            run_time=MOVE,
        )
        self.wait(HOLD)
