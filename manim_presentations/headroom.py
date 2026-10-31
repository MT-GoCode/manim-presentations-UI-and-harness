"""How many jobs fit: up to 75% of the CPU and RAM free when a phase starts (Minh's rule), from measured per-job peaks.
Callers route on the tag: Width(n), or RamExceeded when one job alone does not fit in 75% of free RAM."""

from collections.abc import Callable
from dataclasses import dataclass
from math import floor

import psutil

FRACTION = 0.75  # Minh: parallel builds use up to 75% of available CPU and RAM by default
# Seconds. On macOS psutil's per-CPU idle over a shorter window reads biased low, not just noisy (an idle 18-core
# M-series Mac: 1.0 idle cores at 0.05 s, 8.7 at 0.5 s, 17.2-17.7 from 1.0 s on, spread 0.44); the shortest window
# that reads true. Every sample with more than one job costs this once.
MIN_SAMPLE_WINDOW = 1.0


@dataclass(frozen=True)
class Headroom:
    idle_cores: float
    available_ram: int


@dataclass(frozen=True)
class Width:
    n: int


@dataclass(frozen=True)
class RamExceeded:
    per_job: int
    available: int


def sample(window_s: float) -> Headroom:
    """Idle cores over the window and available RAM at its end. Take it while the caller is idle and has no live
    children, so no own-load term is needed."""
    per_cpu = psutil.cpu_times_percent(interval=window_s, percpu=True)
    busy = sum(100.0 - c.idle for c in per_cpu) / 100.0
    return Headroom(idle_cores=len(per_cpu) - busy, available_ram=psutil.virtual_memory().available)


def width(h: Headroom, per_job_cores: float, per_job_ram: int, jobs: int) -> Width | RamExceeded:
    if FRACTION * h.available_ram < per_job_ram:
        return RamExceeded(per_job=per_job_ram, available=h.available_ram)
    by_cpu = floor(FRACTION * h.idle_cores / per_job_cores)
    by_ram = floor(FRACTION * h.available_ram / per_job_ram)
    return Width(max(1, min(by_cpu, by_ram, jobs)))


def ram_only(available: int, per_job_ram: int) -> Width | RamExceeded:
    """One job: only RAM can refuse it, and RAM is read instantly, so no core count is ever sampled for it."""
    return Width(1) if FRACTION * available >= per_job_ram else RamExceeded(per_job=per_job_ram, available=available)


class TooBig(Exception):
    """One job alone needs more than 75% of the free RAM; only an explicit --workers runs it anyway."""


def choose(
    phase: str, workers: int | None, jobs: int, cores: float, ram: int, say: Callable[[str], None]
) -> tuple[int, str]:
    """`--workers N` exactly, or 75% of free headroom for jobs of the given measured size, printed with its inputs (a
    human line and one exact machine line for tests to parse). Returns (width, what it was chosen from)."""
    estimate = f"{ram / 2**30:.2f} GB per job est"
    if workers is not None:
        say(f"{phase} width: {workers} (--workers) · {estimate}")
        return workers, "--workers"
    if jobs == 1:
        tagged, label = ram_only(psutil.virtual_memory().available, ram), "1 job"
    else:
        h = sample(MIN_SAMPLE_WINDOW)
        tagged = width(h, cores, ram, jobs)
        label = f"idle {h.idle_cores:.1f} cores, {h.available_ram / 2**30:.0f} GB free"
        say(
            f"machine: phase={phase} idle_cores={h.idle_cores!r} available_ram={h.available_ram} "
            f"per_job_cores={cores!r} per_job_ram={ram} jobs={jobs}"
        )
    match tagged:
        case Width(n):
            say(f"{phase} width: {n} ({label}) · {estimate}")
            return n, label
        case RamExceeded(per_job, available):
            raise TooBig(
                f"one {phase} job needs {per_job / 2**30:.1f} GB, more than 75% of the "
                f"{available / 2**30:.1f} GB free; pass --workers 1 to run it anyway"
            )
