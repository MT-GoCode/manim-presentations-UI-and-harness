# /// script
# requires-python = "==3.12.*"
# dependencies = ["av==19.0.2", "numpy==2.5.4", "playwright==1.64.1", "pillow"]
# ///
"""Probe 3: the fresh-element route. Every show makes a new <video> under the front one, waits for loadeddata, seeks
paused to (k+0.5)/fps, raises it on `seeked` (removing the old one), then plays if asked. Checks canvas and screen."""

import argparse, io, json, sys, tempfile
from pathlib import Path

import numpy as np
from PIL import Image
from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).parent))
from seeked_probe import CELLS, FPS, ROW_H, JS, make_clip, page_html  # noqa: E402

VW, VH = 480, 270
ROUTE = r"""
let front = null;
window.show = (i, k, play, loop) => new Promise((res, rej) => {
  const v = mk(i, loop); v.style.zIndex = 0; const old = front, t0 = performance.now();
  const to = setTimeout(() => rej(new Error('timeout ' + i + ' ' + k)), 10000);
  const go = () => { v.addEventListener('seeked', () => { clearTimeout(to);
      const e = {canvas: code(v), oldOnTop: old ? old.style.zIndex === '2' : null, ms: Math.round(performance.now() - t0)};
      v.style.zIndex = 2; if (old) old.remove(); front = v; if (play) v.play(); res(e); }, {once: true});
    v.currentTime = (k + 0.5) / FPS; };
  v.readyState >= 2 ? go() : v.addEventListener('loadeddata', go, {once: true});
});
window.frontCode = () => code(front);
"""


def screen_code(page) -> int:
    img = np.asarray(Image.open(io.BytesIO(page.screenshot(clip={"x": 0, "y": 0, "width": VW, "height": VH}))).convert("L"))
    cw = VW // CELLS
    return sum(1 << b for b in range(CELLS) if img[ROW_H // 2, b * cw + cw // 2] > 128)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--engine", choices=("webkit", "chrome"), required=True)
    engine = ap.parse_args().engine
    ns = [60, 45, 30]
    d = Path(tempfile.mkdtemp())
    html = d / "p.html"
    html.write_text(page_html([make_clip(VW, VH, n, i + 1) for i, n in enumerate(ns)]).replace(
        "<body>", "<body style='margin:0'><style>video{position:absolute;left:0;top:0;width:480px;height:270px}</style>"
    ).replace("</body>", f"<script>{ROUTE}</script></body>"))
    ok_all = True
    with sync_playwright() as pw:
        b = pw.webkit.launch(headless=True) if engine == "webkit" else pw.chromium.launch(channel="chrome", headless=True)
        p = b.new_page(viewport={"width": 960, "height": 540})
        p.goto(html.as_uri())
        # (clip, frame, play, loop, settle_ms): Before, Next, Next(loop), Previous(hold), Replay, self-hold, Previous...
        steps = [(0, 0, False, False, 0), (0, 0, True, False, 2500), (1, 0, True, True, 700), (0, 59, False, False, 0),
                 (0, 0, True, False, 300), (0, 59, False, False, 0), (1, 44, False, False, 0), (2, 0, True, False, 200),
                 (1, 0, True, True, 400), (2, 29, False, False, 0), (0, 30, False, False, 0), (0, 0, False, False, 0)]
        for i, k, play, loop, settle in steps:
            e = p.evaluate(f"show({i}, {k}, {str(play).lower()}, {str(loop).lower()})")
            want = (i + 1) << 10 | k
            scr = screen_code(p)
            ok = e["canvas"] == want and (play or scr == want) and e["oldOnTop"] in (True, None)
            row = {"clip": i, "k": k, "play": play, "canvas": e["canvas"], "screen": scr, "want": want, "ms": e["ms"], "ok": ok}
            if settle:
                p.wait_for_timeout(settle)
                row["after_settle_canvas"], row["after_settle_screen"] = p.evaluate("frontCode()"), screen_code(p)
            ok_all &= ok
            print(json.dumps({"engine": engine, **row}), flush=True)
        n_videos = p.evaluate("document.querySelectorAll('video').length")
        print(json.dumps({"engine": engine, "videos_left": n_videos, "summary_ok": ok_all and n_videos == 1}), flush=True)
        b.close()
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main())
