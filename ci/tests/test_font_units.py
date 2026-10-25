"""browser/scripts/measure-font-units.py: the font units' rates come from the pinned fpgen model.

The rates in font-manifests.json used to say `measured` with no corpus behind
them (#246): `hololens` read 0.592 while the pinned model gives 0.289.
"""

import importlib.util
import json

import pytest

from ci._util import REPO_ROOT

SCRIPT = REPO_ROOT / "browser/scripts/measure-font-units.py"
MANIFEST = REPO_ROOT / "browser/scripts/data/font-manifests.json"
MODEL = REPO_ROOT / "python/src/camoufox/fpgen-model.json"


@pytest.fixture(scope="module")
def mfu():
    spec = importlib.util.spec_from_file_location("measure_font_units", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_a_bundle_shows_whole_so_a_sample_reveals_it_every_time(mfu):
    assert mfu.reveal_probability("bundle", probed=3, total=3, sizes=[]) == 1


def test_an_alacarte_unit_is_revealed_only_if_a_probed_font_was_installed(mfu):
    # 4 fonts, 2 probed, one installed: it is a probed one half of the time.
    assert mfu.reveal_probability("alacarte", 2, 4, [{"n": 1, "w": 1.0}]) == pytest.approx(0.5)
    # Installing all four always includes a probed one.
    assert mfu.reveal_probability("alacarte", 2, 4, [{"n": 4, "w": 1.0}]) == 1
    # Installing three of four misses both probed fonts never: one unprobed
    # font cannot cover two.
    assert mfu.reveal_probability("alacarte", 2, 4, [{"n": 3, "w": 1.0}]) == 1


def test_exclusive_fonts_drop_what_another_unit_or_the_base_also_carries(mfu):
    units = [
        {"id": "a", "fonts": ["x", "shared"]},
        {"id": "b", "fonts": ["y", "shared", "inbase"]},
    ]
    assert mfu.exclusive_fonts(units, base={"inbase"}) == {"a": {"x"}, "b": {"y"}}


def test_the_rate_corrects_for_fonts_the_model_never_probes(mfu):
    samples = [{"p1"}, set(), set(), set()]  # 1 of 4 shows a probed font
    # Half the unit's fonts are probed and one font is installed: observed
    # 0.25 means 0.5 installed it.
    rate = mfu.unit_rate(
        samples,
        "alacarte",
        probed={"p1", "p2"},
        total=4,
        sizes=[{"n": 1, "w": 1.0}],
    )
    assert rate == pytest.approx(0.5)


def test_every_measured_windows_unit_names_the_model_it_was_measured_against():
    tag = json.loads(MODEL.read_text())["tag"]
    stale = [
        unit["id"]
        for unit in json.loads(MANIFEST.read_text())["win"]["additions"]
        if unit.get("model") not in (None, tag)
    ]
    assert not stale, (
        f"measured against another model than {tag}: {stale}; "
        "rerun measure-font-units.py --write"
    )


def test_the_units_the_model_can_see_carry_its_tag():
    tag = json.loads(MODEL.read_text())["tag"]
    additions = {
        unit["id"]: unit
        for unit in json.loads(MANIFEST.read_text())["win"]["additions"]
    }
    measured = ("hololens", "office", "libreoffice", "pan-euro", "web", "dev")
    missing = [unit_id for unit_id in measured if additions[unit_id].get("model") != tag]
    assert not missing, f"not measured from the pinned model: {missing}"


def test_a_locale_gated_unit_is_not_measured_from_samples_that_ignore_locale(mfu):
    # cjk-tc is on ~90% of zh-TW machines; a Windows sample is mostly not
    # zh-TW, so counting it would read ~2%.
    unit = {"id": "cjk-tc", "requiresLocale": "zh-TW", "fonts": ["x"]}
    assert "locale" in mfu.skip_reason(unit, probed={"x"})


def test_a_unit_whose_fonts_the_model_never_probes_is_not_measured(mfu):
    assert "probes none" in mfu.skip_reason({"id": "meslo", "fonts": ["x"]}, probed=set())
    assert mfu.skip_reason({"id": "web", "fonts": ["x"]}, probed={"x"}) is None


def test_an_alacarte_unit_without_sizes_fails_loudly_not_by_dividing_by_zero(mfu):
    with pytest.raises(ValueError, match="sizes"):
        mfu.reveal_probability("alacarte", 2, 4, [])


def test_the_script_imports_fpgen_only_through_the_pinned_loader():
    # A bare `import fpgen` downloads the first model GitHub lists, while the
    # script records the pinned tag as its source.
    source = SCRIPT.read_text()
    assert "import fpgen\n" not in source and "load_fpgen" in source
