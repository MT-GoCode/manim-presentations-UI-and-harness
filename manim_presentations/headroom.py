"""How many jobs fit: up to 75% of the CPU and RAM free when a phase starts (Minh's rule), from measured per-job peaks.
Callers route on the tag: Width(n), or RamExceeded when one job alone does not fit in 75% of free RAM."""

import os
from dataclasses import dataclass
from math import floor

import psutil

FRACTION = 0.75  # Minh: parallel builds use up to 75% of available CPU and RAM by default
MIN_SAMPLE_WINDOW = None  # set from P5 below


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
    return Headroom(idle_cores=(os.cpu_count() or 1) - busy, available_ram=psutil.virtual_memory().available)


def width(h: Headroom, per_job_cores: float, per_job_ram: int, jobs: int) -> Width | RamExceeded:
    if FRACTION * h.available_ram < per_job_ram:
        return RamExceeded(per_job=per_job_ram, available=h.available_ram)
    by_cpu = floor(FRACTION * h.idle_cores / per_job_cores)
    by_ram = floor(FRACTION * h.available_ram / per_job_ram)
    return Width(max(1, min(by_cpu, by_ram, jobs)))


def ram_only(available: int, per_job_ram: int) -> Width | RamExceeded:
    """One job: only RAM can refuse it, and RAM is read instantly, so no core count is ever sampled for it."""
    return Width(1) if FRACTION * available >= per_job_ram else RamExceeded(per_job=per_job_ram, available=available)
