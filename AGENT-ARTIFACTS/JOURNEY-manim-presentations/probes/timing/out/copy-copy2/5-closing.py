import textwrap

from manim import (
    DOWN,
    LEFT,
    RIGHT,
    FadeIn,
    FadeOut,
    Rectangle,
    ReplacementTransform,
    UL,
    Transform,
    VGroup,
    config,
)

from manim_presenters.scene import TalkSlide
from manim_presenters.transcript import Transcript

from .speedup import SWARM_VALUE, final_zoom_parts
from .visuals import CODE, DOCK, DOCK_SCALE, HOLD, INK, MATH, MOVE, TRAIN, WEB, counter, label


class Outcomes(TalkSlide):
    chapter_id = "09"

    def construct(self):
        content = Transcript.load(self.presentation_path / "transcript.json").by_id
        wide, head, caption, number = final_zoom_parts(*content["08.14"].screen)
        self.add(wide, head, caption, number)
        title, *_ = content["09.1"].screen
        heading = VGroup(
            *(label(line, 38, INK) for line in textwrap.wrap(title, 40))
        ).arrange(DOWN, aligned_edge=LEFT, buff=0.1).move_to([-1.3, 3.9, 0])
        palette = (WEB, CODE, TRAIN, MATH)
        cards = VGroup()
        for beat, color in zip(("09.1", "09.2", "09.3", "09.4"), palette, strict=True):
            headline, sub, *tag = content[beat].screen[1:] if beat == "09.1" else content[beat].screen
            words = VGroup(
                VGroup(*(label(line, 26, color) for line in textwrap.wrap(headline, 28))).arrange(DOWN, aligned_edge=LEFT, buff=0.08),
                VGroup(*(label(line, 20, "#D0D4DC") for line in textwrap.wrap(sub, 44))).arrange(DOWN, aligned_edge=LEFT, buff=0.06),
            ).arrange(DOWN, aligned_edge=LEFT, buff=0.15)
            if tag:
                words.add(label(tag[0], 22, MATH))
                words.arrange(DOWN, aligned_edge=LEFT, buff=0.15)
            shell = Rectangle(width=7.0, height=3.4, color=color, stroke_width=2, fill_color=color, fill_opacity=0.08)
            words.move_to(shell.get_corner(UL) + RIGHT * 0.3 + DOWN * 0.3, aligned_edge=UL)
            cards.add(VGroup(shell, words))
        for card, (x, y) in zip(cards, ((-3.8, 1.5), (3.8, 1.5), (-3.8, -1.95), (3.8, -1.95)), strict=True):
            card.move_to([x, y, 0])
        rows = cards

        self.beat("09.1")
        self.wait(1 / config.frame_rate)
        target = counter(SWARM_VALUE)
        self.play(
            FadeOut(caption),
            Transform(wide, target[0]),
            Transform(head, target[1]),
            ReplacementTransform(number, target[2]),
            run_time=MOVE,
        )
        speed = VGroup(wide, head, target[2])
        self.remove(wide, head, target[2])
        self.add(speed)
        self.play(
            speed.animate.scale(DOCK_SCALE).move_to(DOCK),
            FadeIn(heading),
            FadeIn(rows[0], scale=0.95),
            run_time=MOVE * 1.5,
        )
        self.wait(HOLD)
        for i, beat in enumerate(("09.2", "09.3", "09.4"), start=1):
            self.beat(beat)
            self.play(FadeIn(rows[i], scale=0.95), run_time=MOVE)
            self.wait(HOLD)


class Questions(TalkSlide):
    chapter_id = "10"

    def construct(self):
        self.beat("10.1")
        self.wait(1 / config.frame_rate)
        mark = label("?", 260, INK)
        self.play(FadeIn(mark, scale=0.8), run_time=MOVE)
        self.remove(*self.mobjects)
        self.add(mark)
        self.wait(HOLD)
