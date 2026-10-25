import ipaddress
import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Dict, NamedTuple, Optional, Tuple
from urllib.parse import quote, unquote, urlsplit

import requests

from .exceptions import InvalidIP, InvalidProxy

"""
Helpers to find the user's public IP address for geolocation.
"""


@dataclass
class Proxy:
    """
    Stores proxy information.
    """

    server: str
    username: Optional[str] = None
    password: Optional[str] = None
    bypass: Optional[str] = None

    @staticmethod
    def parse_server(server: str) -> Tuple[str, str, Optional[str]]:
        """
        Parses the proxy server string.
        """
        proxy_match = re.match(r'^(?:(?P<schema>\w+)://)?(?P<url>.*?)(?:\:(?P<port>\d+))?$', server)
        if not proxy_match:
            raise InvalidProxy(f"Invalid proxy server: {server}")
        return proxy_match['schema'], proxy_match['url'], proxy_match['port']

    def as_string(self) -> str:
        schema, url, port = self.parse_server(self.server)
        if not schema:
            schema = 'http'
        result = f"{schema}://"
        # Percent-encode the credentials: a raw `#`, `/`, `?` or `@` breaks the
        # URL, and a raw `%XX` is decoded into a different password.
        if self.username:
            result += quote(self.username, safe='')
            if self.password:
                result += f":{quote(self.password, safe='')}"
            result += "@"

        # An explicit username replaces URL userinfo rather than adding a second
        # credential pair, which would produce an invalid URL with two `@`s.
        result += url.rsplit('@', 1)[-1] if self.username else url
        if port:
            result += f":{port}"
        return result

    @staticmethod
    def as_requests_proxy(proxy_string: str) -> Dict[str, str]:
        """
        Converts the proxy to a requests proxy dictionary.
        """
        return {
            'http': proxy_string,
            'https': proxy_string,
        }


PROXY_CREDENTIALS_ENV = 'CAMOU_PROXY_CREDENTIALS'
SOCKS5_SCHEMES = ('socks5', 'socks5h')


def split_socks_credentials(
    proxy: Optional[Dict[str, str]],
) -> Tuple[Optional[Dict[str, str]], Optional[Dict[str, Dict[str, str]]]]:
    """Split SOCKS5 credentials from Playwright's public proxy settings.

    Playwright's driver rejects SOCKS5 proxies that carry credentials. Return a
    proxy without them for Playwright, plus credentials keyed by lower-case
    ``host:port`` for the launch environment. Credentials in the server URL are
    percent-decoded; explicit username/password fields take precedence.
    """
    if proxy is None:
        return None, None

    server = proxy.get('server')
    if not isinstance(server, str) or not server:
        raise InvalidProxy(f"Invalid proxy server: {server!r}")

    if '://' not in server:
        scheme = server.split(':', 1)[0].lower()
        if scheme in SOCKS5_SCHEMES or server.startswith(('/', '.', '?', '#')) or '/' in server:
            raise InvalidProxy(f"Invalid proxy server: {server}")
        # Playwright accepts a scheme-less HTTP endpoint in host:port form.
        return proxy, None

    try:
        parsed = urlsplit(server)
        host = parsed.hostname
    except ValueError as exception:
        raise InvalidProxy(f"Invalid proxy server: {server}") from exception
    try:
        port = parsed.port
    except ValueError as exception:
        raise InvalidProxy(f"Invalid proxy server port: {server}") from exception

    if parsed.scheme.lower() not in SOCKS5_SCHEMES:
        return proxy, None
    if not host:
        raise InvalidProxy(f"Invalid proxy server, missing host: {server}")
    if parsed.path or parsed.query or parsed.fragment:
        raise InvalidProxy(f"Invalid proxy server: {server}")

    host_port = parsed.netloc.rsplit('@', 1)[-1]
    if host_port.endswith(':'):
        raise InvalidProxy(f"Invalid proxy server port: {server}")
    if port is not None and not 1 <= port <= 65535:
        raise InvalidProxy(f"Invalid proxy server port: {server}")
    if port is None:
        # Playwright serializes a missing SOCKS port as NaN for Juggler.
        raise InvalidProxy(f"A SOCKS5 proxy needs an explicit port: {server}")

    for field in ('username', 'password'):
        value = proxy.get(field)
        if value is not None and not isinstance(value, str):
            raise InvalidProxy(f"Invalid proxy {field}: expected a string")

    if 'username' in proxy:
        username = proxy['username'] or ''
    else:
        username = unquote(parsed.username or '')
    if 'password' in proxy:
        password = proxy['password'] or ''
    else:
        password = unquote(parsed.password or '')

    if password and not username:
        raise InvalidProxy("A SOCKS5 proxy password requires a username")

    playwright_proxy = dict(proxy)
    playwright_proxy.pop('username', None)
    playwright_proxy.pop('password', None)
    normalized_host = host.lower()
    normalized_server = f"[{normalized_host}]" if ':' in normalized_host else normalized_host
    normalized_server += f":{port}"
    playwright_proxy['server'] = f"socks5://{normalized_server}"

    if not username:
        return playwright_proxy, None
    return playwright_proxy, {
        f"{normalized_host}:{port}": {
            "username": username,
            "password": password,
        }
    }


