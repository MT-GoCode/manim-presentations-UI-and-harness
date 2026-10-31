from manim import DOWN, LEFT, RIGHT, UP, Dot, UpdateFromFunc


def construct(talk):
    talk.beat("accumulate")
    total = {"x": 0.0, "ticks": 0}
    dot = Dot().shift(LEFT * 4)
    talk.add(dot)

    def step(m):
        total["x"] += 0.02
        m.move_to([-4 + total["x"], 0, 0])

    talk.play(UpdateFromFunc(dot, step), run_time=1)
    ticker = Dot().shift(DOWN * 2 + LEFT * 4)

    def tick(m):  # an accumulating non-time updater: its effect depends on how many frames ran
        total["ticks"] += 1
        m.move_to([-4 + 0.01 * total["ticks"], -2, 0])

    ticker.add_updater(tick)
    talk.add(ticker)

    talk.beat("after-accumulate")  # depends on the state the closures accumulated
    talk.play(dot.animate.shift(UP * total["x"]))

    talk.beat("after-again")
    ticker.clear_updaters()
    talk.play(dot.animate.shift(RIGHT * total["ticks"] * 0.001))
