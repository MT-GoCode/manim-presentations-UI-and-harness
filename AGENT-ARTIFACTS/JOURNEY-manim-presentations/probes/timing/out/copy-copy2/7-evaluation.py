from manim import (
    DOWN,
    LEFT,
    RIGHT,
    UP,
    Create,
    FadeIn,
    FadeOut,
    GrowFromEdge,
    LaggedStart,
    Rectangle,
    SurroundingRectangle,
    Text,
    VGroup,
    config,
)

from manim_presenters.scene import TalkSlide
from manim_presenters.transcript import Transcript

from .speedup import bump
from .visuals import (
    CODE,
    CPU,
    EVAL,
    GPU,
    HOLD,
    INK,
    MATH,
    MOVE,
    QUIET,
    TRAIN,
    WEB,
    DOCK,
    DOCK_SCALE,
    counter,
    label,
)


class Evaluation(TalkSlide):
    chapter_id = "04"

    def construct(self):
        content = Transcript.load(self.presentation_path / "transcript.json").by_id
        speed = counter("1.25x")
        crazy = label(content["03.5"].screen[1], 44).next_to(speed, DOWN, buff=0.5)
        self.add(speed, crazy)
        self.beat("04.1")
        self.wait(1 / config.frame_rate)
        title = label(content["04.1"].screen[0], 36).move_to([-1.3, 4.35, 0])
        examples = (
            ("E", 7, 5), ("D", 6, 4), ("A", 5, 4), ("H", 6, 3),
            ("B", 5, 3), ("G", 4, 4), ("C", 4, 3), ("F", 3, 3),
        )
        palette = dict(zip("EDAHBGCF", (WEB, CODE, MATH, TRAIN, GPU, EVAL, CPU, "#FF6B6B"), strict=True))
        heads = ("Example", "Context\nlength", "Continuation\nlength", "Input\nlength")
        cells = [label(h, 20, QUIET) for h in heads]
        for name, ctx, cont in examples:
            cells += [label(name, 24, palette[name]), label(str(ctx), 24), label(str(cont), 24), label(str(ctx + cont), 24)]
        table = VGroup(*cells).arrange_in_grid(rows=9, cols=4, col_alignments="lrrr", buff=(0.5, 0.2)).move_to([-4.6, 0.6, 0])
        rows_at = {name: VGroup(*table[4 * (i + 1) : 4 * (i + 2)]) for i, (name, _, _) in enumerate(examples)}
        # best-fit, longest-first placement: (row, first slot)
        place = {"E": (0, 0), "D": (1, 0), "A": (1, 10), "H": (2, 0), "B": (0, 12), "G": (2, 9), "C": (3, 0), "F": (3, 7)}
        slot, x0 = 0.38, -0.2
        ys = (2.5, 1.3, 0.1, -1.1)
        def at(row, k):
            return [x0 + slot * (k + 0.5), ys[row], 0]
        self.play(
            FadeOut(crazy),
            speed.animate.scale(DOCK_SCALE).move_to(DOCK),
            FadeIn(title),
            FadeIn(table[:4]),
            run_time=MOVE,
        )
        self.play(LaggedStart(*(FadeIn(rows_at[n]) for n, _, _ in examples), lag_ratio=0.1), run_time=MOVE * 2)
        caption = label(content["04.1"].screen[1], 26, INK).move_to([3.6, 3.25, 0])
        self.play(FadeIn(caption), run_time=MOVE)
        positions, bars = VGroup(), VGroup()
        for name, ctx, cont in examples:
            length = ctx + cont
            row, first = place[name]
            bar = Rectangle(width=slot * length, height=0.46, stroke_width=0, fill_color=palette[name], fill_opacity=0.9)
            bar.move_to(at(row, first + (length - 1) / 2))
            text = label(f"{name}: {length} tokens", 17, "#000000").move_to(bar)
            nums = VGroup(*(label(str(p), 13, QUIET).move_to([at(row, first + p)[0], ys[row] - 0.62, 0]) for p in range(length)))
            marker = SurroundingRectangle(rows_at[name], color=palette[name], buff=0.05, stroke_width=2)
            self.play(Create(marker), GrowFromEdge(bar, LEFT), FadeIn(text), run_time=MOVE / 2)
            self.play(FadeIn(nums), FadeOut(marker), run_time=MOVE / 3)
            bars.add(VGroup(bar, text))
            positions.add(nums)
        pads = VGroup()
        for row, first, count in ((1, 19, 1), (2, 17, 3), (3, 13, 7)):
            pad = Rectangle(width=slot * count, height=0.46, color=QUIET, stroke_width=2, fill_opacity=0).move_to(at(row, first + (count - 1) / 2))
            pads.add(VGroup(pad, label("pad" if count < 4 else f"{count} pad", 15, QUIET).move_to(pad)))
            pads.add(VGroup(*(label(str(p), 13, QUIET).move_to([at(row, first + p)[0], ys[row] - 0.62, 0]) for p in range(count))))
        self.play(FadeIn(pads), run_time=MOVE)
        # scored slots (the slot before each continuation token) and targets (the continuation tokens)
        scored, targets, flat = VGroup(), VGroup(), []
        for name, ctx, cont in examples:
            row, first = place[name]
            for k in range(ctx - 1, ctx + cont - 1):
                flat.append((row * 20 + first + k, row * 20 + first + k + 1))
                scored.add(Rectangle(width=slot * 0.92, height=0.1, stroke_width=0, fill_color=EVAL, fill_opacity=1).move_to([at(row, first + k)[0], ys[row] + 0.3, 0]))
                targets.add(Rectangle(width=slot * 0.92, height=0.1, stroke_width=0, fill_color=MATH, fill_opacity=1).move_to([at(row, first + k + 1)[0], ys[row] - 0.3, 0]))
        self.play(FadeIn(scored), run_time=MOVE)
        self.play(FadeIn(targets), run_time=MOVE)
        listing = VGroup(
            label("scored_slots = [" + ", ".join(str(a) for a, _ in flat[:9]) + ", …]", 22, EVAL),
            label("targets = tokens at slots [" + ", ".join(str(b) for _, b in flat[:9]) + ", …]", 22, MATH),
        ).arrange(DOWN, aligned_edge=LEFT, buff=0.2).move_to([3.7, -2.55, 0])
        legend = VGroup(
            *(
                VGroup(Rectangle(width=0.3, height=0.1, stroke_width=0, fill_color=color, fill_opacity=1), label(text, 20, color)).arrange(RIGHT, buff=0.15)
                for text, color in (("scored slot: predicts the next token", EVAL), ("target: the continuation token", MATH))
            )
        ).arrange(DOWN, aligned_edge=LEFT, buff=0.15).move_to([3.7, -3.7, 0])
        self.play(FadeIn(listing), FadeIn(legend), run_time=MOVE)
        self.wait(HOLD)

        self.beat("04.2")
        self.play(*(FadeOut(m) for m in self.mobjects if m not in (speed, title)), run_time=MOVE)
        colors = {"tokens": TRAIN, "positions": WEB, "scored_slots": EVAL, "targets": MATH}
        chunks = [
            ["hidden = model(", "    input_ids=tokens,", "    position_ids=positions,", "    use_cache=False,", ").last_hidden_state", "hidden = hidden.flatten(0, 1)[scored_slots]"],
            ["logits = lm_head(hidden)", "log_probs = logits.log_softmax(-1)", "# K target scores", "scores = log_probs.gather(1, targets[:, None]).squeeze(1)"],
            ["doc_totals.index_add_(0, slot_docs, scores)"],
        ]
        code_chunks = []
        for lines in chunks:
            rows = VGroup(
                *(
                    Text(t.lstrip(), font="Menlo", font_size=17, t2c=colors, color=QUIET if t.startswith("#") else INK)
                    for t in lines
                )
            ).arrange(DOWN, aligned_edge=LEFT, buff=0.1)
            for row, t in zip(rows, lines, strict=True):
                row.shift(RIGHT * 0.45 * ((len(t) - len(t.lstrip())) // 4))
            code_chunks.append(rows)
        code = VGroup(*code_chunks).arrange(DOWN, aligned_edge=LEFT, buff=0.4).to_edge(LEFT, buff=0.5).shift(DOWN * 0.5)
        heading = label(content["04.2"].screen[0], 34, INK).next_to(code, UP, buff=0.4, aligned_edge=LEFT)
        chips = VGroup(
            *(
                VGroup(
                    Rectangle(width=0.35, height=0.35, stroke_width=0, fill_color=color, fill_opacity=1),
                    label(f"{name}  {shape}", 26, color),
                ).arrange(RIGHT, buff=0.25)
                for (name, color), shape in zip(colors.items(), ("[4, 20]", "[4, 20]", "[29]", "[29]"), strict=True)
            )
        ).arrange(DOWN, aligned_edge=LEFT, buff=0.45).move_to([4.9, -0.3, 0])
        self.play(FadeIn(heading), FadeIn(chips), run_time=MOVE)
        for chunk in code_chunks:
            self.play(FadeIn(chunk), run_time=MOVE)
        self.wait(HOLD)

        self.beat("04.3")
        bump(self, speed, "Speedup due to eval optimizations", "1.25x", "1.44x", return_to_side=False)
        self.wait(HOLD)
