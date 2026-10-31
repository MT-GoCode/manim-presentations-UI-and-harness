import numpy as np
from manim import (
    DOWN,
    LEFT,
    RIGHT,
    UP,
    ApplyWave,
    Arrow,
    Create,
    Dot,
    FadeIn,
    FadeOut,
    GrowArrow,
    GrowFromEdge,
    LaggedStart,
    MoveAlongPath,
    Rotate,
    SurroundingRectangle,
    Transform,
    VGroup,
    config,
)

from manim_presenters.scene import TalkSlide
from manim_presenters.transcript import Transcript

from .code import TranscriptCode
from .visuals import (
    CODE,
    CPU,
    GPU,
    HOLD,
    INK,
    MATH,
    MOVE,
    QUIET,
    WEB,
    BenefitCard,
    ContextView,
    CpuJob,
    GpuJob,
    MixCard,
    TitleView,
    counter,
    elbow,
    label,
)


class Title(TalkSlide):
    chapter_id = "01"

    def construct(self):
        content = Transcript.load(self.presentation_path / "transcript.json").by_id
        self.beat("01.1")
        view = TitleView(content["01.1"].screen)
        self.play(FadeIn(view.heading, shift=UP * 0.2), run_time=MOVE)
        self.play(ApplyWave(view.heading, amplitude=0.16), run_time=MOVE)
        self.play(FadeIn(view.subtitle), run_time=MOVE)
        card = MixCard("mix", (0.4, 0.5, 0.1)).move_to(view.job)
        self.play(FadeIn(card[0]), FadeIn(card[1]), run_time=MOVE)
        self.play(
            LaggedStart(
                *(GrowFromEdge(segment, LEFT) for segment in card.bar), lag_ratio=0.2
            ),
            run_time=MOVE,
        )
        self.remove(*self.mobjects)
        self.add(view.heading, view.subtitle, card)
        self.play(FadeOut(card), run_time=MOVE / 2)
        self.play(FadeIn(view.job), run_time=MOVE / 2)
        self.wait(HOLD)


class Context(TalkSlide):
    chapter_id = "02"

    def construct(self):
        content = Transcript.load(self.presentation_path / "transcript.json").by_id
        initial = TitleView(content["01.1"].screen)
        self.add(initial)
        self.beat("02.1")
        self.wait(1 / config.frame_rate)
        view = ContextView(content["02.1"].screen)
        self.play(FadeOut(initial), FadeIn(view.heading), run_time=MOVE)
        self.play(
            LaggedStart(*(FadeIn(card) for card in view.cards), lag_ratio=0.2),
            run_time=MOVE,
        )
        self.play(
            FadeIn(view.cpu), Create(view.links), FadeIn(view.legend), run_time=MOVE
        )
        packets = VGroup(*(card.bar.copy().scale(0.25) for card in view.cards))
        self.add(*packets)
        self.play(
            Rotate(
                view.cpu.loading,
                angle=2 * np.pi,
                about_point=view.cpu.shape.get_center(),
            ),
            LaggedStart(
                *(packet.animate.move_to(view.cpu.shape) for packet in packets),
                lag_ratio=0.2,
            ),
            run_time=MOVE * 2,
        )
        self.play(
            LaggedStart(*(FadeIn(cpu) for cpu in view.model_cpus), lag_ratio=0.2),
            *(
                packet.animate.move_to(cpu.shape)
                for packet, cpu in zip(packets, view.model_cpus, strict=True)
            ),
            run_time=MOVE,
        )
        for jobs in (view.trains, view.evaluations):
            self.play(
                LaggedStart(*(Create(job.shape) for job in jobs), lag_ratio=0.2),
                run_time=MOVE,
            )
            self.play(
                LaggedStart(
                    *(
                        GrowFromEdge(phase, LEFT)
                        for job in jobs
                        for phase in job.phases
                    ),
                    lag_ratio=0.12,
                ),
                *(
                    packet.animate.move_to(job.shape.get_bottom() + UP * 0.12)
                    for packet, job in zip(packets, jobs, strict=True)
                ),
                run_time=MOVE * 2,
            )
        self.play(
            *(FadeOut(packet) for packet in packets),
            Create(view.return_path),
            FadeIn(view.time),
            run_time=MOVE,
        )
        score = Dot(view.return_path.get_start(), radius=0.09, color=GPU)
        self.add(score)
        self.play(MoveAlongPath(score, view.return_path), run_time=1)
        self.play(FadeOut(score), run_time=MOVE)
        self.remove(*self.mobjects)
        self.add(*view.submobjects)
        self.wait(HOLD)
        self.beat("02.2")
        self.play(
            *(part.animate.fade(0.65) for part in view.quiet_parts),
            FadeIn(view.scope),
            run_time=MOVE,
        )
        self.wait(HOLD)


