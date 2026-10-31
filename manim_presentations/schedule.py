"""Where render work is cut into chunks. A pure function of the plays to render and the measured cost model, never
of the machine's width or load, so the same inputs always give the same cuts (and the same verification outcome).

Cost is in wall-seconds of one worker: rendering an animation costs render_s_per_video_s(megapixels) per second of
video, and a chunk starting at play k first pays fast_forward_cost(k) to replay the chapter up to it. A chunk never
spans two chapters or a reused stretch, so each is one contiguous play range paying exactly one fast-forward."""

from dataclasses import dataclass

# P3 (DECISIONS): the sweep could not separate 10–160 s beyond load noise; 20 s keeps the per-chunk start cost
# (process, imports, cache copy ≈ 1–1.5 s) under ~10% and still splits any beat with more than 20 s of render work.
CHUNK_COST = 20.0


def render_s_per_video_s(megapixels: float) -> float:
    """P2: tee render seconds per video second, a line through 0.135 / 0.851 at 0.52 / 7.49 MP (0.278 at 2.07)."""
    return 0.082 + 0.103 * megapixels


def fast_forward_cost(start: int) -> float:
    """P3: seconds to fast-forward the `start` plays before a chunk (least squares; the start cost is ≈ 0)."""
    return 0.047 * start


@dataclass(frozen=True)
class Chunk:
    chapter: str
    first: int  # play indices in the chapter's scene, inclusive
    last: int


def runs(plays: list[int]) -> list[list[int]]:
    """Sorted play indices split into maximal runs of consecutive ones."""
    out: list[list[int]] = []
    for n in plays:
        if out and out[-1][-1] == n - 1:
            out[-1].append(n)
        else:
            out.append([n])
    return out


def chunks(to_render: dict[str, dict[int, float]], megapixels: float) -> list[Chunk]:
    """Cut each chapter's to-render plays ({play index: run time}) at the play where a chunk's cost — its render work
    plus its fast-forward — reaches CHUNK_COST."""
    rate = render_s_per_video_s(megapixels)
    out: list[Chunk] = []
    for chapter, plays in to_render.items():
        for run in runs(sorted(plays)):
            start, work = run[0], 0.0
            for i, n in enumerate(run):
                work += rate * plays[n]
                if work + fast_forward_cost(start) >= CHUNK_COST and i < len(run) - 1:
                    out.append(Chunk(chapter, start, n))
                    start, work = run[i + 1], 0.0
            out.append(Chunk(chapter, start, run[-1]))
    return out
