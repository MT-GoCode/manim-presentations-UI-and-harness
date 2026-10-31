"""Every frame carries its identity: 12 cells along the top edge, white for 1, read back by the export tests.
The code is beat number << 8 | a counter that each play moves linearly by one per frame (a loop's counter wraps at
its period, so the loop closes)."""

from manim import UP, WHITE, Rectangle, ValueTracker, VGroup, config, linear

BITS = 12


class FrameCode:
    def __init__(self, talk):
        self.talk, self.beat, self.period = talk, 0, 256
        self.counter = ValueTracker(0)
        self.cells = VGroup(*[Rectangle(width=14.2 / BITS, height=0.8, stroke_width=0) for _ in range(BITS)])
        self.cells.arrange(buff=0).to_edge(UP, buff=0.05)
        self.cells.add_updater(lambda _: self.paint())
        talk.add(self.cells)

    def start(self, beat, period=256):
        self.beat, self.period = beat, period
        self.counter.set_value(0)
        self.paint()

    def play(self, animation, run_time):
        end = self.counter.get_value() + run_time * config.frame_rate  # talk.toml's, as the build set it
        self.talk.play(animation, self.counter.animate(rate_func=linear).set_value(end), run_time=run_time)

    def paint(self):
        code = self.beat << 8 | round(self.counter.get_value()) % self.period
        for b, cell in enumerate(self.cells):
            cell.set_fill(WHITE, opacity=code >> b & 1)
