# /// script
# requires-python = "==3.12.*"
# dependencies = ["av==19.0.2", "numpy==2.5.4", "playwright==1.64.1"]
# ///
"""Sub-journey export probe: the paused-seek route (swap on `seeked`) in headless WebKit and Chrome.
Prints one JSON line per check; exit 0 iff every check passes."""

import argparse, json, sys, tempfile, base64
from pathlib import Path

import av
import numpy as np
from playwright.sync_api import sync_playwright

FPS = 30
CELLS, ROW_H = 16, 24  # 16 cells across the top band of a 480x270 frame


def make_clip(w, h, n, clip_id):
    path = Path(tempfile.mkstemp(suffix=".mp4")[1])
    cw = w // CELLS
    with av.open(str(path), "w", options={"movflags": "faststart"}) as out:
        s = out.add_stream("libx264", rate=FPS)
        s.width, s.height, s.pix_fmt = w, h, "yuv420p"
        s.codec_context.options = {"crf": "28", "threads": "1", "g": "6"}
        for i in range(n):
            rgb = np.full((h, w, 3), 40, np.uint8)
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


JS = r"""
const CELLS = %d, ROW_H = %d, FPS = %d;
window.code = (v) => {
  const w = v.videoWidth, c = document.createElement('canvas'); c.width = w; c.height = 1;
  const g = c.getContext('2d', {willReadFrequently: true});
  g.drawImage(v, 0, ROW_H / 2, w, 1, 0, 0, w, 1);
  const d = g.getImageData(0, 0, w, 1).data, cw = Math.floor(w / CELLS);
  let k = 0; for (let b = 0; b < CELLS; b++) if (d[4 * (b * cw + (cw >> 1))] > 128) k |= 1 << b;
  return k;
};
const blobs = [...document.querySelectorAll('script[type="application/octet-stream"]')].map(s => {
  const b = atob(s.textContent), u = new Uint8Array(b.length); for (let i = 0; i < b.length; i++) u[i] = b.charCodeAt(i);
  return URL.createObjectURL(new Blob([u], {type: 'video/mp4'}));
});
window.mk = (i, loop) => { const v = document.createElement('video'); v.muted = true; v.playsInline = true; v.preload = 'auto';
  v.loop = !!loop; v.src = blobs[i]; document.body.appendChild(v); return v; };
window.seek = (v, t, ms = 5000) => new Promise((res) => {
  const to = setTimeout(() => res({timeout: true}), ms);
  v.addEventListener('seeked', () => { clearTimeout(to);
    const now = {code: code(v) & 1023, ready: v.readyState, t: v.currentTime};
    requestAnimationFrame(() => res({...now, raf: code(v) & 1023})); }, {once: true});
  v.pause(); v.currentTime = t; });
window.sampleUntil = (v, ms) => new Promise(res => { const log = [], t0 = performance.now();
  const f = () => { log.push({c: code(v), t: v.currentTime, ended: v.ended, paused: v.paused});
    performance.now() - t0 < ms ? requestAnimationFrame(f) : res(log); }; f(); });
"""


def page_html(clips):
    blocks = "".join(f'<script type="application/octet-stream">{base64.b64encode(c).decode()}</script>' for c in clips)
    return f"<!doctype html><html><body>{blocks}<script>{JS % (CELLS, ROW_H, FPS)}</script></body></html>"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--engine", choices=("webkit", "chrome"), required=True)
    engine = ap.parse_args().engine
    n = 60
    d = Path(tempfile.mkdtemp())
    html = d / "p.html"
    html.write_text(page_html([make_clip(480, 270, n, 1), make_clip(480, 270, 45, 2)]))
    ok_all = True

    def emit(name, ok, **kw):
        nonlocal ok_all
        ok_all &= ok
        print(json.dumps({"check": name, "engine": engine, "ok": ok, **kw}), flush=True)

    with sync_playwright() as pw:
        b = pw.webkit.launch(headless=True) if engine == "webkit" else pw.chromium.launch(channel="chrome", headless=True)
        ctx = b.new_context(viewport={"width": 960, "height": 540})
        ctx.route("**/*", lambda r: r.continue_() if r.request.url.startswith(("file:", "blob:", "data:")) else r.abort())
        p = ctx.new_page()
        p.goto(html.as_uri())
        # 1. Fresh video: seek immediately after src (before metadata) to frame 0 and to the last frame.
        r0 = p.evaluate("seek(mk(0), 0.5 / FPS)")
        emit("fresh_seek_frame0", r0.get("code") == 0 and r0.get("raf") == 0, result=r0)
        rl = p.evaluate(f"seek(mk(0), ({n} - 0.5) / FPS)")
        emit("fresh_seek_last", rl.get("code") == n - 1 and rl.get("raf") == n - 1, result=rl)
        # 2. One loaded video, paused seeks in sequence (last, 0, middle, last, 0).
        p.evaluate("window.V = mk(0)")
        res = []
        for k in (n - 1, 0, 30, n - 1, 0, 1, n - 2):
            r = p.evaluate(f"seek(V, ({k} + 0.5) / FPS)")
            res.append({"k": k, **r})
        emit("paused_seeks", all(r.get("code") == r["k"] and r.get("raf") == r["k"] and r.get("ready", 0) >= 2 for r in res), seeks=res)
        # 3. Same-position seek (already at 0.5/FPS -> 0.5/FPS) still fires seeked.
        p.evaluate("seek(V, 0.5 / FPS)")
        rs = p.evaluate("seek(V, 0.5 / FPS)")
        emit("same_position_seek", not rs.get("timeout") and rs.get("code") == 0, result=rs)
        # 4. Seek to frame 0 paused, then play: plays through to ended and holds the last frame.
        p.evaluate("seek(V, 0.5 / FPS).then(() => V.play())")
        log = p.evaluate(f"sampleUntil(V, {int(n / FPS * 1000) + 1500})")
        codes = [e["c"] & 1023 for e in log]
        emit("play_to_ended_holds_last", log[-1]["ended"] and codes[-1] == n - 1 and codes == sorted(codes),
             first=codes[:3], last=codes[-3:], n_samples=len(codes))
        # 5. Loop: 2x duration later still playing and wrapped.
        p.evaluate("window.L = mk(1, true); seek(L, 0.5 / FPS).then(() => L.play())")
        log = p.evaluate(f"sampleUntil(L, {int(2 * 45 / FPS * 1000) + 300})")
        full = [e["c"] for e in log]
        codes = [c & 1023 for c in full]
        wraps = sum(1 for a, c in zip(codes, codes[1:]) if c < a)
        emit("loop_wraps", wraps >= 2 and not log[-1]["paused"] and all(c >> 10 == 2 for c in full), wraps=wraps,
             tail=codes[-5:])
        # 6. Two seeks back to back: which seeked events fire, and the final frame.
        r = p.evaluate("""new Promise(res => { const ev = []; V.pause();
            V.addEventListener('seeked', () => ev.push(code(V) & 1023));
            V.currentTime = 10.5 / FPS; V.currentTime = 40.5 / FPS;
            setTimeout(() => res({ev, final: code(V) & 1023}), 1500); })""")
        emit("back_to_back_seeks", r["final"] == 40, result=r)
        # 7. After ended (non-loop), a paused seek to the last frame still fires seeked (Previous onto a just-played beat).
        p.evaluate("V.pause()")
        r = p.evaluate(f"seek(V, ({n} - 0.5) / FPS)")
        emit("seek_last_after_ended", r.get("code") == n - 1, result=r)
        b.close()
    print(json.dumps({"summary": engine, "ok": ok_all}), flush=True)
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main())
