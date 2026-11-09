import json
import warnings

import pytest

from camoufox import utils
from camoufox._warnings import LeakWarning

from test_launch_environment import isolated_launch_dependencies  # noqa: F401  (fixture)

# Stock Firefox 159 values (StaticPrefList.yaml, all.js; media.preload.* are unset there and
# HTMLMediaElement.cpp GetPreloadDefault/GetPreloadDefaultAuto fall back to 2 and 3).
STOCK = {
    'browser.cache.disk.smart_size.enabled': True,
    'browser.cache.disk.capacity': 256000,
    'media.preload.default': 2,
    'media.preload.auto': 3,
    'network.prefetch-next': True,
    'gfx.downloadable_fonts.enabled': True,
    'permissions.default.image': 1,
}
CACHE_ONLY = {
    'browser.cache.disk.smart_size.enabled': False,
    'browser.cache.disk.capacity': 2 * 1024 * 1024,
}
PAGE_VISIBLE = {
    'media.preload.default': 1,
    'media.preload.auto': 2,
    'network.prefetch-next': False,
    'gfx.downloadable_fonts.enabled': False,
}


def _prefs(**kwargs):
    kwargs.setdefault('enable_cache', True)
    kwargs.setdefault('i_know_what_im_doing', True)
    return utils.launch_options(**kwargs)['firefox_user_prefs']


def _owned(prefs):
    """The mode's prefs this launch writes; a key left out keeps Firefox's default."""
    return {k: prefs[k] for k in STOCK if k in prefs}


@pytest.mark.parametrize('level', [None, 0, False])
def test_off_writes_nothing_on_a_fresh_profile(isolated_launch_dependencies, level):
    # Stock Firefox has no user pref for any of these; writing stock values would be a
    # difference of its own in about:support and prefs.js.
    # enable_cache off: it writes smart sizing on itself, at stock.
    assert _owned(_prefs(low_bandwidth=level, enable_cache=False)) == {}


def test_off_clears_what_an_earlier_level_left(isolated_launch_dependencies, tmp_path):
    # A persistent profile keeps a user.js pref in prefs.js after the launch that set it.
    left = {**CACHE_ONLY, **PAGE_VISIBLE, 'permissions.default.image': 2}
    (tmp_path / 'prefs.js').write_text(
        ''.join(f'user_pref("{k}", {json.dumps(v)});\n' for k, v in left.items())
    )
    assert _owned(_prefs(enable_cache=False, user_data_dir=str(tmp_path))) == STOCK


def test_lower_level_clears_what_a_higher_one_left(isolated_launch_dependencies, tmp_path):
    (tmp_path / 'prefs.js').write_text(
        ''.join(f'user_pref("{k}", {json.dumps(v)});\n' for k, v in {**CACHE_ONLY, **PAGE_VISIBLE}.items())
    )
    prefs = _owned(_prefs(low_bandwidth=1, user_data_dir=str(tmp_path)))
    assert prefs == {**CACHE_ONLY, **{k: STOCK[k] for k in PAGE_VISIBLE}}


def test_level_1_changes_only_the_disk_cache(isolated_launch_dependencies):
    assert _owned(_prefs(low_bandwidth=1)) == CACHE_ONLY


def test_level_1_does_not_warn(isolated_launch_dependencies):
    with warnings.catch_warnings():
        warnings.simplefilter('error', LeakWarning)
        _prefs(low_bandwidth=1, i_know_what_im_doing=False)


def test_level_2_adds_cellular_preload_no_prefetch_no_web_fonts(isolated_launch_dependencies):
    assert _owned(_prefs(low_bandwidth=2)) == {**CACHE_ONLY, **PAGE_VISIBLE}


def test_level_2_warns(isolated_launch_dependencies):
    with pytest.warns(LeakWarning, match='cellular'):
        _prefs(low_bandwidth=2, i_know_what_im_doing=False)


def test_level_3_blocks_images_with_both_warnings(isolated_launch_dependencies):
    with pytest.warns(LeakWarning) as caught:
        prefs = _prefs(low_bandwidth=3, i_know_what_im_doing=False)
    messages = ' '.join(str(w.message) for w in caught)
    assert 'web fonts' in messages and 'image' in messages
    assert _owned(prefs) == {**CACHE_ONLY, **PAGE_VISIBLE, 'permissions.default.image': 2}


def test_level_3_contradicting_block_images_is_refused(isolated_launch_dependencies):
    with pytest.raises(ValueError, match='block_images'):
        _prefs(low_bandwidth=3, block_images=False)


def test_block_images_still_works_alone(isolated_launch_dependencies):
    assert _owned(_prefs(block_images=True, enable_cache=False)) == {'permissions.default.image': 2}


def test_cache_size_survives_enable_cache(isolated_launch_dependencies):
    # enable_cache merges CACHE_PREFS, which turns smart sizing back on; that would cap the
    # cache at Firefox's 1 GB smart size and ignore the capacity.
    assert _prefs(low_bandwidth=1)['browser.cache.disk.smart_size.enabled'] is False


@pytest.mark.parametrize('cache', [None, False])
def test_requires_the_cache(isolated_launch_dependencies, cache):
    with pytest.raises(ValueError, match='enable_cache'):
        _prefs(low_bandwidth=1, enable_cache=cache)


@pytest.mark.parametrize('level', [4, -1, 1.5, '2', True])
def test_rejects_unknown_levels(isolated_launch_dependencies, level):
    with pytest.raises(ValueError, match='low_bandwidth'):
        _prefs(low_bandwidth=level)


def test_caller_prefs_win(isolated_launch_dependencies):
    prefs = _prefs(low_bandwidth=2, firefox_user_prefs={'gfx.downloadable_fonts.enabled': True})
    assert prefs['gfx.downloadable_fonts.enabled'] is True
