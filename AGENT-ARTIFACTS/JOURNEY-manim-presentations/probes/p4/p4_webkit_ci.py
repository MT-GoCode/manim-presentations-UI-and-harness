# /// script
# requires-python = "==3.12.*"
# dependencies = ["av==19.0.2", "numpy==2.5.4", "playwright==1.64.1", "psutil==7.2.2"]
# ///
"""P4 browser checks and P5 browser bullets: one self-contained script, no ffmpeg binary needed.

Run on GitHub macos-latest:
    uv run --script p4_webkit_ci.py --engine webkit     # after: uvx playwright@1.64.1 install webkit
    uv run --script p4_webkit_ci.py --engine chrome     # stock /Applications/Google Chrome.app, headless

It makes its own barcoded H.264 clips with PyAV (frame i shows the 24-bit code i | clip<<16, read back
from the presented frame through a canvas), builds single-file export pages with the plan's player
(base64 <script> blocks, Blob URLs only for the current beat +-1, previous video kept in front until the
incoming one's first requestVideoFrameCallback), and prints one JSON object per check, then a summary.
Exit 0 iff play-to-ended and the paused seeks at the player's half-frame targets pass (the P5 gate).
"""

import argparse
import base64
import json
import statistics
import sys
import tempfile
import threading
import time
from pathlib import Path

import av
import numpy as np
import psutil
from playwright.sync_api import sync_playwright

FPS = 30
SRC_W, SRC_H = 3456, 2168  # the talk's aspect; small test clips keep it
GEOM = {"x0": 48 / 3456, "cell": 72 / 3456, "yc": (48 + 36) / 3456, "bits": 24}  # fractions of width


def width_for(h: int) -> int:
    return 2 * round(h * SRC_W / SRC_H / 2)


