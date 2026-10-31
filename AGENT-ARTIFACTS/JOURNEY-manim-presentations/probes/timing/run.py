"""Throwaway orchestrator for P0, P2, P3 and P7(c). Run on an idle machine; prints progress, writes results.json.

usage: python run.py STAGE   (STAGE: p2 | p3ff | p0 | sweep | d12 | copy | all)
"""
import json
import os
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import psutil

HERE = Path(__file__).parent.resolve()
PY = "/Users/minhtrinh/code/explainers/.venv/bin/python"
OUT = HERE / "out"
RES = HERE / "results.json"
R = json.loads(RES.read_text()) if RES.exists() else {}
CHAPTERS = 10
WIDTH = int(0.75 * os.cpu_count())  # 75% of cores, the PLAN's default rule on an idle machine


def save():
    RES.write_text(json.dumps(R, indent=1))


def synth(*args, w=3456, h=2168):
    env = {**os.environ, "PYTHONHASHSEED": "0", "P_W": str(w), "P_H": str(h)}
    p = subprocess.run([PY, str(HERE / "synth.py"), *map(str, args)], env=env, capture_output=True, text=True)
    if p.returncode:
        raise RuntimeError(p.stderr[-2000:])
    return json.loads(p.stdout.strip().splitlines()[-1])


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


def p2():
    """Plain and tee render of one chapter at three sizes: render_s_per_video_s, cores, RSS, tee overhead."""
    synth("pass1", 0, OUT / "p2", w=480, h=270)  # warm this chapter's tex/text cache
    for w, h in ((960, 540), (1920, 1080), (3456, 2168)):
        p1 = synth("pass1", 0, OUT / "p2", w=w, h=h)
        runs = []
        for rep in range(2):
            plain = synth("plain", 0, OUT / "p2", w=w, h=h)
            tee = synth("tee", 0, OUT / "p2", 0, -1, w=w, h=h)
            runs.append({"plain": plain, "tee": tee})
            log(f"p2 {w}x{h} rep {rep}: plain {plain['seconds']:.1f}s cpu {plain['cpu_s']:.1f}s rss {plain['maxrss']/2**20:.0f}MB"
                f" · tee {tee['seconds']:.1f}s rss {tee['maxrss']/2**20:.0f}MB · pass1 {p1['seconds']:.1f}s rss {p1['maxrss']/2**20:.0f}MB")
        R.setdefault("p2", {})[f"{w}x{h}"] = {"pass1": p1, "runs": runs}
        save()


def p3ff():
    """Fast-forward cost by starting play: render exactly play k (from=k, upto=k) minus rendering play k alone."""
    out = {}
    for k in (0, 7, 14, 21, 28, 35, 41):
        reps = [synth("tee", 0, OUT / "p3ff", k, k)["seconds"] for _ in range(2)]
        out[k] = reps
        log(f"p3ff play {k}: {reps}")
    R["p3ff"] = out
    save()


def p0():
    """Pass-1 cost: one chapter cold and warm, then all chapters in parallel (warm), per-chapter RSS and CPU."""
    cold = synth("pass1", 9, OUT / "p0cold")
    warm = synth("pass1", 9, OUT / "p0cold")
    for c in range(CHAPTERS):  # warm every chapter's cache once
        synth("pass1", c, OUT / "p0")
    t = time.monotonic()
    with ThreadPoolExecutor(CHAPTERS) as ex:
        par = list(ex.map(lambda c: synth("pass1", c, OUT / "p0"), range(CHAPTERS)))
    wall = time.monotonic() - t
    R["p0"] = {"cold_one": cold, "warm_one": warm, "parallel_wall": wall, "parallel": par}
    log(f"p0 pass1 one chapter cold {cold['seconds']:.1f}s warm {warm['seconds']:.1f}s; all {CHAPTERS} parallel {wall:.1f}s;"
        f" max rss {max(p['maxrss'] for p in par)/2**20:.0f}MB")
    save()


def chunks_for(durations, chunk_cost, rate, ff):
    """Cut plays into contiguous chunks at the play nearest every chunk_cost of cost(anim) = rate·d + ff(start)."""
    out, start, acc = [], 0, 0.0
    for i, d in enumerate(durations):
        acc += rate * d
        if acc + ff(start) >= chunk_cost and i < len(durations) - 1:
            out.append((start, i))
            start, acc = i + 1, 0.0
    out.append((start, len(durations) - 1))
    return out


