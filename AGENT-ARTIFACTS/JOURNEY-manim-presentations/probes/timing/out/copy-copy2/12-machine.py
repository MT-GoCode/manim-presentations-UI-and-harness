import textwrap

from manim import (
    DOWN,
    LEFT,
    RIGHT,
    UP,
    Arrow,
    Code,
    Create,
    Dot,
    FadeIn,
    FadeOut,
    GrowFromEdge,
    Indicate,
    LaggedStart,
    Rectangle,
    SurroundingRectangle,
    Transform,
    VGroup,
)

from manim_presenters.scene import TalkSlide
from manim_presenters.transcript import Transcript

from .speedup import final_zoom_parts
from .visuals import (
    CODE,
    CPU,
    DOCK_SCALE,
    EVAL,
    GPU,
    HOLD,
    INK,
    MATH,
    MOVE,
    OVERHEAD,
    QUIET,
    TRAIN,
    WEB,
    CpuJob,
    docked,
    elbow,
    label,
)

TITLE = "[In Progress] A well-oiled swarm machine"


def title_bar():
    return label(TITLE, 40).move_to([-1.3, 4.45, 0])


def caption(text, color=INK):
    lines = textwrap.wrap(text, 62)
    return VGroup(*(label(line, 28, color) for line in lines)).arrange(DOWN, buff=0.1).move_to([-1.3, 3.4, 0])


def reset(scene, *keep):
    scene.play(*(FadeOut(m) for m in scene.mobjects if m not in keep), run_time=MOVE)


def bar(width, height, color, words=None, size=20, opacity=0.9):
    box = Rectangle(width=width, height=height, stroke_width=0, fill_color=color, fill_opacity=opacity)
    if words is None:
        return box
    return VGroup(box, label(words, size, "#000000").move_to(box))


def code_box(text, size=16):
    return Code(
        code_string=text,
        language="python",
        formatter_style="monokai",
        add_line_numbers=False,
        background="rectangle",
        background_config={"fill_color": "#000000", "stroke_color": GPU, "stroke_width": 2},
        paragraph_config={"font_size": size},
    )


