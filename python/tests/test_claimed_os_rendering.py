"""Rendering answers that come from the host must follow the claimed OS instead.

A Linux build lays text out with its own font prefs, fallback table and
FreeType metrics. When the identity claims another OS, the launcher sets that
OS's values; when it claims the host's own, nothing changes. Expected values
were measured on stock Firefox 152.0.4 on Windows 10 against this build on a
Linux host claiming Windows (2026-09-24).
"""

import pytest

from camoufox import fingerprints as fp
from camoufox import utils

from test_launch_environment import isolated_launch_dependencies  # noqa: F401

WIN_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:156.0) Gecko/20100101 Firefox/156.0"
MAC_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:156.0) Gecko/20100101 Firefox/156.0"
LIN_UA = "Mozilla/5.0 (X11; Linux x86_64; rv:156.0) Gecko/20100101 Firefox/156.0"


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


def test_a_caller_user_agent_alone_still_fixes_the_drawn_platform(
    launch, monkeypatch
):
    """A Linux draw can carry another OS's platform beside its Linux oscpu.
    The caller set only the user agent, so platform and oscpu follow it."""
    monkeypatch.setattr(utils, "from_fpgen", fp.from_fpgen)
    monkeypatch.setattr(utils, "fix_navigator_arch", fp.fix_navigator_arch)
    fingerprint = fp.generate_fingerprint(os="linux")
    fingerprint["navigator"]["platform"] = "Win32"
    config, _ = launch(LIN_UA, fingerprint=fingerprint)

    assert config["navigator.platform"] == "Linux x86_64"
    assert config["navigator.oscpu"] == "Linux x86_64"


def test_a_callers_platform_is_kept_when_the_user_agent_is_set(
    launch, monkeypatch
):
    monkeypatch.setattr(utils, "fix_navigator_arch", fp.fix_navigator_arch)
    config, _ = launch(
        LIN_UA, config={"navigator.platform": "Linux i686"}
    )

    assert config["navigator.platform"] == "Linux i686"


class TestFontPrefs:
    """font.* defaults of the claimed OS, from font-prefs.json."""

    def test_windows_identity_gets_windows_font_prefs(self, launch):
        _, prefs = launch(WIN_UA)
        assert prefs["font.name-list.emoji"].startswith("Segoe UI Emoji")
        assert prefs["font.name-list.serif.th"] == "Tahoma"
        # A name-list only Linux sets is emptied rather than left to Linux.
        assert prefs["font.name-list.cursive.ja"] == ""

    def test_macos_identity_gets_macos_font_prefs(self, launch):
        _, prefs = launch(MAC_UA)
        assert prefs["font.name-list.serif.th"] == "Thonburi"

    def test_async_fallback_off_on_a_linux_host(self, launch):
        for ua in (WIN_UA, MAC_UA, LIN_UA):
            _, prefs = launch(ua)
            assert prefs["gfx.font_rendering.fallback.async"] is False

    def test_linux_identity_on_linux_host_is_left_alone(self, launch):
        _, prefs = launch(LIN_UA)
        assert "font.name-list.emoji" not in prefs

    def test_windows_identity_on_windows_host_is_left_alone(self, launch, monkeypatch):
        monkeypatch.setattr(utils, "_host_os_key", lambda: "win")
        _, prefs = launch(WIN_UA)
        assert "font.name-list.emoji" not in prefs
        assert "gfx.font_rendering.fallback.async" not in prefs

    def test_caller_pref_wins(self, launch):
        _, prefs = launch(WIN_UA, firefox_user_prefs={"font.name-list.serif.th": "Garuda"})
        assert prefs["font.name-list.serif.th"] == "Garuda"

    def test_table_matches_stock_firefox(self):
        # Spot checks against all.js, so a regeneration cannot quietly agree
        # with itself.
        prefs = utils._stock_font_prefs("win", "lin")
        assert prefs["font.name-list.serif.x-western"] == "Times New Roman"
        assert prefs["font.name-list.sans-serif.ko"] == "Malgun Gothic, Gulim, Noto Sans CJK KR, Noto Sans KR"


