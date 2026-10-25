"""SOCKS5 launch credentials are split from Playwright's public proxy options."""

import asyncio
import json
from unittest import mock
from urllib.parse import unquote, urlsplit

import pytest

from camoufox import async_api, sync_api, utils
from camoufox.exceptions import InvalidProxy
from camoufox.ip import Proxy, split_socks_credentials

from test_launch_environment import isolated_launch_dependencies  # noqa: F401


PROXY_CREDENTIALS_ENV = "CAMOU_PROXY_CREDENTIALS"


def _launch(proxy, env):
    return utils.launch_options(
        block_webgl=True,
        config={"geolocation:latitude": 0.0, "geolocation:longitude": 0.0},
        headless=True,
        i_know_what_im_doing=True,
        proxy=proxy,
        env=env,
    )


def test_embedded_credentials_are_decoded_and_removed_from_the_server():
    proxy, credentials = split_socks_credentials(
        {
            "server": "socks5://us%40er%23:p%23ss%2Fw%3Frd%2541@Proxy.Example.com:1080",
            "bypass": ".internal.example",
        }
    )

    assert proxy == {
        "server": "socks5://proxy.example.com:1080",
        "bypass": ".internal.example",
    }
    assert credentials == {
        "proxy.example.com:1080": {
            "username": "us@er#",
            "password": "p#ss/w?rd%41",
        }
    }


def test_explicit_credentials_override_embedded_credentials():
    proxy, credentials = split_socks_credentials(
        {
            "server": "SoCkS5H://url-user:url-pass@Proxy.Example.com:1080",
            "username": "field-user",
            "password": "field-pass",
        }
    )

    assert proxy == {"server": "socks5://proxy.example.com:1080"}
    assert credentials == {
        "proxy.example.com:1080": {
            "username": "field-user",
            "password": "field-pass",
        }
    }


def test_unauthenticated_socks5h_is_normalized_without_credentials():
    proxy, credentials = split_socks_credentials(
        {"server": "SOCKS5H://Proxy.Example.com:1080"}
    )

    assert proxy == {"server": "socks5://proxy.example.com:1080"}
    assert credentials is None


def test_ipv6_host_is_bracketed_in_the_server_and_lowercase_in_the_key():
    proxy, credentials = split_socks_credentials(
        {"server": "socks5h://user:pass@[2001:DB8::1]:1080"}
    )

    assert proxy == {"server": "socks5://[2001:db8::1]:1080"}
    assert credentials == {
        "2001:db8::1:1080": {"username": "user", "password": "pass"}
    }


@pytest.mark.parametrize(
    ("proxy", "message"),
    [
        ({"server": "socks5://"}, "host"),
        ({"server": "socks5:proxy.example.com:1080"}, "Invalid proxy"),
        ({"server": "//proxy.example.com:1080"}, "Invalid proxy"),
        ({"server": "socks5://proxy.example.com:not-a-port"}, "port"),
        ({"server": "socks5://proxy.example.com:70000"}, "port"),
        ({"server": "socks5://:pass@proxy.example.com:1080"}, "username"),
        ({"server": "socks5://user:pass@proxy.example.com"}, "port"),
        ({"server": "socks5://proxy.example.com"}, "port"),
        ({"server": "socks5h://proxy.example.com"}, "port"),
        (
            {"server": "socks5://proxy.example.com", "username": "user", "password": "pass"},
            "port",
        ),
        (
            {"server": "socks5://proxy.example.com:1080", "username": "", "password": "pass"},
            "username",
        ),
        ({"server": "socks5://proxy.example.com:1080/path"}, "Invalid proxy"),
    ],
)
def test_invalid_socks_servers_raise_invalid_proxy(proxy, message):
    with pytest.raises(InvalidProxy, match=message):
        split_socks_credentials(proxy)


