"""Export re-encode sweep: every source clip, at each height x crf, as parallel threads=1 jobs.

`encode.py one <src> <dst> <height> <crf>` is one job (decode threads=1, bicubic scale, libx264 yuv420p
threads=1 at the source fps). `encode.py sweep <jobs> <reps>` runs the grid; each job is its own
process, so os.wait4 gives its exact peak RSS and CPU seconds.
"""

import json
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import av

HERE = Path(__file__).parent
HEIGHTS, CRFS = (1080, 720, 540), (20, 23, 28)


def one(src: str, dst: str, height: int, crf: int) -> None:
    with av.open(src) as inp, av.open(dst, "w", options={"movflags": "faststart"}) as out:
        vin = inp.streams.video[0]
        vin.codec_context.thread_count = 1
        vin.codec_context.thread_type = "NONE"
        w = 2 * round(height * vin.width / vin.height / 2)
        vout = out.add_stream("libx264", rate=vin.average_rate)
        vout.width, vout.height, vout.pix_fmt = w, height, "yuv420p"
        vout.codec_context.options = {"crf": str(crf), "threads": "1"}
        for f in inp.decode(vin):
            g = f.reformat(width=w, height=height, format="yuv420p", interpolation="BICUBIC")
            g.pts, g.time_base = f.pts, f.time_base
            out.mux(vout.encode(g))
        out.mux(vout.encode())


def job(src: Path, dst: Path, height: int, crf: int) -> dict:
    t0 = time.monotonic()
    p = subprocess.Popen([sys.executable, __file__, "one", str(src), str(dst), str(height), str(crf)])
    _, status, ru = os.wait4(p.pid, 0)
    wall = time.monotonic() - t0
    assert status == 0, (src, status)
    cpu = ru.ru_utime + ru.ru_stime
    return {"clip": src.name, "wall": wall, "cpu": cpu, "cores": cpu / wall, "rss": ru.ru_maxrss}  # macOS: bytes


def sweep(jobs: int, reps: int) -> None:
    clips = sorted((HERE / "src").glob("clip*.mp4"))
    # Longest first, so the pool's tail is short clips and wall time measures throughput, not one straggler.
    clips.sort(key=lambda c: -c.stat().st_size)
    results = []
    for rep in range(reps):
        for h in HEIGHTS:
            for crf in CRFS:
                d = HERE / "out" / f"h{h}_crf{crf}"
                d.mkdir(parents=True, exist_ok=True)
                # No shared lock: the costs that matter (per-job CPU seconds, peak RSS) are rusage, which load barely
                # moves. Wall time is load-dependent and is reported beside the load average.
                load0 = os.getloadavg()
                t0 = time.monotonic()
                with ThreadPoolExecutor(jobs) as ex:
                    rows = list(ex.map(lambda c: job(c, d / c.name, h, crf), clips))
                wall = time.monotonic() - t0
                load1 = os.getloadavg()
                size = sum((d / c.name).stat().st_size for c in clips)
                r = {"rep": rep, "height": h, "crf": crf, "jobs": jobs, "wall": wall, "bytes": size, "rows": rows,
                     "load_before": load0, "load_after": load1}
                results.append(r)
                print(f"rep {rep} h{h} crf{crf}: wall {wall:.1f}s, {size / 2**20:.1f} MiB, load {load0[0]:.1f}->{load1[0]:.1f}, "
                      f"max rss {max(x['rss'] for x in rows) / 2**20:.0f} MiB, "
                      f"max cores {max(x['cores'] for x in rows):.2f}", flush=True)
                (HERE / "results").mkdir(exist_ok=True)
                (HERE / "results" / "encode.json").write_text(json.dumps(results))


if __name__ == "__main__":
    if sys.argv[1] == "one":
        one(sys.argv[2], sys.argv[3], int(sys.argv[4]), int(sys.argv[5]))
    else:
        sweep(int(sys.argv[2]), int(sys.argv[3]))