def stamp(rgb: np.ndarray, code: int) -> None:
    w = rgb.shape[1]
    cell, yc = round(GEOM["cell"] * w), round(GEOM["yc"] * w)
    half = max(2, cell // 2)
    x = lambda b: round(w * (GEOM["x0"] + b * GEOM["cell"]))  # noqa: E731
    rgb[yc - half - 3 : yc + half + 3, x(0) - 3 : x(GEOM["bits"]) + 3] = 0
    for b in range(GEOM["bits"]):
        if code >> b & 1:
            rgb[yc - half : yc + half, x(b) : x(b + 1)] = 255


def make_clip(w: int, h: int, n: int, clip_id: int, crf: int = 20) -> bytes:
    """Frame i: barcode i | clip_id<<16 over a gradient that shifts by 256/n per frame, so frame n == frame 0."""
    yy, xx = np.mgrid[0:h, 0:w]
    path = Path(tempfile.mkstemp(suffix=".mp4")[1])
    with av.open(str(path), "w", options={"movflags": "faststart"}) as out:
        s = out.add_stream("libx264", rate=FPS)
        s.width, s.height, s.pix_fmt = w, h, "yuv420p"
        s.codec_context.options = {"crf": str(crf), "threads": "1"}
        for i in range(n):
            rgb = np.zeros((h, w, 3), np.uint8)
            rgb[..., 2] = ((xx * 256 // w + i * 256 // n) % 256).astype(np.uint8)
            rgb[..., 1] = (yy * 200 // h).astype(np.uint8)
            rgb[..., 0] = (clip_id * 37) % 256
            stamp(rgb, i | clip_id << 16)
            f = av.VideoFrame.from_ndarray(rgb, format="rgb24")
            f.pts = i
            out.mux(s.encode(f))
        out.mux(s.encode())
    data = path.read_bytes()
    path.unlink()
    return data


PLAYER_JS = r"""
const G = %(geom)s;
window.readCode = (v) => {
  const w = v.videoWidth, c = window._bc || (window._bc = document.createElement('canvas'));
  c.width = w; c.height = 1;
  const g = c.getContext('2d', {willReadFrequently: true});
  g.drawImage(v, 0, Math.round(G.yc * w), w, 1, 0, 0, w, 1);
  const d = g.getImageData(0, 0, w, 1).data;
  let code = 0;
  for (let b = 0; b < G.bits; b++) if (d[4 * Math.round(w * (G.x0 + (b + 0.5) * G.cell))] > 128) code |= 1 << b;
  return code;
};
const D = JSON.parse(document.getElementById('beats').textContent), FPS = D.fps;
const R = +(new URLSearchParams(location.search).get('r') || 1);  // window radius; 1 is the plan
const stage = document.getElementById('stage');
const V = D.beats.map(b => {
  const v = document.createElement('video');
  v.muted = true; v.playsInline = true; v.preload = 'auto'; v.loop = b.loop; v.style.zIndex = 0;
  stage.appendChild(v); return v;
});
const urls = new Map();
window.ERR = [];
function bytes(i) {
  const s = atob(document.getElementById('c' + i).textContent), u = new Uint8Array(s.length);
  for (let k = 0; k < s.length; k++) u[k] = s.charCodeAt(k);
  return u;
}
function load(i) {
  if (i < 0 || i >= V.length || urls.has(i)) return;
  const u = URL.createObjectURL(new Blob([bytes(i)], {type: 'video/mp4'}));
  urls.set(i, u); V[i].onerror = () => ERR.push({i, code: V[i].error && V[i].error.code}); V[i].src = u;
}
function unload(i) {
  V[i].pause(); V[i].removeAttribute('src'); V[i].load(); URL.revokeObjectURL(urls.get(i)); urls.delete(i);
}
function windowAt(c) {
  for (const i of [...urls.keys()]) if (Math.abs(i - c) > R) unload(i);
  for (let i = c - R; i <= c + R; i++) load(i);
}
let front = null, pos = -1;  // pos -1 is Before
// Seek targets sit half a frame past the wanted pts: an exact last-frame pts presents the frame before it in Chrome.
const at = (k) => (k + 0.5) / FPS;
function present(i, mode) {  // 'play' | 'first' | 'last'. 'play' shows frame 0 paused, swaps on its rVFC, then plays.
  windowAt(i);
  const v = V[i], old = front, t = performance.now();
  return new Promise((res, rej) => {
    const to = setTimeout(() => rej(new Error(`no frame: beat ${i} ${mode}`)), 15000);
    v.requestVideoFrameCallback((now, md) => {
      clearTimeout(to);
      const e = {i, mode, mediaTime: md.mediaTime, code: readCode(v), oldInFront: old ? old.style.zIndex === '2' : null,
                 ms: performance.now() - t, at: performance.now()};
      v.style.zIndex = 2;
      if (old && old !== v) { old.style.zIndex = 0; old.pause(); }
      if (mode === 'play' && v !== front) v.play().catch(rej);
      front = v; res(e);
    });
    // Already in front on frame 0 (Before -> Next): a same-position seek presents nothing, so just play.
    if (v === front && mode === 'play') v.play().catch(rej);
    else { v.pause(); v.currentTime = mode === 'last' ? at(D.beats[i].n - 1) : 0; }
  });
}
window.P = {
  next: () => (pos + 1 < V.length ? present(++pos, 'play') : null),
  prev: () => (pos < 0 ? null : (--pos < 0 ? present(0, 'first') : present(pos, 'last'))),
  seek: (i, t) => { windowAt(i); const v = V[i]; v.pause();
    return new Promise(res => { v.requestVideoFrameCallback((n, md) => res({mediaTime: md.mediaTime, code: readCode(v)})); v.currentTime = t; }); },
  live: () => V.filter(v => v.hasAttribute('src')).length,
  // Play beat i and log every presented frame until `wraps` wraps (loop) or `ended` (non-loop).
  trace: (i, wraps, doubleBuffer) => new Promise((res, rej) => {
    windowAt(i);
    const log = [], n = D.beats[i].n, v = V[i];
    let w = 0, done = false;
    const finish = () => { if (!done) { done = true; res(log); } };
    setTimeout(() => rej(new Error('trace timeout ' + JSON.stringify(log.slice(-5)))), 4000 * (wraps + 1) * n / FPS + 15000);
    const tick = (vid) => (now, md) => {
      if (done || vid !== front) return;
      const code = readCode(vid) & 0xffff, prev = log.length ? log[log.length - 1].code : -1;
      if (code < prev) w++;
      log.push({code, mediaTime: md.mediaTime, now, presentedFrames: md.presentedFrames, el: vid === v ? 'A' : 'B'});
      if (w >= wraps) return finish();
      if (vid === front) vid.requestVideoFrameCallback(tick(vid));
    };
    v.onended = () => setTimeout(finish, 300);
    if (!doubleBuffer) { present(i, 'play').then(() => v.requestVideoFrameCallback(tick(v)), rej); return; }
    // Fallback under test: two <video>s on one Blob URL, no `loop`. The spare waits behind, paused on frame 0;
    // when the front presents its last frame, the spare is raised (frame 0 already painted) and played.
    v.loop = false;
    const b = document.createElement('video');
    b.muted = true; b.playsInline = true; b.preload = 'auto'; b.style.zIndex = 0; b.src = v.src; b.currentTime = 0;
    stage.appendChild(b);
    const arm = (cur, nxt) => {
      const watch = (now, md) => {
        if (done) return;
        if (md.mediaTime < (n - 1) / FPS - 1e-3) return cur.requestVideoFrameCallback(watch);
        setTimeout(() => {  // raise when the last frame has had its full frame period on screen
          nxt.style.zIndex = 2; cur.style.zIndex = 0; front = nxt;
          log.push({code: readCode(nxt) & 0xffff, mediaTime: 0, now: performance.now(), el: 'raise'});
          if (log[log.length - 1].code < log[log.length - 2].code) w++;
          if (w >= wraps) return finish();
          nxt.play(); nxt.requestVideoFrameCallback(tick(nxt));
          cur.pause(); cur.currentTime = 0; arm(nxt, cur);
        }, md.expectedDisplayTime + 1000 / FPS - performance.now());
      };
      cur.requestVideoFrameCallback(watch);
    };
    present(i, 'play').then(() => { v.requestVideoFrameCallback(tick(v)); arm(v, b); }, rej);
  }),
};
window.FIRST = present(0, 'first');
"""

PAGE_HEAD = """<!doctype html><html><head><meta charset=utf-8><title>export</title><style>
body{margin:0;background:#000}#stage{position:fixed;inset:0}
video{position:absolute;inset:0;width:100%;height:100%;object-fit:contain;background:#000}
</style></head><body><div id=stage></div>
"""


def build_html(clips: list[tuple[bytes, int, bool]]) -> str:
    """clips: (mp4 bytes, frame count, loop). One self-contained page."""
    beats = {"fps": FPS, "beats": [{"n": n, "loop": loop} for _, n, loop in clips]}
    parts = [PAGE_HEAD, f'<script type="application/json" id=beats>{json.dumps(beats)}</script>\n']
    for i, (data, _, _) in enumerate(clips):
        parts.append(f'<script type="application/octet-stream" id=c{i}>{base64.b64encode(data).decode()}</script>\n')
    parts.append(f"<script>{PLAYER_JS % {'geom': json.dumps(GEOM)}}</script></body></html>\n")
    return "".join(parts)


class TreeSampler:
    """Peak RSS of this process's descendants plus Playwright's WebKit XPC services, which macOS parents to
    launchd, so they are found by their executable living under the ms-playwright cache."""

    RENDERER = ("--type=renderer", "WebContent")

    def __init__(self, period: float = 0.05):
        self.period, self.stop = period, threading.Event()
        self.peak_total = self.peak_renderer = 0
        self.cpu: dict[int, float] = {}

    def procs(self) -> list[psutil.Process]:
        me = psutil.Process()
        out = {p.pid: p for p in (me, *me.children(recursive=True))}
        for p in psutil.process_iter(["exe"]):
            if "ms-playwright" in (p.info["exe"] or ""):
                out.setdefault(p.pid, p)
        return list(out.values())

    def sample(self) -> None:
        total = rend = 0
        for p in self.procs():
            try:
                rss, t, name = p.memory_info().rss, p.cpu_times(), p.name() + " " + " ".join(p.cmdline())
            except psutil.Error:
                continue  # exited between listing and reading
            self.cpu[p.pid] = t.user + t.system
            total += rss
            if any(k in name for k in self.RENDERER):
                rend = max(rend, rss)
        self.peak_total, self.peak_renderer = max(self.peak_total, total), max(self.peak_renderer, rend)

    def __enter__(self):
        self.t0 = time.monotonic()
        self.sample()
        self.cpu0 = dict(self.cpu)
        self.th = threading.Thread(target=lambda: [self.sample() for _ in iter(lambda: not self.stop.wait(self.period), False)], daemon=True)
        self.th.start()
        return self

    def __exit__(self, *a):
        self.stop.set()
        self.th.join()
        self.wall = time.monotonic() - self.t0
        self.cores = sum(v - self.cpu0.get(pid, 0.0) for pid, v in self.cpu.items()) / self.wall

    def report(self) -> dict:
        return {"tree_peak_rss_mb": round(self.peak_total / 2**20), "renderer_peak_rss_mb": round(self.peak_renderer / 2**20),
                "tree_cores": round(self.cores, 2), "wall_s": round(self.wall, 2)}


def launch(pw, engine: str):
    return pw.webkit.launch(headless=True) if engine == "webkit" else pw.chromium.launch(channel="chrome", headless=True)


def open_page(browser, html: Path, r: int = 1):
    ctx = browser.new_context(viewport={"width": 1920, "height": 1080})
    ctx.route("**/*", lambda rt: rt.continue_() if rt.request.url.startswith(("file:", "blob:", "data:")) else rt.abort())
    page = ctx.new_page()
    t0 = time.monotonic()
    page.goto(html.as_uri() + f"?r={r}", timeout=300000)
    first = page.evaluate("FIRST")
    return page, {"first_frame_ms_perf": round(first["at"]), "first_frame_s_wall": round(time.monotonic() - t0, 3),
                  "first_code": first["code"], "first_mediaTime": first["mediaTime"]}


def write(d: Path, name: str, clips) -> Path:
    p = d / name
    p.write_text(build_html(clips))
    return p


def seam(log: list[dict], n: int) -> dict:
    """Wrap = code decreases. Stall = the wall gap at a wrap exceeds 3x the median gap elsewhere and 100 ms."""
    gaps = [(b["now"] - a["now"], a["code"], b["code"]) for a, b in zip(log, log[1:])]
    wrap = [g for g in gaps if g[2] < g[1]]
    rest = [g[0] for g in gaps if g[2] >= g[1]]
    med = statistics.median(rest)
    skips_rest = sum(1 for g in gaps if g[2] > g[1] + 1)
    out = {"frames_logged": len(log), "wraps": len(wrap), "median_gap_ms": round(med, 2), "max_gap_ms_nonwrap": round(max(rest), 2),
           "wrap_gaps_ms": [round(g[0], 2) for g in wrap], "wrap_steps": [[g[1], g[2]] for g in wrap],
           "skipped_steps_nonwrap": skips_rest, "frames_per_cycle": n}
    out["stall"] = any(g[0] > max(3 * med, 100) for g in wrap)
    out["clean_wraps"] = sum(1 for g in wrap if g[1] == n - 1 and g[2] == 0)
    return out


def run(engine: str, force_fallback: bool) -> dict:
    d = Path(tempfile.mkdtemp(prefix="p4w-"))
    res: dict = {"engine": engine}
    with sync_playwright() as pw:
        browser = launch(pw, engine)
        res["version"] = browser.version
        with TreeSampler() as ts:
            ctx = browser.new_context(); ctx.new_page().goto("about:blank"); time.sleep(1); ctx.close()
        print(json.dumps({"check": "baseline_blank_page", "engine": engine, **ts.report()}), flush=True)
        emit = lambda k, v: (res.__setitem__(k, v), print(json.dumps({"check": k, "engine": engine, **v}), flush=True))  # noqa: E731

        # P5: 480x270 clip plays to `ended`; paused seeks present exactly the target frame.
        n = 60
        page, ff = open_page(browser, write(d, "p5.html", [(make_clip(480, 270, n, 0), n, False)]))
        log = page.evaluate("P.trace(0, 1, false)")
        log = [e for e in log]
        last = log[-1]
        emit("play_to_ended", {"ended": page.evaluate("document.querySelector('video').ended"), "frames_presented": len(log),
                               "last_code": last["code"], "last_mediaTime": last["mediaTime"],
                               "ok": last["code"] == n - 1 and abs(last["mediaTime"] - (n - 1) / FPS) < 1e-3})
        seeks = []
        for k in (n - 1, 0, n // 2, n - 1):
            for t, label in ((k / FPS, "exact"), ((k + 0.5) / FPS, "half_frame")):  # the player uses half_frame
                r = page.evaluate("([t]) => P.seek(0, t)", [t])
                seeks.append({"frame": k, "how": label, "mediaTime": r["mediaTime"], "code": r["code"] & 0xffff,
                              "ok": (r["code"] & 0xffff) == k and abs(r["mediaTime"] - k / FPS) < 1e-3})
        emit("paused_seek", {"ok_exact": all(s["ok"] for s in seeks if s["how"] == "exact"),
                             "ok_half_frame": all(s["ok"] for s in seeks if s["how"] == "half_frame"), "seeks": seeks})
        page.context.close()
        # Freshly loaded paused video at pts 0 (the Before state), plus Previous onto the last frame.
        page, ff = open_page(browser, write(d, "two.html", [(make_clip(480, 270, 45, 0), 45, False), (make_clip(480, 270, 45, 1), 45, False)]))
        # From Before, frame 0 is already on screen, so the first new frame after Next is frame 1.
        a = page.evaluate("P.next()"); b = page.evaluate("P.next()"); c = page.evaluate("P.prev()"); z = page.evaluate("P.prev()")
        emit("transitions", {"before": ff, "next0": a, "next1": b, "prev_to_last": c, "prev_to_before": z,
                             "ok": ff["first_code"] == 0 and a["code"] == 1 and b["code"] == 1 << 16 and c["code"] == 44
                             and z["code"] == 0 and b["oldInFront"] and c["oldInFront"] and z["oldInFront"]})
        page.context.close()

        # Loop seam: <video loop> mediaTime + pixel sequence across 4 wraps.
        nl = 45
        page, _ = open_page(browser, write(d, "loop.html", [(make_clip(480, 270, nl, 0), nl, True)]))
        s = seam(page.evaluate("P.trace(0, 4, false)"), nl)
        emit("loop_seam", s)
        page.context.close()
        if s["stall"] or force_fallback:
            page, _ = open_page(browser, write(d, "loopdb.html", [(make_clip(480, 270, nl, 0), nl, True)]))
            emit("loop_double_buffer", {"forced": not s["stall"], **seam(page.evaluate("P.trace(0, 4, true)"), nl)})
            page.context.close()

        # >=120 beats: click through all with the +-1 window, then the all-src control (r=1000).
        nb = 130
        many = [(make_clip(480, 270, 6, i, crf=28), 6, False) for i in range(nb)]
        html = write(d, "many.html", many)
        for r in (1, 1000):
            page, _ = open_page(browser, html, r)
            bad, live_max = [], 0
            for i in range(nb):
                try:
                    e = page.evaluate("P.next()")
                    if e["code"] >> 16 != i:
                        bad.append({"beat": i, "code": e["code"]})
                except Exception as ex:  # a missing frame is the result being measured, not a crash
                    bad.append({"beat": i, "error": str(ex)[:120]})
                    break
                live_max = max(live_max, page.evaluate("P.live()"))
            emit(f"click_through_r{r}", {"beats": nb, "failures": bad[:5], "n_failures": len(bad), "max_live_src": live_max,
                                          "media_errors": page.evaluate("ERR.length"), "ok": not bad})
            page.context.close()

        # Open -> first frame at each export height, 3-clip page (3 s each), 3 runs.
        for h in (1080, 720, 540):
            clips = [(make_clip(width_for(h), h, 90, i), 90, False) for i in range(3)]
            html = write(d, f"h{h}.html", clips)
            runs = []
            for _ in range(3):
                with TreeSampler() as ts:
                    page, ff = open_page(browser, html)
                    page.evaluate("P.next()")
                    page.context.close()
                runs.append({**ff, **ts.report()})
            emit(f"first_frame_h{h}", {"html_bytes": html.stat().st_size, "runs": runs,
                                       "median_first_frame_ms": statistics.median(x["first_frame_ms_perf"] for x in runs),
                                       "max_first_frame_ms": max(x["first_frame_ms_perf"] for x in runs)})
        browser.close()
    return res


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--engine", choices=("webkit", "chrome"), default="webkit")
    ap.add_argument("--force-fallback", action="store_true", help="also exercise the double-buffer loop when the seam is clean")
    a = ap.parse_args()
    with TreeSampler() as ts:
        res = run(a.engine, a.force_fallback)
    ok = res["play_to_ended"]["ok"] and res["paused_seek"]["ok_half_frame"]
    print(json.dumps({"summary": a.engine, "version": res["version"], "p5_gate": "PASS" if ok else "FAIL",
                      "loop_stall": res["loop_seam"]["stall"], "click_through_r1_ok": res["click_through_r1"]["ok"],
                      "transitions_ok": res["transitions"]["ok"], "script_process_tree": ts.report()}), flush=True)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