class TestFontMetrics:
    """fonts:metrics "windows": DirectWrite's line boxes on a FreeType host."""

    def test_windows_identity_gets_windows_metrics(self, launch):
        config, _ = launch(WIN_UA)
        assert config["fonts:metrics"] == "windows"

    @pytest.mark.parametrize("ua", [MAC_UA, LIN_UA])
    def test_other_identities_keep_freetype_metrics(self, launch, ua):
        config, _ = launch(ua)
        assert "fonts:metrics" not in config

    def test_windows_host_is_left_alone(self, launch, monkeypatch):
        monkeypatch.setattr(utils, "_host_os_key", lambda: "win")
        config, _ = launch(WIN_UA)
        assert "fonts:metrics" not in config

    def test_caller_value_wins(self, launch):
        config, _ = launch(WIN_UA, config={"fonts:metrics": "freetype"})
        assert config["fonts:metrics"] == "freetype"


class TestCodecs:
    """The codec matrix and decodingInfo() follow the claimed OS (#558)."""

    def test_windows_identity_claims_windows_codecs(self, launch):
        config, _ = launch(WIN_UA)
        assert config["media:spoof_codecs"] is True
        assert config["media:hwCodecs"] == ["video/avc", "video/hevc", "video/vp9"]

    def test_macos_identity_claims_codecs_without_windows_hardware(self, launch):
        config, _ = launch(MAC_UA)
        assert config["media:spoof_codecs"] is True
        assert "media:hwCodecs" not in config

    def test_host_os_identity_is_left_alone(self, launch, monkeypatch):
        config, _ = launch(LIN_UA)
        assert "media:spoof_codecs" not in config
        monkeypatch.setattr(utils, "_host_os_key", lambda: "win")
        config, _ = launch(WIN_UA)
        assert "media:spoof_codecs" not in config
        assert "media:hwCodecs" not in config

    def test_caller_values_win(self, launch):
        config, _ = launch(WIN_UA, config={"media:spoof_codecs": False, "media:hwCodecs": []})
        assert config["media:spoof_codecs"] is False
        assert config["media:hwCodecs"] == []


class TestLookAndFeel:
    """Glyph positioning and system colours of the claimed OS."""

    def test_windows_identity_gets_windows_look_and_feel(self, launch):
        _, prefs = launch(WIN_UA)
        assert prefs["gfx.text.subpixel-position.force-enabled"] is True
        assert utils.WINDOWS_UI_COLORS["ui.highlight"] == "#0078d7"
        for pref, value in utils.WINDOWS_UI_COLORS.items():
            assert prefs[pref] == value

    def test_macos_identity_gets_subpixel_only(self, launch):
        _, prefs = launch(MAC_UA)
        assert prefs["gfx.text.subpixel-position.force-enabled"] is True
        assert "ui.highlight" not in prefs

    def test_host_os_identity_is_left_alone(self, launch, monkeypatch):
        _, prefs = launch(LIN_UA)
        assert "gfx.text.subpixel-position.force-enabled" not in prefs
        assert "ui.highlight" not in prefs
        monkeypatch.setattr(utils, "_host_os_key", lambda: "win")
        _, prefs = launch(WIN_UA)
        assert "gfx.text.subpixel-position.force-enabled" not in prefs
        assert "ui.highlight" not in prefs

    def test_caller_values_win(self, launch):
        _, prefs = launch(WIN_UA, firefox_user_prefs={
            "ui.highlight": "#ff0000", "gfx.text.subpixel-position.force-enabled": False,
        })
        assert prefs["ui.highlight"] == "#ff0000"
        assert prefs["gfx.text.subpixel-position.force-enabled"] is False
