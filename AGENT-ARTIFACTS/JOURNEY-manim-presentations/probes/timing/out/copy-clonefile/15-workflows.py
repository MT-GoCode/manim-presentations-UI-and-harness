import textwrap

import numpy as np
from manim import (
    DOWN,
    LEFT,
    RIGHT,
    UP,
    Arrow,
    Circumscribe,
    Create,
    Dot,
    FadeIn,
    FadeOut,
    GrowFromEdge,
    ImageMobject,
    LaggedStart,
    Rotate,
    Square,
    VGroup,
    VMobject,
)

from manim_presenters.scene import TalkSlide
from manim_presenters.transcript import Transcript

from .visuals import (
    EVAL,
    HOLD,
    INK,
    MOVE,
    OVERHEAD,
    QUIET,
    TRAIN,
    WEB,
    CpuJob,
    GpuTimeline,
    DOCK,
    DOCK_SCALE,
    counter,
    label,
)


class OldSwarmView(VGroup):
    def __init__(self):
        self.coordinator = CpuJob(radius=0.38)
        self.coordinator.shift(
            np.array([-6.6, -0.4, 0]) - self.coordinator.shape.get_center()
        )
        self.caption = label("swarm", 24, QUIET).next_to(
            self.coordinator.shape, UP, buff=0.2
        )
        self.models, self.trains, self.evaluations = VGroup(), VGroup(), VGroup()
        self.branches, self.train_links, self.eval_links = VGroup(), VGroup(), VGroup()
        # Six representative staggered rows from Minh's original drawing; widths are schematic.
        for x, y in zip(
            (-3.7, -1.8, -2.7, -2.0, -4.1, 0.25),
            (1.8, 0.75, -0.3, -1.35, -2.4, -3.45),
            strict=True,
        ):
            cpu = CpuJob(radius=0.26)
            cpu.shift(np.array([x, y, 0]) - cpu.shape.get_center())
            train = GpuTimeline("Train", TRAIN).scale(0.7)
            train.move_to([cpu.shape.get_right()[0] + 0.3 + train.width / 2, y, 0])
            evaluate = GpuTimeline("Eval", EVAL).scale(0.7)
            evaluate.move_to(
                [train.shape.get_right()[0] + 0.35 + evaluate.width / 2, y, 0]
            )
            self.models.add(cpu)
            self.trains.add(train)
            self.evaluations.add(evaluate)
            self.branches.add(
                VMobject(color=QUIET, stroke_width=2).set_points_as_corners(
                    [
                        self.coordinator.shape.get_right(),
                        [-5.55, -0.4, 0],
                        [-5.55, y, 0],
                        cpu.shape.get_left(),
                    ]
                )
            )
            self.train_links.add(
                Arrow(
                    cpu.shape.get_right(),
                    train.shape.get_left(),
                    color=QUIET,
                    buff=0.04,
                    stroke_width=2,
                )
            )
            self.eval_links.add(
                Arrow(
                    train.shape.get_right(),
                    evaluate.shape.get_left(),
                    color=QUIET,
                    buff=0.04,
                    stroke_width=2,
                )
            )
        self.phases = tuple(
            VGroup(*(job.phases[i] for job in jobs))
            for jobs in (self.trains, self.evaluations)
            for i in range(3)
        )
        self.overhead = VGroup(*(self.phases[i] for i in (0, 2, 3, 5)))
        self.time = VGroup(
            Arrow([-4.8, 3, 0], [6.9, 3, 0], color=QUIET, buff=0),
            label("time", 24, QUIET).move_to([1.1, 3.25, 0]),
        )
        self.repeat = label("repeat 500 times", 24, QUIET).move_to([-6, -4.45, 0])
        self.legend = (
            VGroup(
                label("startup / export", 22, OVERHEAD),
                label("train", 22, TRAIN),
                label("eval", 22, EVAL),
            )
            .arrange(RIGHT, buff=0.4)
            .move_to([1.7, -4.45, 0])
        )
        super().__init__(
            self.coordinator,
            self.caption,
            self.models,
            self.branches,
            self.train_links,
            self.eval_links,
            self.trains,
            self.evaluations,
            self.time,
            self.repeat,
            self.legend,
        )


