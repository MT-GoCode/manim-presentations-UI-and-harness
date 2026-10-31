import os
import sys
from pathlib import Path

from manim import FadeIn, Square


def construct(talk):
    talk.beat("probe")
    # The test names the paths no scene process may import from: the cwd the build ran in, and the live talk root.
    forbidden = [os.path.realpath(p) for p in os.environ["MPRES_TEST_FORBIDDEN"].split(os.pathsep)]
    leaked = [p for p in sys.path if p and os.path.realpath(p) in forbidden]
    assert not leaked, f"sys.path holds {leaked}"
    talk.play(FadeIn(Square(1 + 0 * len(Path(__file__).name))))
