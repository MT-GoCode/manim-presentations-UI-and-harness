import pytest

from manim_presentations.settings import Settings, SettingsError, load


def talk(tmp_path, toml: str | None):
    if toml is not None:
        (tmp_path / "talk.toml").write_text(toml)
    return tmp_path


def test_defaults_without_talk_toml(tmp_path):
    s = load(talk(tmp_path, None))
    assert (s.pixel_width, s.pixel_height, s.frame_rate, s.background) == (1920, 1080, 30, "#000000")
    assert s.frame_width == pytest.approx(8 * 1920 / 1080)
    assert s.min_text == pytest.approx(32 / 960 / 8) and s.min_tex == pytest.approx(40 / 960 / 8)


def test_override_with_origin(tmp_path):
    s = load(
        talk(tmp_path, '[render]\npixel_width = 3456\npixel_height = 2168\nframe_width = 16\norigin = "measured"\n')
    )
    assert (s.pixel_width, s.pixel_height, s.frame_width) == (3456, 2168, 16.0)


@pytest.mark.parametrize(
    "toml",
    [
        "[render]\nframe_rate = 60\n",
        '[render]\nframe_rate = 60\norigin = "  "\n',
        "[checks]\nmin_text = 0.01\n",
    ],
)
def test_override_without_origin_is_refused_with_an_example(tmp_path, toml):
    with pytest.raises(SettingsError, match="without an `origin`") as e:
        load(talk(tmp_path, toml))
    assert 'origin = "' in str(e.value)  # a paste-ready example


def test_explicit_zero_is_an_override_not_a_default(tmp_path):
    with pytest.raises(SettingsError, match="without an `origin`"):
        load(talk(tmp_path, "[checks]\nmin_text = 0\n"))
    s = load(talk(tmp_path, '[checks]\nmin_text = 0\norigin = "no minimum"\n'))
    assert s.min_text == 0


@pytest.mark.parametrize(
    "toml",
    [
        '[render]\npixel_width = 1921\norigin = "x"\n',
        '[render]\npixel_hieght = 1080\norigin = "x"\n',
        "[render\n",
    ],
)
def test_bad_talk_toml_is_refused(tmp_path, toml):
    with pytest.raises(SettingsError):
        load(talk(tmp_path, toml))


def test_argv_round_trip(tmp_path):
    s = load(talk(tmp_path, '[render]\nframe_rate = 24\norigin = "film"\n'))
    assert Settings.from_argv(s.to_argv()) == s