class OneJob(TalkSlide):
    chapter_id = "03"

    def construct(self):
        content = Transcript.load(self.presentation_path / "transcript.json").by_id
        initial = ContextView(content["02.1"].screen, highlighted=True)
        self.add(*initial.submobjects)
        self.beat("03.1")
        self.wait(1 / config.frame_rate)
        title_text, job_text, name_text = content["03.1"].screen
        title = label(title_text, 46).move_to([0, 4.45, 0])
        old = VGroup(
            initial.row_cpu,
            initial.row_links,
            initial.train,
            initial.evaluate,
            initial.scope_box,
        )
        self.play(
            *(FadeOut(part) for part in initial.quiet_parts),
            FadeOut(initial.heading),
            FadeOut(initial.scope_label),
            old.animate.scale(0.55).move_to([0, 3.1, 0]),
            FadeIn(title),
            run_time=MOVE * 1.5,
        )
        cpu = CpuJob(radius=0.42).move_to([-2.2, 0.55, 0])
        job = GpuJob(job_text, width=3.4, height=1.4, size=30).move_to([0.9, 0.55, 0])
        link = Arrow(
            cpu.shape.get_right(), job.shape.get_left(), color=QUIET, buff=0.08
        )
        box = SurroundingRectangle(VGroup(cpu, job), color=GPU, buff=0.3)
        name = label(name_text, 32).next_to(box, DOWN, buff=0.25)
        down = Arrow([0, 2.5, 0], [0, 1.75, 0], color=INK, buff=0, stroke_width=8)
        self.play(GrowArrow(down), run_time=MOVE)
        self.play(Create(box), FadeIn(cpu), run_time=MOVE)
        self.play(Create(link), FadeIn(job), run_time=MOVE)
        self.play(
            job.activity.animate.set_fill(opacity=1), FadeIn(name), run_time=MOVE
        )
        self.wait(HOLD)

        self.beat("03.2")
        self.play(old.animate.fade(0.75), run_time=MOVE)
        bus_y, drop_y = -1.75, -3.1
        left, right = box.get_left()[0], box.get_right()[0]
        centers = ((-5.75, box.get_y()), (5.75, box.get_y()), (-5.4, drop_y), (0, drop_y), (5.4, drop_y))
        benefits = []
        for text, (x, y), place in zip(
            content["03.2"].screen, centers, ("left", "right", "bus", "bus", "bus"), strict=True
        ):
            claim, _, payoff = text.partition(" | ")
            rows = [(claim, INK)] + ([(payoff, WEB)] if payoff else [])
            card = BenefitCard(*rows, wrap=24).move_to([x, y, 0])
            if place == "left":
                connector = elbow([left, y, 0], card.get_right() + RIGHT * 0.2)
            elif place == "right":
                connector = elbow([right, y, 0], card.get_left() + LEFT * 0.2)
            else:
                stem = [0, name.get_bottom()[1] - 0.1, 0]
                connector = elbow(stem, [0, bus_y, 0], [x, bus_y, 0], card.get_top() + UP * 0.15)
            self.play(FadeIn(card), Create(connector), run_time=MOVE)
            benefits.append(VGroup(card, connector))
        self.wait(HOLD)

        self.beat("03.3")
        self.play(*(FadeOut(benefit) for benefit in benefits), run_time=MOVE)
        code = TranscriptCode(content["03.3"], 16, [-3.85, -2.95, 0])
        input_label = label("INPUT", 36, CPU).next_to(
            code, UP, buff=0.2, aligned_edge=LEFT
        )
        into = elbow(
            input_label.get_top() + UP * 0.1,
            [input_label.get_top()[0], box.get_y(), 0],
            [box.get_left()[0] - 0.05, box.get_y(), 0],
            color=CPU,
            tip=True,
        )
        self.play(FadeIn(code), FadeIn(input_label), run_time=MOVE)
        self.play(Create(into), run_time=MOVE)
        kinds = {
            "green": lambda text: BenefitCard((text, WEB), wrap=26),
            "white": lambda text: BenefitCard((text, INK), wrap=26),
            "rainbow": lambda title, sub: BenefitCard((title, INK), (sub, INK), wrap=26),
        }
        cards = VGroup(
            *(
                kinds[kind](*parts)
                for kind, *parts in (
                    entry.split("|") for entry in content["03.3"].screen
                )
            )
        ).arrange(DOWN, buff=0.6).move_to([5.4, -0.3, 0])
        for card in cards[:-1]:
            self.play(FadeIn(card), run_time=MOVE)
        backend = cards[-1]
        backend[0][0][0].set_color_by_gradient(WEB, CODE, GPU, MATH)
        lines = code.code.code_lines
        highlights = VGroup(
            SurroundingRectangle(VGroup(lines[2], lines[3]), color=CPU, buff=0.02, stroke_width=2),
            SurroundingRectangle(VGroup(lines[10], lines[11]), color=CPU, buff=0.02, stroke_width=2),
        )
        self.play(FadeIn(backend), Create(highlights), run_time=MOVE)
        self.play(ApplyWave(backend[0][0][0], amplitude=0.12), run_time=MOVE)
        self.wait(HOLD)

        self.beat("03.4")
        self.play(
            FadeOut(code),
            FadeOut(input_label),
            FadeOut(into),
            FadeOut(cards),
            FadeOut(highlights),
            run_time=MOVE,
        )
        two_text, one_text, speed_text = content["03.4"].screen
        counter_text, crazy_text = content["03.5"].screen
        two = VGroup(
            VGroup(
                *(GpuJob("job", width=1.5, height=0.7, size=22) for _ in range(2))
            ).arrange(RIGHT, buff=0.2),
            label(two_text, 44),
        ).arrange(DOWN, buff=0.3)
        one = VGroup(
            GpuJob("job", width=1.5, height=0.7, size=22), label(one_text, 44)
        ).arrange(DOWN, buff=0.3)
        value, word_text = speed_text.split(" ", 1)
        number = label(value, 44, WEB)
        speed = VGroup(number, label(word_text, 44, WEB)).arrange(RIGHT, buff=0.25)
        arrows = VGroup(*(Arrow(LEFT * 0.7, RIGHT * 0.7, color=INK, buff=0) for _ in range(2)))
        row = VGroup(two, arrows[0], one, arrows[1], speed).arrange(RIGHT, buff=0.5)
        row.scale_to_fit_width(min(row.width, 13.5)).move_to([0, -2.4, 0])
        self.play(FadeIn(two), run_time=MOVE)
        self.play(GrowArrow(arrows[0]), FadeIn(one), run_time=MOVE)
        self.play(GrowArrow(arrows[1]), FadeIn(speed), run_time=MOVE)
        self.wait(HOLD)

        self.beat("03.5")
        self.play(*(FadeOut(m) for m in self.mobjects if m is not speed), run_time=MOVE)
        current = counter(counter_text)
        number, word = speed
        number.set_z_index(10)
        self.play(
            Transform(number, current[2]),
            FadeOut(word, shift=DOWN * 0.5),
            FadeIn(current[0]),
            FadeIn(current[1]),
            run_time=MOVE * 1.5,
        )
        self.remove(speed)
        current = VGroup(current[0], current[1], number)
        self.add(current)
        crazy = label(crazy_text, 44).next_to(current, DOWN, buff=0.5)
        self.play(FadeIn(crazy), run_time=MOVE)
        self.wait(HOLD)
