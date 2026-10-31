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
# bytes, not by anything the player says, plus the order of Blob creations and play() calls against the swap.
_PAGE = """(ROW, CELLS) => {
  const live = new Map(), create = URL.createObjectURL, revoke = URL.revokeObjectURL;
  URL.createObjectURL = (o) => { const u = create.call(URL, o); live.set(u, o); T.made.push([o, T.early()]); return u; };
  const play = HTMLMediaElement.prototype.play;
  HTMLMediaElement.prototype.play = function () { T.made.push(["play", T.early()]); return play.call(this); };
  URL.revokeObjectURL = (u) => { live.delete(u); revoke.call(URL, u); };
  const canvas = document.createElement("canvas");
  window.T = {
    log: [],
    made: [],  // [Blob or "play", made while the outgoing element was still in front], in order
    early() { return T.old !== undefined && T.video() === T.old; },
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
    watch() {  // the front video at every change to the stage, before the browser paints it:
      // [code, is it the incoming element, is it seeking, is its source a live Blob URL]
      new MutationObserver(() => {
        const v = T.video();
        T.log.push(v ? [T.code(v), v !== T.old, v.seeking, live.has(v.src)] : [-1, true, false, false]);
      })
        .observe(document.getElementById("stage"), {subtree: true, childList: true, attributes: true});
    },
    async beats(blobs) {  // which clip each Blob holds, by its bytes
      const clips = [...document.querySelectorAll('script[type="application/octet-stream"]')].map((s) => atob(s.textContent));
      const out = [];
      for (const blob of blobs) {
        const bytes = new Uint8Array(await blob.arrayBuffer());
        out.push(clips.findIndex((c) => c.length === bytes.length && [...bytes].every((x, k) => x === c.charCodeAt(k))));
      }
      return out;
    },
    async liveBeats() { return (await T.beats(live.values())).sort((a, b) => a - b); },
    async madeLog() {  // [beat index or "play", early], in order
      const beats = await T.beats(T.made.filter(([o]) => o !== "play").map(([o]) => o));
      return T.made.map(([o, early]) => [o === "play" ? "play" : beats.shift(), early]);
    },
  };
}"""
PAGE_JS = f"({_PAGE})({ROW}, {CELLS});"


# The frames talk's script.md, verbatim: what is spoken, and the private notes.
NARRATION = [f"Narration of beat {x}, spoken aloud." for x in "ABCD"]
NOTES = ["Private note on beat A.", "Private note on beat C."]


def everywhere(html: str) -> str:
    """The page's text plus every embedded block decoded, so nothing hidden in a block escapes a search."""
    return html + "".join(c.decode("latin-1") for c in clips(html))


class Player:
    """One exported page in one browser, observed only through the stage's pixels, the DOM and the Blob ledger."""

    def __init__(self, page, errors: list[str]):
        self.page, self.errors = page, errors  # errors: the page's uncaught errors; none may be left at teardown

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
        on the way: always a video in front, from a live Blob URL; the outgoing element shows the outgoing beat; the
        incoming one shows the target beat and appears on `frame`. Neither is ever unreadable (code 0). The outgoing
        one never moves back (held or ended it stays, playing it advances), except an outgoing loop: it wraps, and while
        it seeks back to its start it may be unreadable — a seek the browser makes, never the player."""
        before, loops = self.page.evaluate(
            f"T.log = []; T.old = T.video(); [T.code(T.old), M.beats[{old}].kind === 'loop']"
        )
        press()
        self.page.wait_for_function("() => T.video() !== T.old")  # the incoming element is in front
        self.settle(beat)
        log = self.page.evaluate("T.log")
        assert all(c != -1 and live for c, _, _, live in log), log
        assert all(c > 0 and (c >> 8) - 1 == beat for c, new, _, _ in log if new), log
        outgoing = [(c, seeking) for c, new, seeking, _ in log if not new]
        if loops:
            assert all((c == 0 and seeking) or (c >> 8) - 1 == old for c, seeking in outgoing), log
        else:
            assert all((c >> 8) - 1 == old and c >= before for c, _ in outgoing), (before, log)
        assert next(c & 255 for c, new, _, _ in log if new) == frame, log