class OldSwarm(TalkSlide):
    chapter_id = "07"

    def reveal(self, phases):
        self.play(
            LaggedStart(
                *(GrowFromEdge(phase, LEFT) for phase in phases), lag_ratio=0.15
            ),
            run_time=MOVE * 2,
        )

    def construct(self):
        content = Transcript.load(self.presentation_path / "transcript.json").by_id
        self.beat("07.1")
        header = label("Current Swarm Workflow", 48).move_to([-1.3, 4.2, 0])
        speed = counter("4x")
        self.add(speed)
        asset = content["07.1"].asset
        assert asset is not None, "The original meme asset must be authored at 09.1"
        meme = (
            ImageMobject(self.presentation_path / asset)
            .set(height=6)
            .move_to([0, -0.2, 0])
        )
        self.play(
            FadeIn(meme),
            speed.animate.scale(DOCK_SCALE).move_to(DOCK),
            run_time=MOVE,
        )
        self.wait(HOLD)

        self.beat("07.2")
        view = OldSwarmView()
        self.play(FadeOut(meme), FadeIn(header), run_time=MOVE)
        self.play(
            FadeIn(view.coordinator),
            FadeIn(view.caption),
            Create(view.time),
            run_time=MOVE,
        )
        self.play(Create(view.branches), run_time=MOVE)
        self.play(
            LaggedStart(*(FadeIn(cpu) for cpu in view.models), lag_ratio=0.15),
            FadeIn(view.repeat),
            FadeIn(view.legend),
            run_time=MOVE * 2,
        )
        self.wait(HOLD)

        self.beat("07.3")
        self.play(
            Create(view.train_links),
            *(Create(job.shape) for job in view.trains),
            Rotate(
                view.coordinator.loading,
                angle=2 * np.pi,
                about_point=view.coordinator.shape.get_center(),
            ),
            run_time=MOVE,
        )
        self.reveal(view.phases[0])
        self.wait(HOLD)

        self.beat("07.4")
        self.reveal(view.phases[1])
        tokens = VGroup(
            *(
                Dot(
                    phase[0].get_left() + RIGHT * 0.08 + UP * 0.3,
                    radius=0.045,
                    color=WEB,
                )
                for phase in view.phases[1]
            )
        )
        self.add(*tokens)
        self.play(
            *(
                token.animate.move_to(phase[0].get_right() + LEFT * 0.08 + UP * 0.3)
                for token, phase in zip(tokens, view.phases[1], strict=True)
            ),
            run_time=MOVE,
        )
        self.play(FadeOut(tokens), run_time=MOVE / 2)
        self.wait(HOLD)

        self.beat("07.5")
        self.reveal(view.phases[2])
        checkpoints = VGroup(
            *(
                Square(side_length=0.12, color=INK, fill_opacity=1)
                .rotate(np.pi / 4)
                .move_to(job.shape.get_right())
                for job in view.trains
            )
        )
        self.add(*checkpoints)
        self.play(
            *(point.animate.shift(RIGHT * 0.175) for point in checkpoints),
            run_time=MOVE,
        )
        note = label("checkpoint", 20, QUIET).move_to([checkpoints[0].get_x(), 2.5, 0])
        self.play(FadeIn(note), run_time=MOVE / 2)
        self.wait(HOLD)

        self.beat("07.6")
        self.play(
            Create(view.eval_links),
            *(Create(job.shape) for job in view.evaluations),
            run_time=MOVE,
        )
        self.reveal(view.phases[3])
        self.play(
            *(
                point.animate.move_to(phase[0].get_bottom() + UP * 0.1)
                for point, phase in zip(checkpoints, view.phases[3], strict=True)
            ),
            run_time=MOVE,
        )
        self.play(FadeOut(checkpoints), FadeOut(note), run_time=MOVE / 2)
        self.wait(HOLD)

        self.beat("07.7")
        self.reveal(view.phases[4])
        self.play(
            *(
                Circumscribe(phase[0], color=EVAL, buff=0.03, stroke_width=2)
                for phase in view.phases[4]
            ),
            run_time=MOVE,
        )
        self.wait(HOLD)

        self.reveal(view.phases[5])
        self.wait(HOLD)

        self.beat("07.8")
        cpu_cost, gpu_cost, *bottom = content["07.8"].screen
        self.play(view.animate.scale(0.86).move_to([0, -0.22, 0]), run_time=MOVE)
        top = (
            label(cpu_cost, 24, OVERHEAD).move_to([-3.4, 3.5, 0]),
            label(gpu_cost, 24, OVERHEAD).move_to([2.2, 3.5, 0]),
        )
        below = [
            VGroup(*(label(line, 24, OVERHEAD) for line in textwrap.wrap(text, 24))).arrange(DOWN, buff=0.14).move_to([x, -4.4, 0])
            for text, x in zip(bottom, (-4.8, 0, 4.8), strict=True)
        ]
        self.play(*(FadeIn(item, shift=DOWN * 0.15) for item in top), run_time=MOVE)
        self.play(
            LaggedStart(*(FadeIn(item, shift=UP * 0.15) for item in below), lag_ratio=0.3),
            run_time=MOVE * 2,
        )
        self.wait(HOLD)

        self.beat("07.9")
        self.play(*(FadeOut(m) for m in self.mobjects if m is not speed), run_time=MOVE)
        self.wait(HOLD)
