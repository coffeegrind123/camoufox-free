"""A Windows identity on another host behaves as stock Windows Firefox does.

What was measured on stock Firefox on Windows against this build on a Linux
host claiming Windows: the math (browser/tests/ucrt-math), the keyboard (the
windows-keyboard guard), the scrollbar width, and four behaviour prefs
(middlemouse.paste, general.autoScroll, eat_space_to_next_word and the
fullscreen transition, the spot checks below). The other behaviour prefs are
Firefox 158's Windows defaults, read from all.js, firefox.js and
StaticPrefList.yaml, not measured. On a Windows host the build already behaves
that way, and a macOS or Linux identity is left as it is.
"""

import pytest

from camoufox import fingerprints, utils

from test_launch_environment import isolated_launch_dependencies  # noqa: F401

WIN_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:158.0) Gecko/20100101 Firefox/158.0"
MAC_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:158.0) Gecko/20100101 Firefox/158.0"
LIN_UA = "Mozilla/5.0 (X11; Linux x86_64; rv:158.0) Gecko/20100101 Firefox/158.0"


@pytest.fixture
def launch(monkeypatch, isolated_launch_dependencies):  # noqa: F811
    """launch_options on a Linux host; returns (config, prefs)."""
    monkeypatch.setattr(utils, "_host_os_key", lambda: "lin")
    seen = {}

    def capture(config, *args, **kwargs):
        seen["config"] = dict(config)
        return {}

    monkeypatch.setattr(utils, "get_env_vars", capture)

    def run(ua, **kwargs):
        config = {"navigator.userAgent": ua, **kwargs.pop("config", {})}
        prefs = utils.launch_options(config=config, i_know_what_im_doing=True, **kwargs)["firefox_user_prefs"]
        return seen["config"], prefs

    return run


def test_windows_identity_gets_windows_crt_math(launch):
    _, prefs = launch(WIN_UA)
    assert prefs["javascript.options.use_ucrt_math"] is True


@pytest.mark.parametrize("ua", [MAC_UA, LIN_UA])
def test_other_identities_keep_host_math(launch, ua):
    _, prefs = launch(ua)
    assert "javascript.options.use_ucrt_math" not in prefs


def test_windows_identity_on_windows_host_is_left_alone(launch, monkeypatch):
    monkeypatch.setattr(utils, "_host_os_key", lambda: "win")
    _, prefs = launch(WIN_UA)
    assert "javascript.options.use_ucrt_math" not in prefs


def test_caller_values_win(launch):
    _, prefs = launch(WIN_UA, firefox_user_prefs={"javascript.options.use_ucrt_math": False})
    assert prefs["javascript.options.use_ucrt_math"] is False


def test_windows_identity_gets_windows_keyboard(launch):
    config, _ = launch(WIN_UA)
    assert config["input:windowsKeyboard"] is True


@pytest.mark.parametrize("ua", [MAC_UA, LIN_UA])
def test_other_identities_keep_host_keyboard(launch, ua):
    config, _ = launch(ua)
    assert "input:windowsKeyboard" not in config


def test_windows_keyboard_on_windows_host_is_left_alone(launch, monkeypatch):
    monkeypatch.setattr(utils, "_host_os_key", lambda: "win")
    config, _ = launch(WIN_UA)
    assert "input:windowsKeyboard" not in config


def test_caller_keyboard_wins(launch):
    config, _ = launch(WIN_UA, config={"input:windowsKeyboard": False})
    assert config["input:windowsKeyboard"] is False


def test_windows_identity_gets_windows_behaviour(launch):
    _, prefs = launch(WIN_UA)
    for pref, value in utils.WINDOWS_BEHAVIOUR_PREFS.items():
        assert prefs[pref] == value
    # Spot checks against stock Firefox on Windows, so an edit to the table
    # cannot quietly agree with itself.
    assert prefs["media.eme.enabled"] is True
    assert prefs["middlemouse.paste"] is False
    assert prefs["general.autoScroll"] is True
    assert prefs["layout.word_select.eat_space_to_next_word"] is True
    assert prefs["full-screen-api.transition-duration.enter"] == "200 200"


