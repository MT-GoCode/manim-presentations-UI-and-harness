"""The build routes on headroom's tag: one job too big for 75% of free RAM refuses without --workers and runs with it.
No test forces real memory pressure on a laptop; the job size is what is raised here."""

import pytest

from manim_presentations import build


@pytest.mark.parametrize("jobs", [1, 3])
def test_ram_exceeded_refuses_without_workers(monkeypatch, jobs):
    monkeypatch.setattr(build, "PASS1_RAM", 2**60)
    with pytest.raises(build.BuildError, match="pass --workers 1 to run it anyway"):
        build.pass1_width(None, jobs)


def test_workers_overrides_exactly(monkeypatch):
    monkeypatch.setattr(build, "PASS1_RAM", 2**60)
    assert build.pass1_width(1, 3) == 1
    assert build.pass1_width(5, 3) == 5
