from manim_presentations import schedule
from manim_presentations.schedule import Chunk, chunks

# At 7.49 MP (3456×2168) one video second costs 0.082 + 0.103·7.49 = 0.853 s, so CHUNK_COST 20 s of work is ~23.4 s
# of video at the start of a chapter.
MP = 7.49


def test_cuts_are_the_same_for_the_same_inputs():
    plays = {"a": {i: 1.0 for i in range(60)}, "b": {i: 2.0 for i in range(10)}}
    assert chunks(plays, MP) == chunks(dict(plays), MP)


def test_a_long_beat_spreads_across_chunks_at_the_cost_target():
    """One edited beat of 80 one-second plays: cut where render work plus fast-forward reaches 20 s."""
    got = chunks({"a": {i: 1.0 for i in range(80)}}, MP)
    assert len(got) >= 4  # TEST_WORKERS_WIDE: enough work to keep four workers busy
    assert [c.first for c in got] == [0, *[c.last + 1 for c in got[:-1]]]  # contiguous, nothing skipped
    assert got[-1].last == 79
    rate = schedule.render_s_per_video_s(MP)
    for c in got[:-1]:  # every full chunk reached the target at its last play, not one play earlier
        n = c.last - c.first + 1
        assert rate * n + schedule.fast_forward_cost(c.first) >= schedule.CHUNK_COST
        assert rate * (n - 1) + schedule.fast_forward_cost(c.first) < schedule.CHUNK_COST


def test_cuts_fall_at_to_render_run_boundaries_and_never_span_chapters():
    plays = {"a": {0: 1.0, 1: 1.0, 5: 1.0, 6: 1.0}, "b": {0: 1.0}}
    assert chunks(plays, MP) == [Chunk("a", 0, 1), Chunk("a", 5, 6), Chunk("b", 0, 0)]


def test_a_later_start_pays_its_fast_forward():
    near, far = chunks({"a": {i: 1.0 for i in range(40)}}, MP), chunks({"a": {i: 1.0 for i in range(200, 240)}}, MP)
    assert len(far[0:1]) == 1 and (far[0].last - far[0].first) < (near[0].last - near[0].first)
