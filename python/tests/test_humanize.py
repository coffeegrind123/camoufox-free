"""Humanize launch configuration. True or a number is the browser's own engine
(humanize, humanize:maxTime, humanize:engine); a dict runs myuri(), with the
parts it is passed, or raw() per channel in the driver, and the browser is told
only humanize:driver."""


import pytest

from camoufox import utils
from camoufox.humanize import CHANNELS, cursory, myuri, normalize, raw


def noop(*_args, **_kwargs):
    return None


@pytest.fixture
def captured_launch_config(monkeypatch):
    captured = {}

    monkeypatch.setattr(utils, "generate_fingerprint", lambda **_kwargs: object())
    monkeypatch.setattr(utils, "from_fpgen", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(utils, "get_screen_cons", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(
        utils, "_generate_random_font_subset", lambda *_args, **_kwargs: []
    )
    monkeypatch.setattr(
        utils, "draw_voice_config", lambda *_args, **_kwargs: {"voices": []}
    )
    monkeypatch.setattr(utils, "validate_config", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(utils, "add_default_addons", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(utils, "fix_navigator_arch", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        utils, "follow_baseline_protection", lambda *_args, **_kwargs: None
    )
    monkeypatch.setattr(
        utils, "clamp_window_dimensions", lambda *_args, **_kwargs: None
    )
    monkeypatch.setattr(utils, "installed_verstr", lambda *_args, **_kwargs: "152.0")
    monkeypatch.setattr(utils, "launch_path", lambda *_args, **_kwargs: "/camoufox")
    monkeypatch.setattr(utils.LeakWarning, "warn", lambda *_args, **_kwargs: None)

    def capture_env(config, _target_os, **_kwargs):
        captured.clear()
        captured.update(config)
        return {}

    monkeypatch.setattr(utils, "get_env_vars", capture_env)

    def launch(humanize, **kwargs):
        utils.launch_options(
            humanize=humanize,
            block_webgl=True,
            i_know_what_im_doing=True,
            **kwargs,
        )
        return captured.copy()

    return launch


def test_humanize_true_does_not_set_boolean_duration(captured_launch_config) -> None:
    config = captured_launch_config(True)

    assert config["humanize"] is True
    assert "humanize:maxTime" not in config
    assert "humanize:driver" not in config


@pytest.mark.parametrize("duration", [1, 5, 1.25])
def test_humanize_duration_is_encoded_as_double(
    captured_launch_config, duration
) -> None:
    config = captured_launch_config(duration)

    assert config["humanize"] is True
    assert config["humanize:maxTime"] == float(duration)
    assert type(config["humanize:maxTime"]) is float


def test_cursory_is_the_default_engine(captured_launch_config) -> None:
    assert "humanize:engine" not in captured_launch_config(True)


@pytest.mark.parametrize("engine", ["cursory", "mousecrack"])
def test_engine_reaches_the_browser(captured_launch_config, engine) -> None:
    assert captured_launch_config(True, humanize_engine=engine)["humanize:engine"] == engine


def test_unknown_engine_is_refused(captured_launch_config) -> None:
    with pytest.raises(ValueError, match="humanize_engine"):
        captured_launch_config(True, humanize_engine="bezier")


@pytest.mark.parametrize("humanize", [None, {"mouse": myuri()}])
def test_engine_without_the_browsers_humanize_is_refused(captured_launch_config, humanize) -> None:
    # Otherwise the choice would be silently ignored: the browser's engine is off.
    with pytest.raises(ValueError, match="humanize"):
        captured_launch_config(humanize, humanize_engine="mousecrack")


@pytest.mark.parametrize("humanize", [None, False, 0, {"mouse": raw(), "keyboard": raw(), "scroll": raw()}])
def test_nothing_humanized_sends_no_humanize_key(captured_launch_config, humanize) -> None:
    config = captured_launch_config(humanize)
    assert not [key for key in config if key.startswith("humanize")]


@pytest.mark.parametrize(
    "humanize",
    [
        {},
        {"mouse": raw()},
        {"mouse": myuri(move=noop), "keyboard": myuri(type=noop, wpm=70), "scroll": myuri(wheel=noop), "seed": 9},
        {"keyboard": raw(), "seed": 2**32 - 1},
    ],
)
def test_a_driver_engine_tells_the_browser_only_that(captured_launch_config, humanize) -> None:
    config = captured_launch_config(humanize)
    assert {key: value for key, value in config.items() if key.startswith("humanize")} == {"humanize:driver": True}


def test_no_humanize_is_raw_and_the_browsers_engine_leaves_the_driver_raw() -> None:
    for off in (None, False, 0, True, 1.5):
        engines, seed = normalize(off)
        assert engines == {channel: raw() for channel in CHANNELS} and seed is None
    engines, seed = normalize({"scroll": myuri(into_view=noop), "keyboard": {"engine": "myuri", "options": {"wpm": 70}}, "seed": 5})
    assert engines["mouse"] == myuri() and engines["keyboard"] == myuri(wpm=70)
    assert engines["scroll"] == myuri(into_view=noop)
    assert seed == 5


def test_cursory_is_myuri() -> None:
    assert cursory() == myuri() and cursory(move=noop) == myuri(move=noop)
    engines, _seed = normalize({"mouse": {"engine": "cursory", "options": {"move": noop}}, "scroll": cursory()})
    assert engines == {"mouse": myuri(move=noop), "keyboard": myuri(), "scroll": myuri()}


@pytest.mark.parametrize("humanize", [{"mouse": "cursory"}, {"mouse": {"engine": "auto", "options": {}}}])
def test_a_channel_takes_only_an_engine(humanize) -> None:
    with pytest.raises(ValueError, match="is not an engine"):
        normalize(humanize)


def test_a_negative_duration_is_refused(captured_launch_config) -> None:
    with pytest.raises(ValueError, match="positive number of seconds"):
        captured_launch_config(-1.5)


@pytest.mark.parametrize(
    "humanize, message",
    [
        ({"touch": raw()}, "no channel"),
        ({"seed": -1}, "seed"),
        ({"seed": 2**32}, "seed"),
        ({"seed": True}, "seed"),
        ({"seed": "1"}, "seed"),
        ({"mouse": 3}, "is not an engine"),
        ({"mouse": {"engine": "myuri", "options": {"speed": 1}}}, r"myuri\(\) has no part 'speed'"),
        ({"mouse": {"engine": "cursory", "options": {"maxTime": 1}}}, r"myuri\(\) has no part 'maxTime'"),
        ({"mouse": myuri(type=noop)}, r'humanize\["mouse"\]: myuri\(type=...\) is not a mouse part'),
        ({"mouse": {"engine": "myuri", "options": {"wpm": 70}}}, r"myuri\(wpm=...\) is not a mouse part"),
        ({"keyboard": {"engine": "myuri", "options": {"type": "fast"}}}, "takes the function that replaces the part"),
        ({"mouse": {"engine": "custom", "fn": noop}}, "is not an engine"),
        ({"mouse": {"engine": "raw", "options": {"speed": 1}}}, "takes no options"),
    ],
)
def test_malformed_settings_are_refused(humanize, message) -> None:
    with pytest.raises(ValueError, match=message):
        normalize(humanize)