@lru_cache(128, typed=True)
def valid_ipv4(ip: str) -> bool:
    try:
        return isinstance(ipaddress.ip_address(ip), ipaddress.IPv4Address)
    except ValueError:
        return False


@lru_cache(128, typed=True)
def valid_ipv6(ip: str) -> bool:
    try:
        return isinstance(ipaddress.ip_address(ip), ipaddress.IPv6Address)
    except ValueError:
        return False


def validate_ip(ip: str) -> None:
    if not valid_ipv4(ip) and not valid_ipv6(ip):
        raise InvalidIP(f"Invalid IP address: {ip}")


# Probing the exit IP through a proxy adds a hop and a TLS handshake behind it; 5 s
# is not enough for a proxy that routes the long way round, and every URL timing out
# fails the whole launch. Direct probes keep 5 s.
DIRECT_IP_TIMEOUT = 5
PROXIED_IP_TIMEOUT = 15


class ExitGeo(NamedTuple):
    """Where a proxy exits: its IP and that IP's timezone, country and position."""

    ip: str
    timezone: str
    country: str
    latitude: float
    longitude: float


def proxy_exit_geo(proxy: str) -> ExitGeo:
    """
    Where `proxy` exits, looked up through the proxy. Raises InvalidIP when the
    lookup fails: a context that silently kept the host's WebRTC IP and
    timezone behind a proxy would be a leak.
    """
    try:
        resp = requests.get(
            "http://ip-api.com/json?fields=status,message,query,timezone,countryCode,lat,lon",
            proxies=Proxy.as_requests_proxy(proxy),
            timeout=PROXIED_IP_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as exception:
        raise InvalidIP(f"{PROXY_LOOKUP_FAILED}: {exception}") from exception
    if data.get("status") != "success" or not all(
        data.get(key) is not None
        for key in ("query", "timezone", "countryCode", "lat", "lon")
    ):
        raise InvalidIP(f"{PROXY_LOOKUP_FAILED}: {data.get('message') or data}")
    validate_ip(data["query"])
    return ExitGeo(
        data["query"],
        data["timezone"],
        data["countryCode"],
        float(data["lat"]),
        float(data["lon"]),
    )


PROXY_LOOKUP_FAILED = (
    "Could not look up where the proxy exits. Pass webrtc_ip, timezone_id, "
    "locale and geolocation explicitly to skip the lookup"
)


@lru_cache(maxsize=None)
def public_ipv6() -> Optional[str]:
    """
    This host's public IPv6 address, or None when it has none it can reach the
    internet from. The hosts have AAAA records only, so an answer proves the route.
    """
    for url in ("https://api6.ipify.org", "https://v6.ident.me"):
        try:
            resp = requests.get(url, timeout=DIRECT_IP_TIMEOUT, verify=True)
            resp.raise_for_status()
        except requests.RequestException:
            continue
        ip = resp.text.strip()
        if valid_ipv6(ip):
            return ip
    return None


@lru_cache(maxsize=None)
def public_ip(proxy: Optional[str] = None) -> str:
    """
    Sends a request to a public IP api
    """
    URLS = [
        # Prefers IPv4
        "https://api.ipify.org",
        "https://checkip.amazonaws.com",
        "https://ipinfo.io/ip",
        # IPv4 & IPv6
        "https://icanhazip.com",
        "https://ifconfig.co/ip",
        "https://ipecho.net/plain",
    ]

    end_exception = None
    for url in URLS:
        try:
            resp = requests.get(
                url,
                proxies=Proxy.as_requests_proxy(proxy) if proxy else None,
                timeout=PROXIED_IP_TIMEOUT if proxy else DIRECT_IP_TIMEOUT,
                verify=True,
            )
            resp.raise_for_status()
            ip = resp.text.strip()
            validate_ip(ip)
            return ip
        except (requests.exceptions.ProxyError, requests.RequestException, InvalidIP) as exception:
            end_exception = exception
    raise InvalidIP(f"Failed to get IP address: {end_exception}")
