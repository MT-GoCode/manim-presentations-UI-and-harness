"""The export tests' own tools for the frames talk, whose every frame carries the code beat << 8 | frame index
(drawn by fixtures/frames.manim-presentation/helpers/code.py): its decoder and the exported page's parts."""

import base64
import io
import json
import re
import subprocess
import sys
from pathlib import Path

import av
from conftest import SUBPROCESS_TIMEOUT

FRAMES = Path(__file__).parent / "fixtures" / "frames.manim-presentation"
CELLS = 12
ROW = 0.056  # the cells' centre line, as a fraction of frame height (0.45 of 8 scene units)


def code(gray) -> int:
    """The frame code of one frame given as a 2-D luma array."""
    h, w = gray.shape
    return sum(1 << b for b in range(CELLS) if gray[int(ROW * h), int((b + 0.5) * w / CELLS)] > 128)


def run(*args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    """mpres with an environment (the engine-edit pattern); conftest.mpres for everything else."""
    return subprocess.run(
        [sys.executable, "-P", "-m", "manim_presentations.cli", *args],
        capture_output=True,
        text=True,
        timeout=SUBPROCESS_TIMEOUT,
        env=env,
    )


def manifest(html: str) -> dict:
    return json.loads(re.search(r'<script type="application/json" id="manifest">(.*?)</script>', html, re.S)[1])


def clips(html: str) -> list[bytes]:
    blocks = re.findall(r'<script type="application/octet-stream" id="clip-(\d+)">(.*?)</script>', html, re.S)
    assert [int(i) for i, _ in blocks] == list(range(len(blocks)))
    return [base64.b64decode(b) for _, b in blocks]


def decoded(clip: bytes) -> tuple[tuple[int, int, int], list[int]]:
    """The clip's (width, height, frame rate) and the code of every frame, in presentation order."""
    with av.open(io.BytesIO(clip)) as f:
        s = f.streams.video[0]
        return (s.width, s.height, s.average_rate), [code(fr.to_ndarray(format="gray")) for fr in f.decode(s)]


# Installed before the page's own scripts. The tests' decoder (the same code as code() above, reading the front
# video through a canvas) and a ledger of live Blob URLs keyed by the Blob itself, so a URL's beat is found by its
# bytes, not by anything the player says.
_PAGE = """(ROW, CELLS) => {
  const live = new Map(), create = URL.createObjectURL, revoke = URL.revokeObjectURL;
  URL.createObjectURL = (o) => { const u = create.call(URL, o); live.set(u, o); return u; };
  URL.revokeObjectURL = (u) => { live.delete(u); revoke.call(URL, u); };
  const canvas = document.createElement("canvas");
  window.T = {
    log: [],
    code(v) {
      const w = v.videoWidth, h = v.videoHeight;
      if (v.readyState < 2 || !w) return 0;
      canvas.width = w; canvas.height = h;
      const g = canvas.getContext("2d", {willReadFrequently: true});
      g.drawImage(v, 0, 0);
      const row = g.getImageData(0, Math.floor(ROW * h), w, 1).data;
      let c = 0;
      for (let b = 0; b < CELLS; b++) if (row[4 * Math.floor((b + 0.5) * w / CELLS)] > 128) c |= 1 << b;
      return c;
    },
    video() {  // the video the viewer sees at the stage's centre, or null
      const s = document.getElementById("stage").getBoundingClientRect();
      const v = document.elementFromPoint(s.x + s.width / 2, s.y + s.height / 2);
      return v instanceof HTMLVideoElement ? v : null;
    },
    top() {
      const v = T.video();
      return v && {code: T.code(v), ended: v.ended, paused: v.paused};
    },
    watch() {  // the front video at every change to the stage, before the browser paints it: [code, is it new]
      new MutationObserver(() => { const v = T.video(); T.log.push(v ? [T.code(v), v !== T.old] : [-1, true]); })
        .observe(document.getElementById("stage"), {subtree: true, childList: true, attributes: true});
    },
    async liveBeats() {
      const clips = [...document.querySelectorAll('script[type="application/octet-stream"]')].map((s) => atob(s.textContent));
      const out = [];
      for (const blob of live.values()) {
        const bytes = new Uint8Array(await blob.arrayBuffer());
        out.push(clips.findIndex((c) => c.length === bytes.length && [...bytes].every((x, k) => x === c.charCodeAt(k))));
      }
      return out.sort((a, b) => a - b);
    },
  };
}"""
PAGE_JS = f"({_PAGE})({ROW}, {CELLS});"


class Player:
    """One exported page in one browser, observed only through the stage's pixels, the DOM and the Blob ledger."""

    def __init__(self, page):
        self.page = page

    def front(self) -> tuple[int, int] | None:
        """(beat index, frame index) shown at the stage's centre."""
        t = self.page.evaluate("T.top()")
        return None if t is None or t["code"] == 0 else ((t["code"] >> 8) - 1, t["code"] & 255)

    def settle(self, beat: int, frame: int | None = None) -> None:
        """Wait until the front video shows `beat` (and exactly `frame`, when given)."""
        self.page.wait_for_function(
            "([b, f]) => { const t = T.top(); return t && t.code && (t.code >> 8) === b + 1 && (f === null || (t.code & 255) === f); }",
            arg=[beat, frame],
        )

    def videos(self) -> int:
        return self.page.evaluate("document.querySelectorAll('#stage video').length")

    def transition(self, press, old: int, beat: int, frame: int) -> None:
        """Act, wait for a new element in front showing the target, and check every front video seen at a DOM change
        on the way: the outgoing element shows the outgoing beat, the incoming one shows the target beat and appears on
        `frame` and is never unready (code 0), and there is always a video in front (-1 never). The outgoing one may read
        0 only mid-wrap of its own loop, a seek the browser makes and the player never touches."""
        self.page.evaluate("T.log = []; T.old = T.video()")
        press()
        self.page.wait_for_function("() => T.video() !== T.old")  # the incoming element is in front
        self.settle(beat)
        log = self.page.evaluate("T.log")
        assert all((c >> 8) - 1 == beat if new else c == 0 or (c >> 8) - 1 == old for c, new in log), log
        assert next(c & 255 for c, new in log if new) == frame, log
