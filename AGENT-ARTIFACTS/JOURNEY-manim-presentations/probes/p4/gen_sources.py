"""Synthesize a 10-minute, 57-clip talk at 3456x2168 30 fps from the real Mixing Deluxe chapter renders.

Every frame carries a 24-cell barcode (low 16 bits frame index, high 8 bits clip id) so any engine's
displayed frame can be identified by pixels. Loop clips are palindromes of real content, so their last
frame steps cleanly to frame 0.
Usage: uv run gen_sources.py <jobs>
"""

import glob
import json
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import av
import numpy as np

HERE = Path(__file__).parent
SRC = HERE / "src"
CHAPTERS = sorted(
    glob.glob(
        "/Users/minhtrinh/general-purpose/conversation-contexts/mixing-deluxe-presentation/"
        "manim-presenters/presentations/mixing-deluxe/build/*/media/videos/2168p30/*.mp4"
    )
)
W, H, FPS = 3456, 2168, 30
TOTAL = 10 * 60 * FPS
CELL, X0, Y0, BITS = 72, 48, 48, 24
LOOPS = {5: 60, 22: 90, 41: 120}  # clip id -> length; a 2 s, 3 s, 4 s loop


def stamp(rgb: np.ndarray, clip: int, i: int) -> None:
    code = (clip << 16) | i
    rgb[Y0 - 8 : Y0 + CELL + 8, X0 - 8 : X0 + BITS * CELL + 8] = 0
    for b in range(BITS):
        if code >> b & 1:
            rgb[Y0 : Y0 + CELL, X0 + b * CELL : X0 + (b + 1) * CELL] = 255


def chapter_frames(path: str, start: int, n: int):
    k = 0
    with av.open(path) as c:
        for k, f in enumerate(c.decode(video=0)):
            if k >= start:
                last = f.to_ndarray(format="rgb24")
                yield last
            if k == start + n - 1:
                return
    for _ in range(start + n - 1 - k):  # chapter shorter than the clip: hold its last frame
        yield last


def make(spec: dict) -> dict:
    clip, length = spec["clip"], spec["length"]
    if spec["loop"]:
        half = list(chapter_frames(spec["chapter"], spec["start"], length // 2 + 1))
        frames = half + half[-2:0:-1]
    else:
        frames = chapter_frames(spec["chapter"], spec["start"], length)
    n = 0
    path = SRC / f"clip{clip:03d}.mp4"
    with av.open(str(path), "w") as out:
        s = out.add_stream("libx264", rate=FPS)
        s.width, s.height, s.pix_fmt = W, H, "yuv420p"
        s.codec_context.options = {"crf": "18", "preset": "veryfast", "g": "6", "threads": "1"}
        for i, rgb in enumerate(frames):
            rgb = rgb.copy()
            stamp(rgb, clip, i)
            vf = av.VideoFrame.from_ndarray(rgb, format="rgb24")
            vf.pts = i
            out.mux(s.encode(vf))
            n += 1
        out.mux(s.encode())
    assert n == length, (clip, n, length)
    return {**spec, "path": str(path)}


def specs() -> list[dict]:
    rng = np.random.default_rng(0)
    lens = []
    for k in range(57):
        lens.append(LOOPS[k] if k in LOOPS else int(rng.choice([24, 45, 90, 150, 240, 360, 600])))
    scale = (TOTAL - sum(LOOPS.values())) / sum(v for k, v in enumerate(lens) if k not in LOOPS)
    lens = [v if k in LOOPS else max(15, round(v * scale)) for k, v in enumerate(lens)]
    lens[-1] += TOTAL - sum(lens)
    n = {p: av.open(p).streams.video[0].frames for p in CHAPTERS}
    out, ch, pos = [], 0, 0
    for k, length in enumerate(lens):
        p = CHAPTERS[ch % len(CHAPTERS)]
        need = length // 2 + 1 if k in LOOPS else length
        if pos + need > n[p]:
            ch, pos = ch + 1, 0
            p = CHAPTERS[ch % len(CHAPTERS)]
        out.append({"clip": k, "length": length, "loop": k in LOOPS, "chapter": p, "start": pos})
        pos = pos + need if pos + need < n[p] else 0
        if pos == 0:
            ch += 1
    return out


if __name__ == "__main__":
    SRC.mkdir(exist_ok=True)
    sp = specs()
    assert sum(s["length"] for s in sp) == TOTAL and len(sp) == 57
    with ProcessPoolExecutor(int(sys.argv[1])) as ex:
        done = []
        for r in ex.map(make, sp):
            done.append(r)
            print(f"clip {r['clip']:3d} {r['length']:4d} frames loop={r['loop']}", flush=True)
    (SRC / "manifest.json").write_text(json.dumps(done, indent=1))
    print("total frames", sum(s["length"] for s in done))
