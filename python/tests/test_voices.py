"""
Tests for camoufox.fingerprints speech-voice generation.

Mirrored by the "voices" cases in typescript/tests/fingerprints.test.ts.

Run with:
    cd python && python -m pytest tests/test_voices.py -v

The core regression these guard: every spoofable OS -- including Linux --
must yield a non-empty list of MaskConfig voice OBJECTS (not raw
"Name:lang:type" strings), or the C++ MaskConfig::MVoices() silently drops
them and the host machine's native voices leak through.
"""


import pytest

from camoufox.fingerprints import (
    _generate_random_voice_subset,
    _speechd_voices,
    _normalize_preset_voices,
)

_REQUIRED_FIELDS = {"lang", "name", "voiceUri", "isDefault", "isLocalService"}


@pytest.mark.parametrize("target_os", ["macos", "windows", "linux"])
def test_non_empty_for_every_os(target_os):
    voices = _generate_random_voice_subset(target_os, "en-US")
    assert len(voices) > 0


@pytest.mark.parametrize("target_os", ["macos", "windows", "linux"])
def test_entries_are_full_objects(target_os):
    # MaskConfig::MVoices() drops any entry missing a field, so every voice
    # must carry the full object shape.
    for v in _generate_random_voice_subset(target_os, "en-US"):
        assert isinstance(v, dict)
        assert _REQUIRED_FIELDS <= set(v.keys())


@pytest.mark.parametrize("target_os", ["windows", "linux"])
def test_no_default_voice(target_os):
    # Stock Firefox marks no SpeechSynthesisVoice.default with SAPI or
    # speech-dispatcher.
    voices = _generate_random_voice_subset(target_os, "en-US")
    assert voices and not any(v["isDefault"] for v in voices)


def test_macos_system_voice_is_default():
    # Stock Firefox on macOS 14, 15, 26 and 27 marks the system voice default:
    # Samantha on an English system.
    voices = _generate_random_voice_subset("macos", "en-US", seed=1)
    assert [v["name"] for v in voices if v["isDefault"]] == ["Samantha"]


@pytest.mark.parametrize("seed", range(40))
def test_linux_voices_follow_the_font_release(seed):
    # One machine runs one Ubuntu release: its voices and its fonts are that
    # release's, never a mix. 24.04 lists 13362 speech-dispatcher voices and
    # 26.04 lists 14805 (measured on each release's default install).
    import camoufox.fingerprints as fp

    release = fp._pick_release("lin", fp._rng(seed))["id"]
    base = next(b for b in fp._load_font_bases()["lin"] if b["id"] == release)
    assert set(base["fonts"]) <= set(fp._generate_random_font_subset("linux", seed=seed))
    count = len(_generate_random_voice_subset("linux", seed=seed))
    assert count == {"ubuntu2404": 13362, "ubuntu2604": 14805}[release]


def test_linux_voices_are_speech_dispatchers_order():
    # Each espeak-ng language alone, then with each variant, as
    # spd_list_synthesis_voices() returns them.
    names = [v["name"] for v in _generate_random_voice_subset("linux", seed=1)[:3]]
    assert names == ["Afrikaans", "Afrikaans+Adam", "Afrikaans+Alex"]


@pytest.mark.usefixtures("any_installed_browser")
def test_linux_launch_carries_the_grid():
    # ~15000 voice objects do not fit in the environment; the grid does.
    cfg = _launch_config(os="linux")
    grid = cfg["voices:speechd"]
    assert "voices" not in cfg
    assert len(grid["languages"]) in (131, 141)
    assert cfg["voices:blockIfNotDefined"] is True


@pytest.mark.usefixtures("any_installed_browser")
def test_a_given_speechd_grid_is_kept():
    # A caller's grid is the identity's voices,
    # not something to draw over.
    grid = {"languages": [["English (America)", "en-US"]], "variants": ["Adam"]}
    cfg = _launch_config(os="linux", config={"voices:speechd": grid})
    assert cfg["voices:speechd"] == grid
    assert "voices" not in cfg


@pytest.mark.parametrize(
    "value",
    [
        {"languages": [["Afrikaans", "af"]]},  # no variants
        {"languages": [["Afrikaans"]], "variants": []},  # language without a code
        {"languages": [["Afrikaans", "af"]], "variants": [1]},
        [["Afrikaans", "af"]],  # not an object
    ],
)
def test_validate_speechd_voices_rejects_unusable_shapes(value):
    from camoufox.utils import validate_speechd_voices

    with pytest.raises(InvalidPropertyType):
        validate_speechd_voices(value)


def test_windows_display_language_pack():
    # A German display language gets the German OneCore pack first; en-US is
    # the pack every stock en-US box reports (David / Mark / Zira + Desktop).
    de = _generate_random_voice_subset("windows", "de-DE", seed=1)
    assert de[0]["lang"] == "de-DE"
    en = _generate_random_voice_subset("windows", "en-US", seed=1)
    assert [v["name"] for v in en[:3]] == [
        "Microsoft David - English (United States)",
        "Microsoft Mark - English (United States)",
        "Microsoft Zira - English (United States)",
    ]