@pytest.mark.parametrize("ua", [MAC_UA, LIN_UA])
def test_other_identities_keep_host_behaviour(launch, ua):
    _, prefs = launch(ua)
    assert not set(utils.WINDOWS_BEHAVIOUR_PREFS) & set(prefs)


def test_windows_behaviour_on_windows_host_is_left_alone(launch, monkeypatch):
    monkeypatch.setattr(utils, "_host_os_key", lambda: "win")
    _, prefs = launch(WIN_UA)
    assert not set(utils.WINDOWS_BEHAVIOUR_PREFS) & set(prefs)


def test_caller_behaviour_wins(launch):
    _, prefs = launch(WIN_UA, firefox_user_prefs={"middlemouse.paste": True})
    assert prefs["middlemouse.paste"] is True


@pytest.mark.parametrize("ua, enabled", [(WIN_UA, True), (LIN_UA, True), (MAC_UA, False)])
def test_wheel_override_follows_the_identity(launch, ua, enabled):
    _, prefs = launch(ua)
    assert prefs["mousewheel.system_scroll_override.enabled"] is enabled


# Scrollbars are drawn by the host build's theme: GTK's are 12 px where stock
# Windows measures 17 (classic, ui.useOverlayScrollbars 0), so a Windows 10
# identity on a Linux host showed a 12 px gutter.
SCROLLBAR_STYLE = "widget.non-native-theme.scrollbar.style"


@pytest.mark.parametrize(
    "overlay, style",
    [pytest.param(0, 4, id="windows-10-classic"), pytest.param(1, 5, id="windows-11-overlay")],
)
def test_windows_identity_draws_windows_scrollbars(launch, overlay, style):
    _, prefs = launch(WIN_UA, firefox_user_prefs={"ui.useOverlayScrollbars": overlay})
    assert prefs[SCROLLBAR_STYLE] == style


@pytest.mark.parametrize("ua", [MAC_UA, LIN_UA])
def test_other_identities_keep_host_scrollbars(launch, ua):
    _, prefs = launch(ua)
    assert SCROLLBAR_STYLE not in prefs


def test_scrollbars_on_a_windows_host_are_left_alone(launch, monkeypatch):
    monkeypatch.setattr(utils, "_host_os_key", lambda: "win")
    _, prefs = launch(WIN_UA)
    assert SCROLLBAR_STYLE not in prefs


def test_caller_scrollbar_style_wins(launch):
    _, prefs = launch(WIN_UA, firefox_user_prefs={SCROLLBAR_STYLE: 2})
    assert prefs[SCROLLBAR_STYLE] == 2


FRAME_KEYS = ("Left", "Top", "Right", "Bottom")


def frame_of(config):
    return tuple(config.get(f"window.frame{key}") for key in FRAME_KEYS)


def test_windows_identity_gets_stock_windows_window_frame(launch):
    config, _ = launch(WIN_UA)
    left, top, right, bottom = frame_of(config)
    # A normal window (8, 85, 8, 8) or a maximized one, whose top border
    # hangs off the screen above the toolbars (8, 93, 8, 8).
    assert (left, right, bottom) == (8, 8, 8)
    assert top in (85, 93)


def test_macos_identity_on_another_host_gets_stock_macos_window_frame(launch):
    config, _ = launch(MAC_UA)
    assert frame_of(config)[0::2] == (0, 0)
    assert frame_of(config)[3] == 0
    assert frame_of(config)[1] in (84, 85)


def test_linux_identity_keeps_the_real_window_frame(launch):
    config, _ = launch(LIN_UA)
    assert not any(key.startswith("window.frame") for key in config)


@pytest.mark.parametrize("host, ua", [("win", WIN_UA), ("mac", MAC_UA)])
def test_an_identity_on_its_own_os_keeps_the_real_window_frame(launch, monkeypatch, host, ua):
    monkeypatch.setattr(utils, "_host_os_key", lambda: host)
    config, _ = launch(ua)
    assert not any(key.startswith("window.frame") for key in config)


