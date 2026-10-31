"""The synthetic 10-minute talk as single-file exports: size, open -> first frame, peak memory, per variant.

Builds html/h{H}_crf{C}.html from out/ with p4_webkit_ci's player, then for each rep: open the file, wait for
Before's first presented frame, press Next through all 57 beats (each incoming beat must present its own
frame 0, read by barcode), then Previous x3 (each must present that beat's last frame). Process-tree memory
is sampled throughout. Holds /tmp/mpres-heavy.lock per run and records the load average.
Usage: uv run p4_talk.py <engine> <reps>
"""

import fcntl
import json
import os
import statistics
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

from p4_webkit_ci import TreeSampler, build_html, launch, open_page

HERE = Path(__file__).parent
HEIGHTS, CRFS = (1080, 720, 540), (20, 23, 28)


def build(h: int, crf: int) -> Path:
    man = json.loads((HERE / "src" / "manifest.json").read_text())
    clips = [((HERE / "out" / f"h{h}_crf{crf}" / f"clip{m['clip']:03d}.mp4").read_bytes(), m["length"], m["loop"]) for m in man]
    p = HERE / "html" / f"h{h}_crf{crf}.html"
    p.parent.mkdir(exist_ok=True)
    p.write_text(build_html(clips))
    return p


def one_run(browser, html: Path, lengths: list[int]) -> dict:
    with TreeSampler() as ts:
        page, ff = open_page(browser, html)
        assert ff["first_code"] == 0, ff
        bad, ms = [], []
        for i in range(len(lengths)):
            e = page.evaluate("P.next()")
            ms.append(e["ms"])
            if i > 0 and e["code"] != i << 16:  # beat 0 was already on frame 0 at Before
                bad.append((i, e["code"]))
        for i in range(len(lengths) - 2, len(lengths) - 5, -1):
            e = page.evaluate("P.prev()")
            ms.append(e["ms"])
            if e["code"] != (i << 16 | (lengths[i] - 1)):
                bad.append((i, e["code"], "last"))
        errs = page.evaluate("ERR")
        page.context.close()
    return {**ff, **ts.report(), "bad": bad, "media_errors": errs, "transition_ms_median": statistics.median(ms),
            "transition_ms_max": max(ms)}


def main() -> None:
    engine, reps = sys.argv[1], int(sys.argv[2])
    lengths = [m["length"] for m in json.loads((HERE / "src" / "manifest.json").read_text())]
    out = HERE / "results" / f"talk_{engine}.json"
    results = []
    with sync_playwright() as pw:
        browser = launch(pw, engine)
        for h in HEIGHTS:
            for crf in CRFS:
                html = build(h, crf)
                runs = []
                for _ in range(reps):
                    with open("/tmp/mpres-heavy.lock", "w") as lk:
                        fcntl.flock(lk, fcntl.LOCK_EX)
                        load0 = os.getloadavg()[0]
                        r = one_run(browser, html, lengths)
                        r["load_before"], r["load_after"] = load0, os.getloadavg()[0]
                    runs.append(r)
                row = {"engine": engine, "version": browser.version, "height": h, "crf": crf, "html_bytes": html.stat().st_size, "runs": runs}
                results.append(row)
                ffm = [x["first_frame_ms_perf"] for x in runs]
                print(f"{engine} h{h} crf{crf}: html {row['html_bytes'] / 2**20:.1f} MiB, first frame median {statistics.median(ffm)} "
                      f"max {max(ffm)} ms, renderer peak {max(x['renderer_peak_rss_mb'] for x in runs)} MB, tree peak "
                      f"{max(x['tree_peak_rss_mb'] for x in runs)} MB, bad {sum(len(x['bad']) for x in runs)}, "
                      f"load {runs[0]['load_before']:.1f}", flush=True)
                out.write_text(json.dumps(results, indent=1))
        browser.close()


if __name__ == "__main__":
    main()