def test_non_socks_proxies_keep_playwright_credentials():
    proxy = {
        "server": "http://proxy.example.com:8080",
        "username": "user",
        "password": "pass",
    }

    assert split_socks_credentials(proxy) == (proxy, None)


@pytest.mark.parametrize(
    ("server", "expected"),
    [
        ("http://url-user:url-pass@proxy.example.com:8080", "http://field-user:field-pass@proxy.example.com:8080"),
        ("socks5://url-user:url-pass@[2001:db8::1]:1080", "socks5://field-user:field-pass@[2001:db8::1]:1080"),
    ],
)
def test_proxy_url_uses_selected_credentials_without_a_second_at_sign(server, expected):
    proxy = Proxy(
        server=server,
        username="field-user",
        password="field-pass",
    )

    assert proxy.as_string() == expected


def test_launch_removes_credentials_and_injects_the_endpoint_map(
    isolated_launch_dependencies,  # noqa: F811
):
    options = _launch(
        {
            "server": "socks5h://embedded-user:embedded-pass@Proxy.Example.com:1080",
            "username": "launch-user",
            "password": "launch-pass",
        },
        {},
    )

    assert options["proxy"] == {"server": "socks5://proxy.example.com:1080"}
    assert json.loads(options["env"][PROXY_CREDENTIALS_ENV]) == {
        "proxy.example.com:1080": {
            "username": "launch-user",
            "password": "launch-pass",
        }
    }


def test_launch_rejects_socks_without_an_explicit_port(
    isolated_launch_dependencies,  # noqa: F811
):
    with pytest.raises(InvalidProxy, match="port"):
        _launch({"server": "socks5h://proxy.example.com"}, {})


def test_launch_keeps_an_explicit_credentials_env(
    isolated_launch_dependencies,  # noqa: F811
):
    declared = {
        "proxy-a.example.com:1080": {"username": "user-a", "password": "pass-a"},
        "proxy-b.example.com:1080": {"username": "user-b", "password": "pass-b"},
    }
    declared_json = json.dumps(declared)

    options = _launch(
        {
            "server": "socks5://proxy-c.example.com:1080",
            "username": "user-c",
            "password": "pass-c",
        },
        {
            PROXY_CREDENTIALS_ENV: declared_json,
            "UNCHANGED": "value",
        },
    )

    assert options["proxy"] == {"server": "socks5://proxy-c.example.com:1080"}
    assert options["env"][PROXY_CREDENTIALS_ENV] == declared_json
    assert options["env"]["UNCHANGED"] == "value"


def test_launch_does_not_inject_credentials_for_an_unauthenticated_proxy(
    isolated_launch_dependencies,  # noqa: F811
):
    options = _launch({"server": "socks5h://proxy.example.com:1080"}, {})

    assert options["proxy"] == {"server": "socks5://proxy.example.com:1080"}
    assert PROXY_CREDENTIALS_ENV not in options["env"]


def test_geo_lookup_uses_the_sanitized_server_and_selected_credentials(
    monkeypatch, isolated_launch_dependencies  # noqa: F811
):
    class Location:
        @staticmethod
        def as_config():
            return {
                "timezone": "UTC",
                "locale:region": "US",
                "geolocation:latitude": 40.7128,
                "geolocation:longitude": -74.006,
            }

    public_ip = mock.Mock(return_value="198.51.100.7")
    monkeypatch.setattr(utils, "geoip_allowed", lambda: None)
    monkeypatch.setattr(utils, "public_ip", public_ip)
    monkeypatch.setattr(utils, "get_geolocation", lambda *args, **kwargs: Location())

    options = utils.launch_options(
        block_webrtc=True,
        block_webgl=True,
        geoip=True,
        headless=True,
        i_know_what_im_doing=True,
        proxy={
            "server": "socks5h://url-user:url-pass@Proxy.Example.com:1080",
            "username": "field@user",
            "password": "field#pass%",
        },
        env={},
    )

    lookup_url = public_ip.call_args.args[0]
    parsed = urlsplit(lookup_url)
    assert lookup_url.count("@") == 1
    assert parsed.hostname == "proxy.example.com"
    assert parsed.port == 1080
    assert (unquote(parsed.username), unquote(parsed.password)) == (
        "field@user",
        "field#pass%",
    )
    assert options["proxy"] == {"server": "socks5://proxy.example.com:1080"}