def test_a_callers_window_frame_is_kept(launch):
    config, _ = launch(WIN_UA, config={"window.frameTop": 120})
    assert config["window.frameTop"] == 120
    assert config["window.frameLeft"] == 8


def test_a_callers_window_geometry_is_not_maximized(launch):
    geometry = {"screen.width": 1920, "screen.height": 1080, "screen.availWidth": 1920,
                "screen.availHeight": 1032, "window.outerWidth": 1920, "window.outerHeight": 1032,
                "window.screenX": 0, "window.screenY": 0}
    config, _ = launch(WIN_UA, config=geometry)
    assert (config["window.outerWidth"], config["window.screenX"]) == (1920, 0)
    assert frame_of(config) == (8, 85, 8, 8)


def _window(outer, avail=(1920, 1032), position=(0, 0), dpr=None):
    config = {"screen.availLeft": 0, "screen.availTop": 0,
              "screen.availWidth": avail[0], "screen.availHeight": avail[1],
              "window.outerWidth": outer[0], "window.outerHeight": outer[1],
              "window.screenX": position[0], "window.screenY": position[1]}
    if dpr:
        config["window.devicePixelRatio"] = dpr
    return config


def test_a_normal_windows_window_keeps_its_place():
    config = _window((1280, 900), position=(100, 50))
    fingerprints.present_window_frame(config, "win", own_geometry=True)
    assert frame_of(config) == (8, 85, 8, 8)
    assert (config["window.outerWidth"], config["window.screenX"]) == (1280, 100)
    # The browser maximizes it with the top border the frame lacks here
    # (zz-window-presentation.patch); it did not launch maximized.
    assert config["window.frameBorderTop"] == 8
    assert "window.maximized" not in config


def test_a_windows_window_filling_the_available_area_is_maximized():
    # A maximized window at 100% in fpgen's records: outer the available area
    # plus 16x16 at -8,-8, outer - inner 16x101, so on a 1920x1032 work area
    # outer 1936x1048 and content 1920x947 at 0,85.
    config = _window((1920, 1032))
    fingerprints.present_window_frame(config, "win", own_geometry=True)
    assert (config["window.outerWidth"], config["window.outerHeight"]) == (1936, 1048)
    assert (config["window.screenX"], config["window.screenY"]) == (-8, -8)
    assert frame_of(config) == (8, 93, 8, 8)
    content = (1936 - 8 - 8, 1048 - 93 - 8)
    assert content == (1920, 1032 - 85)
    # The launch state, so the browser can show the normal frame once a user's
    # resize leaves the available area (zz-window-presentation.patch).
    assert config["window.maximized"] is True
    assert config["window.frameBorderTop"] == 8


@pytest.mark.parametrize("dpr, outer, frame", [
    (1.25, (1934, 1046), (7, 92, 7, 7)),
    (1.5, (1935, 1047), (7, 92, 8, 8)),
    (2, (1933, 1045), (7, 91, 6, 6)),
])
def test_a_maximized_windows_window_follows_the_display_scale(dpr, outer, frame):
    config = _window((1920, 1032), dpr=dpr)
    fingerprints.present_window_frame(config, "win", own_geometry=True)
    assert (config["window.outerWidth"], config["window.outerHeight"]) == outer
    assert frame_of(config) == frame


def test_a_scale_between_steps_takes_the_nearest():
    config = _window((1280, 900), position=(10, 10), dpr=1.2)
    fingerprints.present_window_frame(config, "win", own_geometry=True)
    assert frame_of(config) == (7, 85, 7, 7)


def test_a_macos_window_is_never_moved():
    config = _window((1440, 875), avail=(1440, 875), dpr=2)
    fingerprints.present_window_frame(config, "mac", own_geometry=True)
    assert frame_of(config) == (0, 84, 0, 0)
    # macOS has no borders off the screen, so nothing moves when it zooms.
    assert "window.frameBorderTop" not in config and "window.maximized" not in config
    assert (config["window.outerWidth"], config["window.screenX"]) == (1440, 0)
