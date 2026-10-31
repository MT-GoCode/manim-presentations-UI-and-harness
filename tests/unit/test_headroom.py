import pytest

from manim_presentations.headroom import Headroom, RamExceeded, Width, ram_only, sample, width

GB = 2**30


@pytest.mark.parametrize(
    "h,cores,ram,jobs,want",
    [
        (Headroom(16.0, 100 * GB), 1.0, 1 * GB, 50, Width(12)),  # CPU-bound: floor(.75·16/1)
        (Headroom(16.0, 8 * GB), 1.0, 2 * GB, 50, Width(3)),  # RAM-bound: floor(.75·8/2)
        (Headroom(16.0, 100 * GB), 1.0, 1 * GB, 5, Width(5)),  # job-bound
        (Headroom(0.5, 100 * GB), 1.0, 1 * GB, 50, Width(1)),  # never below one
        (Headroom(10.0, 100 * GB), 1.1, 1 * GB, 50, Width(6)),  # floor(7.5/1.1) = 6
        (Headroom(16.0, 4 * GB), 1.0, 4 * GB, 50, RamExceeded(4 * GB, 4 * GB)),  # one job needs more than 75%
    ],
)
def test_width(h, cores, ram, jobs, want):
    assert width(h, cores, ram, jobs) == want


def test_ram_only():
    assert ram_only(4 * GB, 3 * GB) == Width(1)
    assert ram_only(4 * GB, 3 * GB + 1) == RamExceeded(3 * GB + 1, 4 * GB)


def test_sample_reads_idle_cores_and_available_ram():
    import os

    import psutil

    h = sample(0.2)
    assert 0 <= h.idle_cores <= os.cpu_count()
    assert h.available_ram < psutil.virtual_memory().total  # available, never total
