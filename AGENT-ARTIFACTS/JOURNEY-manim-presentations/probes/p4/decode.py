"""DECODE_CORES / DECODE_RAM(pixels) for the stills step: one job = open a clip with PyAV, seek to a target frame
(first, middle, last), decode it, write a PNG with Pillow. One subprocess per job, cost from os.wait4 rusage.

Sources: the real clip001 (394 frames of Mixing Deluxe content) at 3456x2168, re-encoded with the build's
clip settings (libx264 yuv420p crf 18, g=6, threads=1) at 1920x1080 and 480x270.
Usage: uv run decode.py one <clip> <frame> <png> | uv run decode.py sweep <reps>
"""

import json
import os
import statistics
import subprocess
import sys
import time
from pathlib import Path

import av

HERE = Path(__file__).parent
SIZES = ((480, 270), (1920, 1080), (3456, 2168))


def one(clip: str, frame: int, png: str) -> None:
    with av.open(clip) as c:
        s = c.streams.video[0]
        s.codec_context.thread_count = 1
        s.codec_context.thread_type = "NONE"
        step = int(1 / (s.average_rate * s.time_base))  # pts per frame
        target = frame * step
        c.seek(target, stream=s, backward=True)
        for f in c.decode(s):
            if f.pts >= target:
                assert f.pts == target, (f.pts, target)
                f.to_image().save(png)
                return
    raise AssertionError("target frame not decoded")


def source(w: int, h: int) -> Path:
    src = HERE / "src" / "clip001.mp4"
    if (w, h) == (3456, 2168):
        return src
    out = HERE / "decode_src" / f"clip001_{w}x{h}.mp4"
    if not out.exists():
        out.parent.mkdir(exist_ok=True)
        with av.open(str(src)) as inp, av.open(str(out), "w") as o:
            vs = o.add_stream("libx264", rate=30)
            vs.width, vs.height, vs.pix_fmt = w, h, "yuv420p"
            vs.codec_context.options = {"crf": "18", "g": "6", "threads": "1"}
            for f in inp.decode(video=0):
                g = f.reformat(width=w, height=h, format="yuv420p", interpolation="BICUBIC")
                g.pts, g.time_base = f.pts, f.time_base
                o.mux(vs.encode(g))
            o.mux(vs.encode())
    return out


def sweep(reps: int) -> None:
    rows = []
    for w, h in SIZES:
        clip = source(w, h)
        with av.open(str(clip)) as c:
            n = c.streams.video[0].frames
        for frame in (0, n // 2, n - 1):
            for rep in range(reps):
                png = HERE / "decode_src" / f"still_{w}_{frame}.png"
                t0 = time.monotonic()
                p = subprocess.Popen([sys.executable, __file__, "one", str(clip), str(frame), str(png)])
                _, status, ru = os.wait4(p.pid, 0)
                assert status == 0
                wall = time.monotonic() - t0
                rows.append({"w": w, "h": h, "frame": frame, "rep": rep, "cpu": ru.ru_utime + ru.ru_stime, "wall": wall,
                             "rss": ru.ru_maxrss, "load": os.getloadavg()[0]})
    base = []
    for _ in range(reps):  # interpreter + av + Pillow import floor, so the per-pixel part can be separated
        p = subprocess.Popen([sys.executable, "-c", "import av, PIL.Image"])
        _, _, ru = os.wait4(p.pid, 0)
        base.append({"cpu": ru.ru_utime + ru.ru_stime, "rss": ru.ru_maxrss})
    (HERE / "results").mkdir(exist_ok=True)
    (HERE / "results" / "decode.json").write_text(json.dumps({"rows": rows, "import_floor": base}, indent=1))
    print(f"import floor: rss median {statistics.median(b['rss'] for b in base) / 2**20:.0f} MiB, "
          f"cpu median {statistics.median(b['cpu'] for b in base):.3f} s")
    for w, h in SIZES:
        for frame in sorted({r["frame"] for r in rows if r["w"] == w}):
            sel = [r for r in rows if r["w"] == w and r["frame"] == frame]
            print(f"{w}x{h} frame {frame}: cpu median {statistics.median(r['cpu'] for r in sel):.3f} max {max(r['cpu'] for r in sel):.3f} s, "
                  f"rss median {statistics.median(r['rss'] for r in sel) / 2**20:.0f} max {max(r['rss'] for r in sel) / 2**20:.0f} MiB, "
                  f"cores (cpu/wall) median {statistics.median(r['cpu'] / r['wall'] for r in sel):.2f}, "
                  f"load {statistics.median(r['load'] for r in sel):.1f}")


if __name__ == "__main__":
    if sys.argv[1] == "one":
        one(sys.argv[2], int(sys.argv[3]), sys.argv[4])
    else:
        sweep(int(sys.argv[2]))