class Machine(TalkSlide):
    chapter_id = "08"

    def construct(self):
        content = Transcript.load(self.presentation_path / "transcript.json").by_id
        speed = docked("4x")
        title = title_bar()
        self.add(speed)
        self.workflow(speed, title)
        self.features(speed, title, content)
        self.status(speed, title, content)

    def workflow(self, speed, title):
        slots = [[-3.7, 1.55 - 0.62 * i, 0] for i in range(6)]
        stack_x, rows = 0.6, [3.1, 1.85, 0.6, -0.65]

        def new_task(i):
            return Rectangle(width=1.5, height=0.4, color=WEB, fill_color=WEB, fill_opacity=0.35, stroke_width=2).move_to(slots[i])

        def worker(y):
            box = Rectangle(width=3.0, height=0.95, color=GPU, fill_color=GPU, fill_opacity=0.12, stroke_width=3)
            words = VGroup(label("Warm worker", 24), label("reused caches", 17, QUIET)).arrange(DOWN, buff=0.06)
            return VGroup(box, words).move_to([stack_x, y, 0])

        def cycle(tasks, workers):
            """One pass: each worker takes the next queued task; the queue refills, so the first frame returns."""
            for w in workers:
                task = tasks.pop(0)
                self.play(task.animate.move_to(w.get_center()).scale(0.6), run_time=MOVE / 2)
                result = Rectangle(width=1.4, height=0.35, color=EVAL, fill_color=EVAL, fill_opacity=0.85, stroke_width=0).move_to([5.3, 0.2, 0])
                self.play(Indicate(w[0], color=EVAL, scale_factor=1.04), FadeOut(task), FadeIn(result), run_time=MOVE / 2)
                fresh = new_task(len(slots) - 1)
                self.play(
                    *(t.animate.move_to(slots[i]) for i, t in enumerate(tasks)),
                    FadeIn(fresh),
                    FadeOut(result),
                    run_time=MOVE / 2,
                )
                tasks.append(fresh)

        self.beat("08.1")
        cpu = CpuJob(radius=0.45).move_to([-6.4, 0.2, 0])
        cpu.shift([0, 0.2 - cpu.shape.get_y(), 0])
        queue = Rectangle(width=2.0, height=4.0, color=QUIET).move_to([-3.7, 0.2, 0])
        queue_name = label("Task queue", 26, QUIET).next_to(queue, UP, buff=0.2)
        tasks = [new_task(i) for i in range(len(slots))]
        workers = [worker(y) for y in rows[1:]]
        stack_name = label("Warm, cache-reuse workers", 24, QUIET).move_to([stack_x, -1.7, 0])
        done = Rectangle(width=3.4, height=3.0, color=QUIET).move_to([5.3, 0.2, 0])
        done_name = VGroup(label("Finished swarm", 26), label("train checkpoints + evals", 22, QUIET)).arrange(DOWN, buff=0.08).next_to(done, UP, buff=0.2)
        arrows = VGroup(
            Arrow(cpu.shape.get_right(), queue.get_left(), color=QUIET, buff=0.1),
            Arrow(queue.get_right(), [stack_x - 1.5, 0.2, 0], color=QUIET, buff=0.1),
            Arrow([stack_x + 1.5, 0.2, 0], done.get_left(), color=QUIET, buff=0.1),
        )
        self.play(FadeIn(title), FadeIn(cpu), run_time=MOVE)
        self.play(Create(queue), FadeIn(queue_name), Create(arrows[0]), run_time=MOVE)
        self.play(LaggedStart(*(FadeIn(t, shift=RIGHT * 0.2) for t in tasks), lag_ratio=0.15), run_time=MOVE * 2)
        self.play(LaggedStart(*(FadeIn(w) for w in workers), lag_ratio=0.25), FadeIn(stack_name), Create(arrows[1]), run_time=MOVE * 2)
        self.play(Create(arrows[2]), Create(done), FadeIn(done_name), run_time=MOVE)
        self.wait(HOLD)

        self.beat("08.2", loop=True)
        cycle(tasks, workers)

        self.beat("08.3")
        extra = worker(rows[0])
        plus = label("+ worker", 24, WEB).next_to(extra, RIGHT, buff=0.3)
        self.play(FadeIn(extra, scale=0.8), FadeIn(plus), run_time=MOVE)
        self.play(FadeOut(plus), run_time=MOVE / 2)
        workers = [extra, *workers]

        self.beat("08.4", loop=True)
        cycle(tasks, workers)

        self.beat("08.5")
        victims = workers[:2]
        tags = [label("CRASHED", 24, OVERHEAD).move_to(w) for w in victims]
        self.play(
            *(w[0].animate.set_color(QUIET).set_fill(QUIET, opacity=0.08) for w in victims),
            *(w[1].animate.set_opacity(0.1) for w in victims),
            *(FadeIn(t) for t in tags),
            run_time=MOVE,
        )
        self.wait(HOLD)
        self.play(*(FadeOut(w) for w in victims), *(FadeOut(t) for t in tags), run_time=MOVE)
        workers = workers[2:]

        self.beat("08.6", loop=True)
        cycle(tasks, workers)

    def features(self, speed, title, content):
        self.beat("08.7")
        reset(self, speed, title)
        head = caption(content["08.7"].screen[0])
        gpu_lane = label("GPU", 30, GPU).move_to([-6.7, 0.9, 0])
        cpu_lane = label("CPU threads", 26, CPU).move_to([-6.1, -1.0, 0])
        trains = VGroup(*(bar(3.2, 0.9, TRAIN, f"candidate {k + 1}", 24).move_to([-3.7 + 3.3 * k, 0.9, 0]) for k in range(3)))
        exports = VGroup(*(bar(2.4, 0.9, CPU, "export + upload", 20).move_to([-0.9 + 3.3 * k, -1.0, 0]) for k in range(3)))
        self.play(FadeIn(head), FadeIn(gpu_lane), FadeIn(cpu_lane), run_time=MOVE)
        for k in range(3):
            moves = [GrowFromEdge(trains[k], LEFT)]
            if k:
                moves.append(GrowFromEdge(exports[k - 1], LEFT))
            self.play(*moves, run_time=MOVE)
        self.play(GrowFromEdge(exports[2], LEFT), run_time=MOVE)
        self.wait(HOLD)

        self.beat("08.8")
        reset(self, speed, title)
        head = caption(content["08.8"].screen[0])
        names = ("tokenizer", "compiled model", "dataloader")
        colors = (WEB, CODE, MATH)
        widths = (1.7, 2.4, 1.7)
        rows, ys = [], (1.4, 0.1, -1.2)
        for r, y in enumerate(ys):
            x, row = -5.0, VGroup(label(f"candidate {r + 1}", 24, QUIET).move_to([-6.5, y, 0]))
            for name, color, width in zip(names, colors, widths, strict=True):
                w = width if r == 0 else 0.2
                seg = bar(w, 0.8, color, name if r == 0 else None, 18, 0.9 if r == 0 else 0.35).move_to([x + w / 2, y, 0])
                row.add(seg)
                x += w
            row.add(bar(3.4, 0.8, TRAIN, "train", 24).move_to([x + 1.7, y, 0]))
            rows.append((row, x + 3.4))
        self.play(FadeIn(head), run_time=MOVE)
        for row, _ in rows[:1]:
            self.play(LaggedStart(*(GrowFromEdge(p, LEFT) for p in row), lag_ratio=0.3), run_time=MOVE * 2)
        cached = label("cached", 22, WEB).move_to([-4.6, -0.55, 0])
        self.play(*(LaggedStart(*(GrowFromEdge(p, LEFT) for p in row), lag_ratio=0.2) for row, _ in rows[1:]), FadeIn(cached), run_time=MOVE * 2)
        saved = VGroup(Arrow([rows[2][1], -2.2, 0], [rows[0][1], -2.2, 0], color=WEB, buff=0), label("time saved", 26, WEB).move_to([(rows[0][1] + rows[2][1]) / 2, -2.65, 0]))
        self.play(FadeIn(saved), run_time=MOVE)
        self.wait(HOLD)

        self.beat("08.9")
        reset(self, speed, title)
        head = caption(content["08.9"].screen[0])
        head_cpu = CpuJob(radius=0.45).move_to([-6.2, 0.1, 0])
        head_cpu.shift([0, 0.1 - head_cpu.shape.get_y(), 0])
        plans = (("full train", 0.0, TRAIN), ("resume train", 0.6, TRAIN), ("new eval only", 1.0, EVAL))
        parts, ys = [], (1.5, 0.1, -1.3)
        for (text, done_fraction, color), y in zip(plans, ys, strict=True):
            left = [-3.8, y, 0]
            frame = Rectangle(width=6, height=0.7, color=QUIET, stroke_width=2).move_to([-0.8, y, 0])
            pieces = VGroup(frame)
            if done_fraction:
                finished = bar(6 * done_fraction, 0.7, QUIET, opacity=0.5).move_to([-3.8 + 3 * done_fraction, y, 0])
                pieces.add(finished)
            todo_width = 6 * (1 - done_fraction) if done_fraction < 1 else 0.7
            start = -3.8 + 6 * done_fraction if done_fraction < 1 else 2.2 - todo_width
            todo = bar(todo_width, 0.7, color).move_to([start + todo_width / 2, y, 0])
            pieces.add(todo)
            link = elbow(head_cpu.shape.get_right(), [-4.6, 0.1, 0], [-4.6, y, 0], [left[0] - 0.05, y, 0], tip=True)
            tag = label(text, 32, color).move_to([5.0, y, 0])
            parts.append((link, pieces, tag))
        self.play(FadeIn(head), FadeIn(head_cpu), run_time=MOVE)
        for link, pieces, tag in parts:
            self.play(Create(link), FadeIn(pieces), FadeIn(tag), run_time=MOVE)
        self.wait(HOLD)

        self.beat("08.10")
        reset(self, speed, title)
        first, rainbow, second, third = content["08.10"].screen[0].split("|")
        lead = VGroup(label(first, 28), label(rainbow, 28).set_color_by_gradient(WEB, CODE, GPU, MATH)).arrange(RIGHT, buff=0.15)
        head = VGroup(lead, label(second, 28), label(third, 28)).arrange(DOWN, buff=0.1).move_to([-1.3, 3.3, 0])
        main = code_box(content["08.10"].code, 15).move_to([-3.2, 0.7, 0])
        input_label = label("INPUT", 34, CPU).next_to(main, UP, buff=0.2, aligned_edge=LEFT)
        line = main.code_lines[5]
        hit = SurroundingRectangle(line, color=CPU, buff=0.03, stroke_width=2)
        alternative = code_box(content["08.10"].screen[1], 15).move_to([-3.2, -2.5, 0])
        arrow = elbow(hit.get_right(), [0.2, hit.get_y(), 0], [0.2, alternative.get_y(), 0], alternative.get_right() + RIGHT * 0.05, color=CPU, tip=True)
        ads = VGroup(
            *(
                VGroup(*(label(line, size, color) for line in textwrap.wrap(text, 30))).arrange(DOWN, aligned_edge=LEFT, buff=0.08)
                for text, size, color in zip(content["08.10"].screen[2:], (30, 30), (WEB, CODE), strict=True)
            )
        ).arrange(DOWN, aligned_edge=LEFT, buff=0.45).move_to([4.7, -0.3, 0])
        self.play(FadeIn(head), FadeIn(main), FadeIn(input_label), run_time=MOVE)
        self.play(Create(hit), run_time=MOVE)
        self.play(FadeIn(alternative), Create(arrow), run_time=MOVE)
        self.play(LaggedStart(*(FadeIn(item, shift=LEFT * 0.2) for item in ads), lag_ratio=0.3), run_time=MOVE * 2)
        self.wait(HOLD)

        for beat in ("08.11", "08.12"):
            self.beat(beat)
            reset(self, speed, title)
            first, rainbow = content[beat].screen
            head = VGroup(
                label(first, 32),
                label(rainbow, 32).set_color_by_gradient(WEB, CODE, GPU, MATH),
            ).arrange(RIGHT, buff=0.2).move_to([-1.3, 3.5, 0])
            lap = code_box(content[beat].code, 17).move_to([-1.3, -0.5, 0])
            self.play(FadeIn(head), run_time=MOVE)
            self.play(FadeIn(lap), run_time=MOVE * 2)
            self.wait(HOLD)

    def status(self, speed, title, content):
        self.beat("08.13")
        reset(self, speed, title)
        def column(header, color, items, x):
            rows = VGroup(*(label(header, 36, color),))
            for text in items:
                text, _, tag = text.partition("|")
                words = label(text, 26)
                row = VGroup(Dot(radius=0.08, color=color), words)
                if tag:
                    row.add(label(tag, 22, MATH))
                rows.add(row.arrange(RIGHT, buff=0.25))
            return rows.arrange(DOWN, aligned_edge=LEFT, buff=0.5).move_to([x, 0, 0]).align_to([0, 2.3, 0], UP)
        left = column("Working today", WEB, content["08.13"].screen[0].split(";"), -3.6)
        right = column("Still to do", CPU, content["08.13"].screen[1].split(";"), 3.0)
        self.play(FadeIn(left[0]), FadeIn(right[0]), run_time=MOVE)
        self.play(LaggedStart(*(FadeIn(r, shift=RIGHT * 0.2) for r in left[1:]), lag_ratio=0.3), run_time=MOVE * 2)
        self.play(LaggedStart(*(FadeIn(r, shift=RIGHT * 0.2) for r in right[1:]), lag_ratio=0.3), run_time=MOVE * 2)
        self.wait(HOLD)

        self.beat("08.14")
        reset(self, speed)
        self.play(speed.animate.scale(1 / DOCK_SCALE).move_to([0, 0, 0]), run_time=MOVE)
        box, head, number = speed
        wide, wide_head, top, value = final_zoom_parts(*content["08.14"].screen)
        self.play(
            Transform(box, wide),
            Transform(head, wide_head),
            FadeOut(number),
            FadeIn(value),
            FadeIn(top),
            run_time=MOVE,
        )
        self.wait(HOLD)