def test_only_an_explicit_caller_env_overrides_the_generated_mapping(
    monkeypatch,
    isolated_launch_dependencies,  # noqa: F811
):
    monkeypatch.setenv(
        PROXY_CREDENTIALS_ENV,
        '{"inherited.example.com:1080":{"username":"inherited","password":"old"}}',
    )

    options = _launch(
        {
            "server": "socks5://proxy.example.com:1080",
            "username": "current",
            "password": "new",
        },
        None,
    )

    assert json.loads(options["env"][PROXY_CREDENTIALS_ENV]) == {
        "proxy.example.com:1080": {
            "username": "current",
            "password": "new",
        }
    }


@pytest.mark.parametrize("api", ["sync", "async"])
@pytest.mark.parametrize(
    "proxy",
    [
        {
            "server": "socks5://user:pass@proxy.example.com:1080",
        },
        {
            "server": "socks5h://proxy.example.com:1080",
            "username": "user",
            "password": "pass",
        },
    ],
)
def test_new_context_rejects_socks_credentials_before_geo_lookup(
    api, proxy, monkeypatch
):
    module = sync_api if api == "sync" else async_api
    resolve = mock.Mock(side_effect=AssertionError("geo lookup ran"))
    monkeypatch.setattr(module, "_resolve_proxy_geo", resolve)

    browser = mock.MagicMock()
    browser.version = "152.0.4"
    if api == "async":
        browser.new_context = mock.AsyncMock()
        operation = async_api.AsyncNewContext(
            browser,
            os="linux",
            proxy=proxy,
        )
        with pytest.raises(InvalidProxy, match="CAMOU_PROXY_CREDENTIALS"):
            asyncio.run(operation)
    else:
        with pytest.raises(InvalidProxy, match="CAMOU_PROXY_CREDENTIALS"):
            sync_api.NewContext(browser, os="linux", proxy=proxy)

    resolve.assert_not_called()
    browser.new_context.assert_not_called()


@pytest.mark.parametrize("api", ["sync", "async"])
def test_new_context_normalizes_unauthenticated_socks5h(api, monkeypatch):
    module = sync_api if api == "sync" else async_api
    fingerprint = {"context_options": {}, "init_script": ""}
    resolve = mock.Mock(side_effect=AssertionError("geo lookup ran"))
    monkeypatch.setattr(
        module,
        "generate_context_fingerprint",
        mock.Mock(return_value=fingerprint),
    )
    monkeypatch.setattr(module, "_resolve_proxy_geo", resolve)

    browser = mock.MagicMock()
    browser.version = "152.0.4"
    context = mock.MagicMock()
    if api == "async":
        context.add_init_script = mock.AsyncMock()
        browser.new_context = mock.AsyncMock(return_value=context)
    else:
        browser.new_context = mock.Mock(return_value=context)
    kwargs = {
        "proxy": {"server": "socks5h://Proxy.Example.com:1080"},
        "webrtc_ip": "198.51.100.1",
        "geolocation": {"latitude": 1.0, "longitude": 2.0},
        "timezone_id": "UTC",
        "locale": "en-US",
    }

    if api == "async":
        asyncio.run(async_api.AsyncNewContext(browser, os="linux", **kwargs))
    else:
        sync_api.NewContext(browser, os="linux", **kwargs)

    assert browser.new_context.call_args.kwargs["proxy"] == {
        "server": "socks5://proxy.example.com:1080"
    }
    resolve.assert_not_called()
