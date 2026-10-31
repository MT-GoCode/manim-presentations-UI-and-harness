"""The exported player in headless WebKit and Chrome, observed through the frame codes on screen: the Position model,
what every transition shows and that nothing else is shown on the way, loops, held last frames, the Blob window, and
the controls. The frames talk: beats a, b, c (a loop), d; frame k of beat index i shows code (i+1) << 8 | k."""

import itertools
import json

import pytest
from conftest import REPO, TESTS
from frames import manifest

pytest_plugins = ["frames_plugin"]  # the built, exported frames talk and the browsers

LOOP = 2


@pytest.fixture
def frames(page_file):
    beats = manifest(page_file.read_text())["beats"]
    assert [b["kind"] for b in beats] == ["beat", "beat", "loop", "beat"]
    return [b["frames"] for b in beats]


def press(player, key):
    return lambda: player.page.keyboard.press(key)


def test_the_page_steps_positions_exactly_as_the_position_table(player):
    table = json.loads((TESTS / "position_table.json").read_text())
    for row in table["steps"]:
        got = player.page.evaluate("([p, a, s]) => step(p, a, s)", [row["from"], row["action"], table["slugs"]])
        assert got == ({"kind": "boundary"} if row["to"] == "boundary" else {"kind": "moved", "position": row["to"]}), (
            row
        )


def test_every_transition_shows_the_right_frame_and_nothing_else_on_the_way(player, browser, frames):
    shots = REPO / "test-results" / "export" / browser.browser_type.name
    shots.mkdir(parents=True, exist_ok=True)
    old = 0  # Before shows beat 0
    for beat in range(4):  # Next plays from frame 0, shown before the outgoing video hides
        player.transition(press(player, "ArrowDown"), old, beat, 0)
        player.page.wait_for_function("() => (T.top().code & 255) > 0")  # and then it plays
        player.page.screenshot(path=shots / f"{beat + 1}-next-{beat}.png")
        old = beat
    for beat, frame in ((2, 0), (1, frames[1] - 1), (0, frames[0] - 1)):  # Previous: as last seen (the loop runs)
        player.transition(press(player, "ArrowUp"), old, beat, frame)
        if beat != LOOP:
            assert player.front() == (beat, frame)
        player.page.screenshot(path=shots / f"{8 - beat}-previous-{beat}.png")
        old = beat
    player.transition(press(player, "ArrowUp"), 0, 0, 0)  # At(0) → Before: beat 0's first frame
    assert player.front() == (0, 0) and player.videos() == 1


def test_a_boundary_flashes_and_changes_nothing(player):
    player.page.keyboard.press("ArrowUp")  # Previous at Before
    assert player.page.evaluate("document.body.classList.contains('boundary')")
    assert player.videos() == 1 and player.front() == (0, 0)


def test_a_played_beat_ends_on_its_last_frame_and_a_loop_keeps_looping(player, frames):
    player.transition(press(player, "ArrowDown"), 0, 0, 0)
    player.page.wait_for_function("() => T.top().ended")
    assert player.front() == (0, frames[0] - 1)
    for beat in (1, 2):
        player.transition(press(player, "ArrowDown"), beat - 1, beat, 0)
    seen = player.page.evaluate(  # every frame code shown over 2.75× the loop's length (0.8 s)
        """() => new Promise((done) => { const codes = [], t0 = performance.now();
            const tick = () => { codes.push(T.top().code); performance.now() - t0 < 2200 ? requestAnimationFrame(tick) : done(codes); };
            tick(); })"""
    )
    seen = [c for c in seen if c]  # 0: unreadable for a moment while the browser seeks back to the start
    assert all(c >> 8 == LOOP + 1 for c in seen), [hex(c) for c in seen if c >> 8 != LOOP + 1]
    assert any(b < a for a, b in itertools.pairwise(seen)), seen  # it wrapped
    assert not player.page.evaluate("T.top().paused")


def test_presses_faster_than_the_player_land_once_on_the_last(player):
    player.page.evaluate("T.log = []")
    player.page.evaluate(
        "for (let i = 0; i < 3; i++) document.dispatchEvent(new KeyboardEvent('keydown', {key: 'ArrowDown'}))"
    )
    player.settle(2, None)
    assert {(c >> 8) - 1 for c, _ in player.page.evaluate("T.log")} <= {0, 2}  # beat 1 was never raised
    player.page.wait_for_function("() => document.querySelectorAll('#stage video').length === 1")


def test_replay_and_jumps_show_the_beat_as_the_presenter_would(player, frames):
    player.transition(press(player, "ArrowDown"), 0, 0, 0)
    player.page.wait_for_function("() => T.top().ended")
    player.transition(press(player, "KeyR"), 0, 0, 0)  # Replay: from frame 0 again
    player.transition(lambda: player.page.select_option("#jump", "d"), 0, 3, frames[3] - 1)  # far ahead: last frame
    player.transition(lambda: player.page.select_option("#jump", "b"), 3, 1, frames[1] - 1)
    player.page.evaluate("T.log = []")
    player.transition(lambda: player.page.select_option("#jump", "b"), 1, 1, frames[1] - 1)  # the beat on screen
    assert player.front() == (1, frames[1] - 1) and player.videos() == 1


def test_blob_urls_exist_for_the_current_beat_and_its_neighbours_only(player, frames):
    def live():
        return player.page.evaluate("T.liveBeats()")

    assert live() == [0, 1]  # Before: beat 0 and its neighbour
    old = 0
    for beat in range(4):
        player.transition(press(player, "ArrowDown"), old, beat, 0)
        assert live() == [i for i in range(4) if abs(i - beat) <= 1], beat
        old = beat
    player.transition(lambda: player.page.select_option("#jump", "a"), 3, 0, frames[0] - 1)
    assert live() == [0, 1]


def test_buttons_and_clicker_keys_act_like_the_arrows_and_auto_repeat_does_nothing(player, frames):
    player.transition(lambda: player.page.click("#next"), 0, 0, 0)
    player.transition(press(player, "PageDown"), 0, 1, 0)
    player.transition(press(player, "PageUp"), 1, 0, frames[0] - 1)
    player.transition(lambda: player.page.click("#replay"), 0, 0, 0)
    player.transition(press(player, "Shift+KeyR"), 0, 0, 0)  # Qt's Key_R is R with or without Shift
    player.transition(lambda: player.page.click("#previous"), 0, 0, 0)  # Before
    held = "document.dispatchEvent(new KeyboardEvent('keydown', {key: 'ArrowDown', repeat: true}))"
    assert player.page.evaluate(f"() => {{ {held}; return document.querySelectorAll('#stage video').length; }}") == 1
    assert player.front() == (0, 0)
