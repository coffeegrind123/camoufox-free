import pytest

from camoufox import utils

from test_launch_environment import isolated_launch_dependencies  # noqa: F401  (fixture)


def _prefs(**kwargs):
    kwargs.setdefault('i_know_what_im_doing', True)
    return utils.launch_options(**kwargs)['firefox_user_prefs']


UAS = {
    'windows': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:159.0) Gecko/20100101 Firefox/159.0',
    'macos': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:159.0) Gecko/20100101 Firefox/159.0',
    'linux': 'Mozilla/5.0 (X11; Linux x86_64; rv:159.0) Gecko/20100101 Firefox/159.0',
}


# The webcompat add-on's own platform names (intervention_helpers.js getOS,
# appConstants.js getPlatform): what its interventions' "platforms" match.
@pytest.mark.parametrize('os_name, platform', [('windows', 'windows'), ('macos', 'mac'), ('linux', 'linux')])
def test_webcompat_interventions_follow_the_claimed_os(isolated_launch_dependencies, os_name, platform):
    prefs = _prefs(config={'navigator.userAgent': UAS[os_name]})
    assert prefs['extensions.webcompat.platform_override'] == platform


def test_webcompat_caller_pref_wins(isolated_launch_dependencies):
    prefs = _prefs(config={'navigator.userAgent': UAS['windows']}, firefox_user_prefs={'extensions.webcompat.platform_override': 'linux'})
    assert prefs['extensions.webcompat.platform_override'] == 'linux'