class TestLinuxSpeechdUris:
    """Linux voiceUris must match Firefox's SpeechDispatcherService.cpp:
    urn:moz-tts:speechd:<NS_EscapeURL(name, OnlyNonASCII|Spaces)>?<lang>
    """

    def setup_method(self):
        self.lin = _generate_random_voice_subset("linux", "en-US")

    def test_prefix_and_lang_suffix(self):
        for v in self.lin:
            assert v["voiceUri"].startswith("urn:moz-tts:speechd:")
            assert v["voiceUri"].endswith("?" + v["lang"])

    def test_spaces_escaped_punctuation_intact(self):
        gb = next(v for v in self.lin if v["name"] == "English (Great Britain)")
        assert gb["voiceUri"] == "urn:moz-tts:speechd:English%20(Great%20Britain)?en-GB"

    def test_none_local_service(self):
        # Stock reports localService false for every speech-dispatcher voice
        # (measured on Ubuntu 26.04: SpeechDispatcherService passes
        # name == "default" as aLocalService).
        assert not any(v["isLocalService"] for v in self.lin)


def test_normalize_preset_voices_converts_strings():
    # Presets historically store "Name:lang:type" strings.
    out = _normalize_preset_voices(
        ["Albert:en-US:local", "Alice:it-IT:local"], "macos"
    )
    assert all(_REQUIRED_FIELDS <= set(v.keys()) for v in out)
    assert out[0]["name"] == "Albert"
    assert out[0]["lang"] == "en-US"
    assert sum(1 for v in out if v["isDefault"]) == 1


def test_normalize_preset_voices_passes_through_objects():
    obj = {
        "name": "Alex",
        "lang": "en-US",
        "voiceUri": "urn:moz-tts:osx:alex",
        "isDefault": True,
        "isLocalService": True,
    }
    out = _normalize_preset_voices([obj], "macos")
    assert out == [obj]


def test_unknown_os_falls_back_to_macos():
    assert len(_generate_random_voice_subset("plan9", "en-US")) > 0


# ── Fail-closed voice configuration (daijro/camoufox#731) ────────────────────
#
# nsSynthVoiceRegistry only withholds the host's speech-dispatcher / SAPI /
# NSSpeech voices while Camoufox owns the list. An empty or unset `voices`
# used to fall through to the host backend and register every native voice --
# 14805 espeak-ng entries on a stock Linux box -- under a fingerprint claiming
# macOS or Windows.

from camoufox.exceptions import InvalidPropertyType  # noqa: E402
from camoufox.utils import validate_voices  # noqa: E402


@pytest.fixture
def any_installed_browser(monkeypatch):
    """The grid must not depend on the build this machine has active, whose
    properties.json may predate it."""
    from camoufox import utils

    monkeypatch.setattr(utils, "validate_config", lambda *args, **kwargs: None)


def _launch_config(**kwargs):
    """Rebuild the config dict from the chunked CAMOU_CONFIG_* env vars."""
    import json

    from camoufox.utils import launch_options

    opts = launch_options(headless=True, i_know_what_im_doing=True, **kwargs)
    env = opts["env"]
    chunks = sorted(
        (k for k in env if k.startswith("CAMOU_CONFIG_")),
        key=lambda k: int(k.rsplit("_", 1)[1]),
    )
    return json.loads("".join(env[k] for k in chunks))


def test_block_flag_is_pinned_by_default():
    # Without this the browser has no instruction to withhold host voices when
    # the list it receives turns out to be empty or unusable.
    assert _launch_config(os="macos")["voices:blockIfNotDefined"] is True


def test_caller_can_override_the_block_flag():
    cfg = _launch_config(os="macos", config={"voices:blockIfNotDefined": False})
    assert cfg["voices:blockIfNotDefined"] is False


def test_voice_generation_failure_fails_closed(monkeypatch):
    import camoufox.utils as utils

    from camoufox._warnings import FallbackWarning

    def boom(*_args, **_kwargs):
        raise OSError("voice-manifests.json unreadable")

    monkeypatch.setattr(utils, "draw_voice_config", boom)
    with pytest.warns(FallbackWarning, match="github.com/daijro/camoufox/issues/new"):
        cfg = _launch_config(os="macos")
    # An empty list plus the block flag means "no voices" -- never "all of the
    # host's".
    assert cfg["voices"] == []
    assert cfg["voices:blockIfNotDefined"] is True


@pytest.mark.parametrize(
    "value",
    [
        ["Alex:en-US:local"],  # the bare-string shape MVoices() drops
        [{"name": "Alex", "lang": "en-US"}],  # incomplete object
        "Alex",  # not a list at all
    ],
)
def test_validate_voices_rejects_unusable_shapes(value):
    with pytest.raises(InvalidPropertyType):
        validate_voices(value)


@pytest.mark.parametrize(
    "value",
    [
        [],  # empty is legal: it means "no voices", and the flag enforces it
        [
            {
                "lang": "en-US",
                "name": "Alex",
                "voiceUri": "urn:moz-tts:osx:alex",
                "isDefault": True,
                "isLocalService": True,
            }
        ],
    ],
)
def test_validate_voices_accepts_usable_shapes(value):
    validate_voices(value)


