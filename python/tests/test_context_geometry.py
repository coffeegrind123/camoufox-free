"""NewContext geometry must fit the process-wide launch window (#164)."""

import asyncio
from unittest import mock

import orjson
import pytest

from camoufox.async_api import AsyncNewContext
from camoufox.fingerprints import generate_context_fingerprint, load_presets
from camoufox.sync_api import NewContext
from camoufox.utils import attach_launch_window


LAUNCH_WINDOW = {
    "outer": (1366, 728),
    "inner": (1366, 643),
    "screen": (1366, 768),
}
NO_INNER = {**LAUNCH_WINDOW, "inner": (None, None)}


def test_viewport_is_the_launch_inner_and_the_screen_holds_the_window():
    fingerprint = generate_context_fingerprint(
        os="windows",
        launch_window=LAUNCH_WINDOW,
    )
    viewport = fingerprint["context_options"]["viewport"]
    assert (viewport["width"], viewport["height"]) == LAUNCH_WINDOW["inner"]
    screen_width = fingerprint["config"]["screen.width"]
    screen_height = fingerprint["config"]["screen.height"]
    outer_width, outer_height = LAUNCH_WINDOW["outer"]
    assert screen_width >= outer_width and screen_height >= outer_height
    assert f"w.setScreenDimensions({screen_width}, {screen_height})" in fingerprint["init_script"]


@pytest.mark.parametrize("os_name", ["windows", "macos", "linux"])
def test_no_launch_inner_keeps_the_preset_viewport_inside_the_outer_window_and_its_scale_factor(
    os_name,
):
    outer_width, outer_height = NO_INNER["outer"]
    presets = load_presets()["presets"][os_name]
    small = next(
        preset
        for preset in presets
        if preset["screen"]["width"] < outer_width
        or preset["screen"]["height"] < outer_height
    )
    clamped = 0
    for preset in (presets[0], small):
        options = generate_context_fingerprint(
            preset=preset,
            launch_window=NO_INNER,
        )["context_options"]
        viewport = options["viewport"]
        assert "no_viewport" not in options
        assert viewport["width"] <= outer_width
        assert viewport["height"] <= outer_height
        assert options.get("device_scale_factor") == preset["screen"].get(
            "devicePixelRatio"
        )
        unclamped = (
            preset["screen"]["width"],
            max(preset["screen"]["height"] - 28, 600),
        )
        clamped += (viewport["width"], viewport["height"]) != unclamped
    assert clamped, "no draw exercised the clamp"


def test_attach_launch_window_reads_the_launch_config_and_defaults_outer():
    class Browser:
        pass

    config = {
        "window.innerWidth": 1000,
        "window.innerHeight": 600,
        "screen.width": 1920,
        "screen.height": 1080,
    }
    browser = attach_launch_window(
        Browser(),
        {"env": {"CAMOU_CONFIG_1": orjson.dumps(config).decode()}},
    )
    assert browser._camoufox_launch_window == {
        "outer": (1280, 1040),
        "inner": (1000, 600),
        "screen": (1920, 1080),
        "cores": None,
    }


def test_attach_launch_window_records_the_launch_cores():
    class Browser:
        pass

    config = {"navigator.hardwareConcurrency": 12}
    browser = attach_launch_window(
        Browser(),
        {"env": {"CAMOU_CONFIG_1": orjson.dumps(config).decode()}},
    )
    assert browser._camoufox_launch_window["cores"] == 12


@pytest.mark.parametrize("os_name", ["windows", "macos", "linux"])
def test_a_context_reports_the_launch_cores(os_name):
    """A page can count cores with workers, so a context reports the launch's
    (fix_hardware_concurrency) on both the preset and the synthetic path."""
    launch = {**LAUNCH_WINDOW, "cores": 6}
    for preset in (None, load_presets()["presets"][os_name][0]):
        fingerprint = generate_context_fingerprint(
            os=os_name if preset is None else None, preset=preset, launch_window=launch)
        assert fingerprint["config"]["navigator.hardwareConcurrency"] == 6
        assert "w.setNavigatorHardwareConcurrency(6)" in fingerprint["init_script"]


def test_attach_launch_window_ignores_malformed_config():
    class Browser:
        pass

    browser = Browser()
    assert attach_launch_window(
        browser,
        {"env": {"CAMOU_CONFIG_1": "{"}},
    ) is browser
    assert not hasattr(browser, "_camoufox_launch_window")


def test_new_context_passes_the_launch_window_and_an_explicit_viewport_wins():
    class Context:
        def add_init_script(self, _script):
            pass

    class Browser:
        version = "156.0"
        _camoufox_launch_window = NO_INNER

        def new_context(self, **options):
            self.options = options
            return Context()

    browser = Browser()
    NewContext(browser, os="windows")
    assert "no_viewport" not in browser.options
    assert browser.options["viewport"]["width"] <= NO_INNER["outer"][0]
    assert browser.options["viewport"]["height"] <= NO_INNER["outer"][1]

    NewContext(browser, os="windows", viewport={"width": 800, "height": 600})
    assert browser.options["viewport"] == {"width": 800, "height": 600}
    assert "no_viewport" not in browser.options


def test_a_malformed_launch_window_behaves_as_none():
    def shape(fingerprint):
        options = fingerprint["context_options"]
        return {
            key: options.get(key) is not None
            for key in ("viewport", "no_viewport", "device_scale_factor")
        }

    baseline = shape(generate_context_fingerprint(os="windows"))
    malformed = (
        mock.MagicMock(),
        {"outer": (1, 2)},
        {"outer": 1, "inner": 2, "screen": 3},
        {"outer": ("wide", "tall"), "inner": (None, None), "screen": (1920, 1080)},
        "not a launch window",
    )
    for launch_window in malformed:
        assert (
            shape(
                generate_context_fingerprint(
                    os="windows",
                    launch_window=launch_window,
                )
            )
            == baseline
        )


def test_new_context_with_a_mock_browser_does_not_crash():
    browser = mock.MagicMock()
    browser.version = "156.0"
    NewContext(browser, os="windows")
    assert "viewport" in browser.new_context.call_args.kwargs


def test_explicit_no_viewport_drops_the_generated_viewport_and_scale_factor():
    preset = next(
        preset
        for preset in load_presets()["presets"]["macos"]
        if preset["screen"].get("devicePixelRatio") == 2
    )

    sync_browser = mock.MagicMock(
        version="156.0",
        _camoufox_launch_window=NO_INNER,
    )
    NewContext(sync_browser, preset=preset)
    assert sync_browser.new_context.call_args.kwargs["device_scale_factor"] == 2
    NewContext(sync_browser, preset=preset, no_viewport=True)
    options = sync_browser.new_context.call_args.kwargs
    assert options["no_viewport"] is True
    assert "viewport" not in options
    assert "device_scale_factor" not in options

    async_browser = mock.MagicMock(
        version="156.0",
        _camoufox_launch_window=LAUNCH_WINDOW,
    )
    async_browser.new_context = mock.AsyncMock()
    async_browser.new_context.return_value.add_init_script = mock.AsyncMock()
    asyncio.run(AsyncNewContext(async_browser, os="windows", no_viewport=True))
    options = async_browser.new_context.call_args.kwargs
    assert options["no_viewport"] is True
    assert "viewport" not in options
    assert "device_scale_factor" not in options
