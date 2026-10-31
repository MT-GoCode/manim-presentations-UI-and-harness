"""--transcript none|narration|full: exactly the text each mode allows, anywhere in the file; and the panel: it follows
the position, a click jumps, a toggle hides it, and it sits beside the video on a wide window and below it on a tall
one."""

import base64
import re

from frames import manifest

pytest_plugins = ["frames_plugin"]  # the built, exported frames talk and the browsers

# The frames talk's script.md, verbatim: what is spoken, and the private notes.
NARRATION = [f"Narration of beat {x}, spoken aloud." for x in "ABCD"]
NOTES = ["Private note on beat A.", "Private note on beat C."]


def everywhere(html: str) -> str:
    """The page's text plus every embedded block decoded, so nothing hidden in a block escapes the search."""
    blocks = re.findall(r'<script type="application/octet-stream" id="clip-\d+">(.*?)</script>', html, re.S)
    return html + "".join(base64.b64decode(b).decode("latin-1") for b in blocks)


def test_each_transcript_mode_carries_exactly_its_text(exported):
    text = {mode: everywhere(exported(mode).read_text()) for mode in ("none", "narration", "full")}
    assert not any(line in text["none"] for line in NARRATION + NOTES)
    assert all(line in text["narration"] for line in NARRATION)
    assert not any(line in text["narration"] for line in NOTES)
    assert all(line in text["full"] for line in NARRATION + NOTES)
    beats = manifest(exported("full").read_text())["beats"]
    assert [b["notes"] for b in beats] == ["Private note on beat A.", "", "Private note on beat C.", ""]


def test_without_a_transcript_there_is_no_panel_and_no_toggle(open_player):
    p = open_player("none")
    assert p.page.evaluate("[document.getElementById('transcript'), document.getElementById('toggle')]") == [None, None]


def current(p) -> str | None:
    return p.page.evaluate("document.querySelector('#transcript section.current h3')?.textContent ?? null")


def test_the_current_beat_is_highlighted_and_scrolled_into_view(open_player):
    p = open_player("full", (960, 300))  # short, so the panel must scroll to show the last beat
    assert p.page.evaluate("(e => e.scrollHeight > e.clientHeight)(document.getElementById('transcript'))")
    assert current(p) == "Beat A"  # Before shows beat 0
    titles = ["Beat A", "Beat B </script> ends no script", "Beat C loops", "d"]
    for i, title in enumerate(titles):
        p.transition(lambda: p.page.keyboard.press("ArrowDown"), max(i - 1, 0), i, 0)
        assert current(p) == title
    inside = """() => { const e = document.querySelector('#transcript section.current').getBoundingClientRect(),
                        panel = document.getElementById('transcript').getBoundingClientRect();
                        return e.top >= panel.top - 1 && e.bottom <= panel.bottom + 1; }  // sub-pixel rounding"""
    assert p.page.evaluate(inside)
    p.transition(lambda: p.page.keyboard.press("ArrowUp"), 3, 2, 0)
    assert current(p) == "Beat C loops" and p.page.evaluate(inside)


def test_clicking_an_entry_shows_that_beat_as_last_seen(open_player):
    p = open_player("narration")
    p.transition(lambda: p.page.click("#transcript section:nth-of-type(2)"), 0, 1, 29)  # beat b's last frame
    assert current(p) == "Beat B </script> ends no script" and p.front() == (1, 29)
    assert p.page.evaluate("document.querySelectorAll('#transcript p.note').length") == 0  # narration: no notes


def box(p, sel: str) -> dict:
    return p.page.evaluate(
        f"(() => {{ const r = document.querySelector('{sel}').getBoundingClientRect(); return {{x: r.x, y: r.y, r: r.right, b: r.bottom, w: r.width}}; }})()"
    )


def test_the_panel_sits_beside_the_video_when_wide_and_below_when_tall_and_the_toggle_hides_it(open_player):
    wide = open_player("full", (1600, 900))
    stage, panel = box(wide, "#stage"), box(wide, "#transcript")
    assert panel["x"] >= stage["r"] - 1 and abs(panel["y"] - stage["y"]) <= 1 and abs(panel["b"] - stage["b"]) <= 1
    wide.page.click("#toggle")
    assert not wide.page.is_visible("#transcript") and box(wide, "#stage")["w"] > stage["w"]
    wide.page.click("#toggle")
    assert wide.page.is_visible("#transcript")
    tall = open_player("full", (600, 1000))
    stage, panel = box(tall, "#stage"), box(tall, "#transcript")
    assert panel["y"] >= stage["b"] - 1 and abs(panel["x"] - stage["x"]) <= 1