def test_a_context_voice_list_keeps_names_that_hold_commas():
    """setSpeechVoices gets one name per line: Windows names hold commas."""
    import json
    import re

    from camoufox.fingerprints import _build_init_script

    names = ["Microsoft Hanhan - Chinese (Traditional, Taiwan)", "Microsoft David - English (United States)"]
    script = _build_init_script({"speechVoices": [{"name": n} for n in names]})
    arg = re.search(r"w\.setSpeechVoices\((\".*?\")\);", script).group(1)
    assert json.loads(arg).split("\n") == names


# ── A context's voices (speech-voices-spoofing.patch) ────────────────────────
#
# A context's list only selects among the voices the browser registered. The
# launch registers its own voices and, as `voices:pool`, every voice the
# manifests hold for any OS a context may claim; a context draws its voices for
# its own locale, as a launch does.


def test_launch_registers_every_voice_a_context_can_draw():
    from camoufox.fingerprints import generate_context_fingerprint

    config = _launch_config(os="windows")
    pool = {v["voiceUri"] for v in config["voices:pool"]}
    grid = config["voices:pool:speechd"]
    pooled_speechd = set(_speechd_voices(grid))
    for os in ("windows", "macos", "linux"):
        for locale in ("de-DE", "fr-FR", "ja-JP", "en-GB"):
            context = generate_context_fingerprint(os=os, locale=locale)["config"]
            if os == "linux":
                # A Linux context names its release's speech-dispatcher grid,
                # which the browser registers from voices:pool:speechd.
                assert "voices" not in context
                assert set(_speechd_voices(context["voices:speechd"])) <= pooled_speechd
            else:
                assert {v["voiceUri"] for v in context["voices"]} <= pool


def test_the_speechd_pool_holds_every_release_grid():
    from camoufox.fingerprints import _load_voice_manifests

    pooled = set(_speechd_voices(_launch_config(os="windows")["voices:pool:speechd"]))
    for release in _load_voice_manifests()["lin"]["releases"].values():
        assert set(_speechd_voices(release["speechd"])) <= pooled


def test_voice_pool_entries_are_full_objects():
    pool = _launch_config(os="macos")["voices:pool"]
    assert pool
    for v in pool:
        assert _REQUIRED_FIELDS <= set(v.keys())
    # Only macOS's system voice, as stock macOS marks it: a macOS context in a
    # launch of another OS reports it default too.
    assert [v["name"] for v in pool if v["isDefault"]] == ["Samantha"]


def test_caller_can_replace_the_voice_pool():
    assert _launch_config(os="macos", config={"voices:pool": []})["voices:pool"] == []


def test_context_voices_follow_its_locale():
    # A German Windows reports the German OneCore pack first, as a launch
    # with locale="de-DE" does.
    from camoufox.fingerprints import generate_context_fingerprint

    for _ in range(5):
        voices = generate_context_fingerprint(os="windows", locale="de-DE")["config"]["voices"]
        assert voices[0]["lang"] == "de-DE"


def _new_context_script(api, **kwargs):
    import asyncio
    from unittest import mock

    from camoufox import async_api, sync_api

    context = mock.MagicMock()
    browser = mock.MagicMock()
    browser.version = "158.0"
    if api == "sync":
        browser.new_context.return_value = context
        sync_api.NewContext(browser, **kwargs)
    else:
        context.add_init_script = mock.AsyncMock()
        browser.new_context = mock.AsyncMock(return_value=context)
        asyncio.run(async_api.AsyncNewContext(browser, **kwargs))
    return browser.new_context.call_args.kwargs, context.add_init_script.call_args.args[0]


@pytest.mark.parametrize("api", ["sync", "async"])
@pytest.mark.parametrize("locale", ["de-DE", "de", "de, en-US, en"])
def test_new_context_draws_voices_for_its_locale(api, locale):
    # Playwright's locale is a tag or a language list whose first entry is the
    # locale; either way the context lists a German Windows's voices, and
    # Playwright gets the locale as given.
    options, script = _new_context_script(api, os="windows", locale=locale)
    assert options["locale"] == locale
    assert "Microsoft Hedda - German (Germany)" in script


def test_a_linux_context_with_a_locale_keeps_its_release_grid():
    """The locale redraw is for Windows' language packs. A Linux grid does not
    depend on the locale, and a redraw could name another Ubuntu release than
    the context's fonts; the browser gets the grid as JSON (leading "{")."""
    import json
    import re

    from camoufox.fingerprints import generate_context_fingerprint

    for locale in ("de-DE", "ja-JP"):
        fp = generate_context_fingerprint(os="linux", locale=locale)
        assert "voices" not in fp["config"]
        grid = fp["config"]["voices:speechd"]
        call = re.search(r"w\.setSpeechVoices\((\".*\")\);", fp["init_script"])
        sent = json.loads(call.group(1))
        assert sent.startswith("{")
        assert json.loads(sent) == {"speechd": grid}
