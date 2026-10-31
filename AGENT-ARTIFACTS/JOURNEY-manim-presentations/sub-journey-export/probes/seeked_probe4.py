# /// script
# requires-python = "==3.12.*"
# dependencies = ["av==19.0.2", "numpy==2.5.4", "playwright==1.64.1"]
# ///
"""Probe 4: under CPU load, is a fresh <video>'s frame drawn by the time `seeked` fires? For many fresh-element paused
seeks, read the frame code through a canvas at `seeked`, at the next requestAnimationFrame, and at the next
requestVideoFrameCallback (if it fires within 1 s); count wrong reads per signal. Clips encoded like export's job."""

import argparse, json, subprocess, sys, tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from seeked_probe import JS, page_html  # noqa: E402

import av
import numpy as np
from playwright.sync_api import sync_playwright

FPS, CELLS, ROW_H = 30, 16, 24


def make_clip(w, h, n, clip_id):
    path = Path(tempfile.mkstemp(suffix=".mp4")[1])
    cw = w // CELLS
    with av.open(str(path), "w", options={"movflags": "faststart"}) as out:
        s = out.add_stream("libx264", rate=FPS)
        s.width, s.height, s.pix_fmt = w, h, "yuv420p"
        s.codec_context.options = {"crf": "28", "threads": "1"}  # export's job: default GOP
        for i in range(n):
            rgb = np.full((h, w, 3), 40, np.uint8)
            rgb[ROW_H:, :, 2] = (np.arange(w) * 255 // w + i * 9) % 256  # moving content, like real clips
            code = i | clip_id << 10
            for b in range(CELLS):
                if code >> b & 1:
                    rgb[0:ROW_H, b * cw + 2 : (b + 1) * cw - 2] = 255
            f = av.VideoFrame.from_ndarray(rgb, format="rgb24")
            f.pts = i
            out.mux(s.encode(f))
        out.mux(s.encode())
    data = path.read_bytes()
    path.unlink()
    return data


TRIAL = r"""
window.trial = (i, k) => new Promise((res) => {
  const v = mk(i); const out = {};
  const to = setTimeout(() => res({...out, timeout: true}), 8000);
  v.addEventListener('loadeddata', () => {
    let vfc = false;
    if (v.requestVideoFrameCallback) v.requestVideoFrameCallback(() => { vfc = true; out.vfc = code(v); });
    v.addEventListener('seeked', () => {
      out.seeked = code(v);
      requestAnimationFrame(() => { out.raf = code(v);
        setTimeout(() => { clearTimeout(to); out.later = code(v); out.vfc_fired = vfc; v.remove(); res(out); }, 1000); });
    }, {once: true});
    v.currentTime = (k + 0.5) / FPS;
  }, {once: true});
});
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--engine", choices=("webkit", "chrome"), required=True)
    ap.add_argument("--trials", type=int, default=120)
    ap.add_argument("--burners", type=int, default=3)
    a = ap.parse_args()
    n = 25
    d = Path(tempfile.mkdtemp())
    html = d / "p.html"
    html.write_text(page_html([make_clip(960, 540, n, c + 1) for c in range(4)]).replace("</body>", f"<script>{TRIAL}</script></body>"))
    burners = [subprocess.Popen([sys.executable, "-c", "while True: pass"]) for _ in range(a.burners)]
    tally = {"seeked": 0, "raf": 0, "vfc": 0, "later": 0, "vfc_fired": 0, "timeout": 0}
    bad = []
    try:
        with sync_playwright() as pw:
            b = pw.webkit.launch() if a.engine == "webkit" else pw.chromium.launch(channel="chrome")
            p = b.new_page(viewport={"width": 960, "height": 600})
            p.goto(html.as_uri())
            for t in range(a.trials):
                i, k = t % 4, (n - 1, 0, 12, n - 1)[t % 4]
                r = p.evaluate(f"trial({i}, {k})")
                want = (i + 1) << 10 | k
                tally["timeout"] += bool(r.get("timeout"))
                tally["vfc_fired"] += bool(r.get("vfc_fired"))
                for s in ("seeked", "raf", "vfc", "later"):
                    if s in r and r[s] != want:
                        tally[s] += 1
                        bad.append({"t": t, "signal": s, "got": r[s], "want": want})
            b.close()
    finally:
        for q in burners:
            q.kill()
    print(json.dumps({"engine": a.engine, "trials": a.trials, "burners": a.burners, "wrong": tally, "first_bad": bad[:8]}), flush=True)


if __name__ == "__main__":
    main()