def build_wall(jobs, width):
    for c in range(CHAPTERS):  # warm each chapter's cache where sweep chunks copy it from
        synth("pass1", c, OUT / "sweep")
    t = time.monotonic()
    with ThreadPoolExecutor(width) as ex:
        list(ex.map(lambda j: synth("tee", j[0], OUT / "sweep", j[1], j[2]), jobs))
    return time.monotonic() - t


def model():
    """rate = render seconds per video second (tee, 3456×2168); ff(k) = seconds to fast-forward k plays, fitted from
    (tee from=k upto=k) − rate·d[k] − the k=0 fixed start cost, least squares through 0."""
    d = R["p0"]["parallel"][0]["durations"]
    hi = R["p2"]["3456x2168"]["runs"]
    rate = min(r["tee"]["seconds"] for r in hi) / sum(d)
    ff = {int(k): min(v) for k, v in R["p3ff"].items()}
    fixed = ff[0] - rate * d[0]
    pts = [(k, ff[k] - rate * d[k] - fixed) for k in ff if k]
    slope = max(0.0, sum(k * y for k, y in pts) / sum(k * k for k, _ in pts))
    R["model"] = {"rate": rate, "fixed": fixed, "ff_slope": slope, "ff_points": pts}
    save()
    return d, rate, lambda k: fixed + slope * k, slope


def sweep():
    d, rate, ff, slope = model()
    out = {}
    for cc in (10, 20, 40, 80, 160):
        jobs = [(c, a, b) for c in range(CHAPTERS) for a, b in chunks_for(d, cc, rate, ff)]
        wall = build_wall(jobs, WIDTH)
        out[cc] = {"chunks": len(jobs), "wall": wall}
        log(f"sweep CHUNK_COST {cc}s: {len(jobs)} chunks, wall {wall:.1f}s at width {WIDTH}")
        R["sweep"] = out
        save()


def d12():
    """Edit the last beat of the last chapter: parallel pass 1 of all chapters + render that beat's plays."""
    d, rate, ff, _ = model()
    best = min(R["sweep"].items(), key=lambda kv: kv[1]["wall"])[0]
    last_beat = (35, 41)
    t = time.monotonic()
    with ThreadPoolExecutor(CHAPTERS) as ex:
        list(ex.map(lambda c: synth("pass1", c, OUT / "p0"), range(CHAPTERS)))
    p1 = time.monotonic() - t
    sub = [(a + last_beat[0], b + last_beat[0]) for a, b in chunks_for(d[last_beat[0]:], float(best), rate, lambda k: ff(k + last_beat[0]))]
    r = build_wall([(CHAPTERS - 1, a, b) for a, b in sub], WIDTH)
    R["d12"] = {"pass1_wall": p1, "render_wall": r, "chunks": sub, "total": p1 + r, "chunk_cost": best}
    log(f"d12: pass1 {p1:.1f}s + render {r:.1f}s ({len(sub)} chunks) = {p1 + r:.1f}s (target 20s)")
    save()


def copy():
    """copy2 vs clonefile over the Mixing Deluxe file set + a warm tex/text cache, file by file."""
    import ctypes
    libc = ctypes.CDLL("libc.dylib", use_errno=True)
    src_talk = Path("/Users/minhtrinh/general-purpose/conversation-contexts/mixing-deluxe-presentation/manim-presenters/presentations/mixing-deluxe")
    files = [p for p in src_talk.rglob("*") if p.is_file() and "build" not in p.parts and "__pycache__" not in p.parts]
    files += [p for p in (OUT / "p0").glob("t*-*/**/*") if p.is_file()]
    size = sum(p.stat().st_size for p in files)
    res = {"files": len(files), "bytes": size}
    for name in ("copy2", "clonefile"):
        times = []
        for rep in range(5):
            dst = OUT / f"copy-{name}"
            shutil.rmtree(dst, ignore_errors=True)
            t = time.monotonic()
            for i, p in enumerate(files):
                q = dst / f"{i}-{p.name}"
                q.parent.mkdir(parents=True, exist_ok=True)
                if name == "copy2":
                    shutil.copy2(p, q)
                elif libc.clonefile(os.fsencode(p), os.fsencode(q), 0) != 0:
                    raise OSError(ctypes.get_errno(), "clonefile")
            times.append(time.monotonic() - t)
        res[name] = times
        log(f"copy {name}: {len(files)} files {size/2**20:.1f}MB: {[round(x*1000,1) for x in times]} ms")
    R["copy"] = res
    save()


STAGES = {"p2": p2, "p3ff": p3ff, "p0": p0, "sweep": sweep, "d12": d12, "copy": copy}
for s in (STAGES if sys.argv[1] == "all" else sys.argv[1:]):
    log("stage", s, "load", psutil.getloadavg())
    STAGES[s]()
log("done")
