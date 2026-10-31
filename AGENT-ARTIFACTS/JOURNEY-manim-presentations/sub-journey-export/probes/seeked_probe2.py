# /// script
# requires-python = "==3.12.*"
# dependencies = ["av==19.0.2", "numpy==2.5.4", "playwright==1.64.1", "pillow"]
# ///
"""Probe 2: what a paused seek shows in headless WebKit, on screen (screenshot) and through a canvas, for a fresh
video, a primed one (played then paused), and over time; plus loop playback rate."""

import argparse, io, json, sys, tempfile
from pathlib import Path

import numpy as np
from PIL import Image
from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).parent))
from seeked_probe import CELLS, FPS, ROW_H, JS, make_clip, page_html  # noqa: E402

VW, VH = 480, 270


def screen_code(page) -> int:
    """Decode the code from the pixels on screen: the video sits at (0,0) at its natural size."""
    img = np.asarray(Image.open(io.BytesIO(page.screenshot(clip={"x": 0, "y": 0, "width": VW, "height": VH}))).convert("L"))
    cw = VW // CELLS
    return sum(1 << b for b in range(CELLS) if img[ROW_H // 2, b * cw + cw // 2] > 128)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--engine", choices=("webkit", "chrome"), required=True)
    engine = ap.parse_args().engine
    n = 60
    d = Path(tempfile.mkdtemp())
    html = d / "p.html"
    html.write_text(page_html([make_clip(VW, VH, n, 1), make_clip(VW, VH, 45, 2)]).replace(
        "<body>", "<body style='margin:0'><style>video{position:absolute;left:0;top:0;width:480px;height:270px}</style>"))

    def out(name, **kw):
        print(json.dumps({"check": name, "engine": engine, **kw}), flush=True)

    with sync_playwright() as pw:
        b = pw.webkit.launch(headless=True) if engine == "webkit" else pw.chromium.launch(channel="chrome", headless=True)
        for prime in ("fresh", "play_pause", "play_until_frame"):
            ctx = b.new_context(viewport={"width": 960, "height": 540})
            p = ctx.new_page()
            p.goto(html.as_uri())
            p.evaluate("window.V = mk(0); new Promise(r => V.addEventListener('loadeddata', r, {once: true}))")
            if prime == "play_pause":
                p.evaluate("V.play().then(() => V.pause())")
            elif prime == "play_until_frame":
                p.evaluate("new Promise(r => { V.requestVideoFrameCallback(() => { V.pause(); r(); }); V.play(); })")
            rows = []
            for k in (n - 1, 30, 0, 45):
                r = p.evaluate(f"seek(V, ({k} + 0.5) / FPS)")
                at = {"k": k, "canvas_seeked": r.get("code"), "screen_now": screen_code(p) & 1023}
                for ms in (100, 500):
                    p.wait_for_timeout(ms)
                    at[f"canvas_{ms}"] = p.evaluate("code(V) & 1023")
                    at[f"screen_{ms}"] = screen_code(p) & 1023
                rows.append(at)
            out(f"paused_seek_{prime}", rows=rows)
            ctx.close()
        # Loop playback: currentTime and code over 4 s.
        ctx = b.new_context(viewport={"width": 960, "height": 540})
        p = ctx.new_page()
        p.goto(html.as_uri())
        log = p.evaluate("""(async () => { const L = mk(1, true);
            await new Promise(r => L.addEventListener('loadeddata', r, {once: true})); await L.play();
            const t0 = performance.now(), log = [];
            while (performance.now() - t0 < 4000) { await new Promise(r => setTimeout(r, 200));
              log.push({ms: Math.round(performance.now() - t0), t: +L.currentTime.toFixed(3), c: code(L) & 1023,
                        paused: L.paused, q: L.getVideoPlaybackQuality && L.getVideoPlaybackQuality().totalVideoFrames}); }
            return log; })()""")
        out("loop_rate", log=log)
        b.close()


if __name__ == "__main__":
    main()
