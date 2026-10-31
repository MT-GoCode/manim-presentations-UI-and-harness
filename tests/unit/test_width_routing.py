"""The build routes on headroom's tag: one job too big for 75% of free RAM refuses without --workers and runs with it.
No test forces real memory pressure on a laptop; the job size is what is raised here."""

import pytest

from manim_presentations import build


@pytest.mark.parametrize("jobs", [1, 3])
def test_ram_exceeded_refuses_without_workers(jobs):
    with pytest.raises(build.BuildError, match="pass --workers 1 to run it anyway"):
        build.width_for("render", None, jobs, 1.0, 2**60)


def test_workers_overrides_exactly():
    assert build.width_for("render", 1, 3, 1.0, 2**60) == 1
    assert build.width_for("render", 5, 3, 1.0, 2**60) == 5
