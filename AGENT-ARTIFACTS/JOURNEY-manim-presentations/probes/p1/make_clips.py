"""Test clips for P1/P5. Each frame carries a 12-bit code in a 4x3 grid of cells:
bits 0-7 = frame index, bits 8-11 = clip id (never 0, so a real frame is never all-black).
Background is mid-gray, so a black/empty presentation is distinguishable from any real frame.
Encoding matches the plan's clip.ENCODE: libx264, yuv420p, 30 fps, threads=1, g=6, crf 18, veryfast."""

import argparse
from fractions import Fraction
from pathlib import Path

import av
import numpy as np

FPS = 30
COLS, ROWS = 4, 3
CLIPS = {  # name: (clip id, frames)
    "A": (1, 90),
    "B": (2, 90),
    "L": (3, 90),  # loop clip: frame 89 steps to frame 0 like any other step
    "S": (4, 180),  # ~6 s seek clip
}
RESOLUTIONS = {"3456x2168": (3456, 2168), "1920x1080": (1920, 1080), "480x270": (480, 270)}


def frame_rgb(w: int, h: int, code: int, i: int, n: int) -> np.ndarray:
    img = np.full((h, w, 3), 128, np.uint8)
    cw, ch = w // COLS, h // ROWS
    for bit in range(COLS * ROWS):
        r, c = divmod(bit, COLS)
        v = 255 if (code >> bit) & 1 else 0
        y0, x0 = r * ch + ch // 5, c * cw + cw // 5
        img[y0 : y0 + ch * 3 // 5, x0 : x0 + cw * 3 // 5] = v
    # a sweeping bar so consecutive frames differ in more than the code cells
    x = (i * w) // n
    img[:, x : x + max(2, w // 200), 0] = 255
    return img


def encode(path: Path, w: int, h: int, clip_id: int, n: int) -> None:
    with av.open(str(path), "w") as out:
        s = out.add_stream("libx264", rate=FPS, options={"crf": "18", "preset": "veryfast", "g": "6", "threads": "1"})
        s.width, s.height, s.pix_fmt = w, h, "yuv420p"
        s.codec_context.time_base = Fraction(1, FPS)
        for i in range(n):
            f = av.VideoFrame.from_ndarray(frame_rgb(w, h, (clip_id << 8) | i, i, n), format="rgb24")
            f.pts = i
            out.mux(s.encode(f))
        out.mux(s.encode(None))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("out", type=Path)
    ap.add_argument("--res", nargs="+", default=list(RESOLUTIONS))
    ap.add_argument("--clips", nargs="+", default=list(CLIPS))
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    for r in a.res:
        w, h = RESOLUTIONS[r]
        for name in a.clips:
            cid, n = CLIPS[name]
            p = a.out / f"{name}_{r}.mp4"
            encode(p, w, h, cid, n)
            print(p, flush=True)


if __name__ == "__main__":
    main()
