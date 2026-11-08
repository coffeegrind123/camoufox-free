"""
Verify authenticated SOCKS5 proxies use RFC 1929 and fail closed.

Playwright's Firefox driver rejects SOCKS5 username/password before Juggler sees
the proxy. The launchers therefore take credentials out of what Playwright sees
and hand them to Juggler: a launch-level proxy's through CAMOU_PROXY_AUTH, a
context's (NewContext, or new_context on a Camoufox browser) through an init
script Juggler removes. Juggler also still reads a caller-declared
CAMOU_PROXY_CREDENTIALS map. It constructs an nsIProxyInfo with
newProxyInfoWithAuth. This guard uses an in-process SOCKS5 server to prove the
browser negotiates method 0x02, carries the configured credentials, and sends a
domain target (socks5h resolves at the proxy), at launch and per context.

The negative cases make the fail-closed requirement testable: a wrong password
at launch, in a context, and in CAMOU_PROXY_CREDENTIALS, and malformed
CAMOU_PROXY_CREDENTIALS JSON. A local HTTP target stays reachable directly; the
page must still fail to fetch it. A fallback to defaultProxyInfo would return
the direct marker.

    python browser/tests/playwright/patches/socks5-auth.py
"""

import http.server
import ipaddress
import json
import os
import socket
import struct
import sys
import threading
import urllib.request
from pathlib import Path
from typing import Dict, List, Tuple
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parent))
from helpers import resolve_binary  # noqa: E402

PROXY_CREDENTIALS_ENV = "CAMOU_PROXY_CREDENTIALS"
MARKER = "authenticated-socks5-target"
TARGET_HOST = "socks5-auth.test"
USERNAME = "guard-user"
PASSWORD = "guard-pass"


def recv_exact(conn: socket.socket, size: int) -> bytes:
    data = b""
    while len(data) < size:
        chunk = conn.recv(size - len(data))
        if not chunk:
            raise ConnectionError("SOCKS peer closed during handshake")
        data += chunk
    return data


class Target(http.server.BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        body = MARKER.encode()
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args: object) -> None:
        pass


class AuthenticatedSocks5:
    """A local SOCKS5 proxy that records the methods and credentials it sees."""

    def __init__(self) -> None:
        self.socket = socket.socket()
        self.socket.bind(("127.0.0.1", 0))
        self.socket.listen()
        self.port = self.socket.getsockname()[1]
        self.target_port = 0
        self.requests: List[Tuple[str, str, str]] = []
        self.failed_auth = 0

    def start(self, target_port: int) -> None:
        self.target_port = target_port
        threading.Thread(target=self._serve, daemon=True).start()

    def close(self) -> None:
        self.socket.close()

    def _serve(self) -> None:
        while True:
            try:
                conn, _ = self.socket.accept()
            except OSError:
                return
            threading.Thread(target=self._handle, args=(conn,), daemon=True).start()

    def _handle(self, conn: socket.socket) -> None:
        conn.settimeout(15)
        try:
            version, methods = recv_exact(conn, 2)
            if version != 5:
                return
            offered = set(recv_exact(conn, methods))
            if 2 not in offered:
                conn.sendall(b"\x05\xff")
                return
            conn.sendall(b"\x05\x02")

            auth_version, username_length = recv_exact(conn, 2)
            username = recv_exact(conn, username_length).decode()
            (password_length,) = recv_exact(conn, 1)
            password = recv_exact(conn, password_length).decode()
            if auth_version != 1 or (username, password) != (USERNAME, PASSWORD):
                self.failed_auth += 1
                conn.sendall(b"\x01\x01")
                return
            conn.sendall(b"\x01\x00")

            version, command, _, address_type = recv_exact(conn, 4)
            if version != 5 or command != 1:
                return
            if address_type == 1:
                address = socket.inet_ntoa(recv_exact(conn, 4))
            elif address_type == 3:
                (length,) = recv_exact(conn, 1)
                address = recv_exact(conn, length).decode()
            elif address_type == 4:
                address = socket.inet_ntop(socket.AF_INET6, recv_exact(conn, 16))
            else:
                return
            (port,) = struct.unpack("!H", recv_exact(conn, 2))
            self.requests.append((username, address, str(port)))

            upstream = socket.create_connection(("127.0.0.1", self.target_port), timeout=5)
            with upstream:
                conn.sendall(b"\x05\x00\x00\x01\x7f\x00\x00\x01\x00\x00")
                self._tunnel(conn, upstream)
        except (ConnectionError, OSError, UnicodeDecodeError):
            pass
        finally:
            conn.close()

    @staticmethod
    def _tunnel(left: socket.socket, right: socket.socket) -> None:
        import select

        peers = {left: right, right: left}
        while True:
            readable, _, _ = select.select(list(peers), [], [], 10)
            if not readable:
                return
            for source in readable:
                data = source.recv(65536)
                if not data:
                    return
                peers[source].sendall(data)


class QuietServer(http.server.ThreadingHTTPServer):
    def handle_error(self, _request: object, _client_address: object) -> None:
        pass


def direct_target_host() -> str:
    """A local non-loopback address, which Firefox does not proxy-bypass."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.connect(("192.0.2.1", 9))
        host = sock.getsockname()[0]
    if ipaddress.ip_address(host).is_loopback:
        raise RuntimeError("no non-loopback address for the direct control")
    return host


def direct_http_available(host: str, port: int) -> bool:
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(f"http://{host}:{port}/", timeout=3) as response:
            return response.read().decode() == MARKER
    except OSError:
        return False


def page_fetch(page: object, url: str) -> Dict[str, object]:
    return page.evaluate(
        """async url => {
          try {
            return {body: await (await fetch(url, {cache: 'no-store'})).text()};
          } catch (error) {
            return {error: String(error)};
          }
        }""",
        url,
    )


def direct_browser_fetch(host: str, port: int) -> Dict[str, object]:
    from camoufox.sync_api import Camoufox

    with Camoufox(
        headless=True,
        executable_path=str(resolve_binary()),
        i_know_what_im_doing=True,
    ) as browser:
        page = browser.new_page()
        page.goto("about:blank")
        return page_fetch(page, f"http://{host}:{port}/")


def authenticated_fetch(proxy: AuthenticatedSocks5) -> Dict[str, object]:
    from camoufox.sync_api import Camoufox

    with Camoufox(
        headless=True,
        executable_path=str(resolve_binary()),
        proxy={
            "server": (
                f"socks5h://{quote(USERNAME)}:{quote(PASSWORD)}"
                f"@127.0.0.1:{proxy.port}"
            )
        },
        i_know_what_im_doing=True,
    ) as browser:
        page = browser.new_page()
        page.goto("about:blank")
        return page_fetch(page, f"http://{TARGET_HOST}:{proxy.target_port}/")


def launch_wrong_password_fetch(proxy: AuthenticatedSocks5, target_host: str) -> Dict[str, object]:
    """A launch-level proxy whose password the proxy refuses (CAMOU_PROXY_AUTH)."""
    from camoufox.sync_api import Camoufox

    try:
        with Camoufox(
            headless=True,
            executable_path=str(resolve_binary()),
            geoip=False,
            proxy={"server": f"socks5://127.0.0.1:{proxy.port}",
                   "username": USERNAME, "password": "wrong-password"},
            firefox_user_prefs={"network.proxy.no_proxies_on": ""},
            i_know_what_im_doing=True,
        ) as browser:
            page = browser.new_page()
            page.goto("about:blank")
            return page_fetch(page, f"http://{target_host}:{proxy.target_port}/")
    except Exception as e:  # noqa: BLE001 - refusing to launch is failing closed
        return {"error": "launch: " + str(e).splitlines()[0][:160]}


def context_fetches(proxy: AuthenticatedSocks5, direct_host: str) -> Dict[str, Dict[str, object]]:
    """Per-context SOCKS5 proxies on a launch with none: the right credentials
    reach the target through the proxy, a wrong password reaches nothing."""
    from camoufox.sync_api import Camoufox

    server = f"socks5h://127.0.0.1:{proxy.port}"
    results: Dict[str, Dict[str, object]] = {}
    with Camoufox(
        headless=True,
        executable_path=str(resolve_binary()),
        firefox_user_prefs={"network.proxy.no_proxies_on": ""},
        i_know_what_im_doing=True,
    ) as browser:
        for name, password, host in (("right", PASSWORD, TARGET_HOST),
                                     ("wrong", "wrong-password", direct_host)):
            try:
                context = browser.new_context(
                    proxy={"server": server, "username": USERNAME, "password": password})
            except Exception as e:  # noqa: BLE001 - a refused context fails closed too
                results[name] = {"error": "context: " + str(e).splitlines()[0][:160]}
                continue
            page = context.new_page()
            page.goto("about:blank")
            results[name] = page_fetch(page, f"http://{host}:{proxy.target_port}/")
            context.close()
    return results


def fetch_with_overridden_credentials(
    proxy: AuthenticatedSocks5, credentials_value: str, target_host: str
) -> Dict[str, object]:
    from camoufox.sync_api import Camoufox

    env = {**os.environ, PROXY_CREDENTIALS_ENV: credentials_value}
    with Camoufox(
        headless=True,
        executable_path=str(resolve_binary()),
        proxy={"server": f"socks5://127.0.0.1:{proxy.port}"},
        env=env,
        firefox_user_prefs={"network.proxy.no_proxies_on": ""},
        i_know_what_im_doing=True,
    ) as browser:
        page = browser.new_page()
        page.goto("about:blank")
        return page_fetch(page, f"http://{target_host}:{proxy.target_port}/")


def main() -> int:
    direct_host = direct_target_host()
    target = QuietServer(("", 0), Target)
    threading.Thread(target=target.serve_forever, daemon=True).start()
    proxy = AuthenticatedSocks5()
    proxy.start(target.server_address[1])
    try:
        if not direct_http_available(direct_host, target.server_address[1]):
            print("FAIL: the direct control target is unreachable, so the negative checks are vacuous")
            return 1
        direct = direct_browser_fetch(direct_host, target.server_address[1])
        if direct.get("body") != MARKER:
            print(f"FAIL: the browser cannot reach the direct control target: {direct}")
            return 1

        good = authenticated_fetch(proxy)
        print(f"proxy requests: {proxy.requests}")
        print(f"authenticated result: {good}")
        failures = []
        if good.get("body") != MARKER:
            failures.append(f"authenticated fetch failed: {good}")
        expected_request = (USERNAME, TARGET_HOST, str(target.server_address[1]))
        if expected_request not in proxy.requests:
            failures.append(f"the proxy did not see a remote-DNS request for {expected_request}")

        wrong_env = json.dumps({
            f"127.0.0.1:{proxy.port}": {"username": USERNAME, "password": "wrong-password"}
        })
        wrong_password = fetch_with_overridden_credentials(proxy, wrong_env, direct_host)
        print(f"wrong-password result: {wrong_password}")
        if "error" not in wrong_password:
            failures.append("a rejected password fell back to a direct connection")
        if not proxy.failed_auth:
            failures.append("the browser never attempted SOCKS5 username/password authentication")

        malformed = fetch_with_overridden_credentials(proxy, "{broken", direct_host)
        print(f"malformed-env result: {malformed}")
        if "error" not in malformed:
            failures.append("malformed credentials fell back to a direct connection")

        launch_wrong = launch_wrong_password_fetch(proxy, direct_host)
        print(f"launch wrong-password result: {launch_wrong}")
        if "error" not in launch_wrong:
            failures.append("a launch-level proxy's rejected password fell back to a direct connection")

        before = len(proxy.requests)
        contexts = context_fetches(proxy, direct_host)
        print(f"per-context results: {contexts}")
        if contexts["right"].get("body") != MARKER:
            failures.append(f"a context's authenticated SOCKS5 proxy failed: {contexts['right']}")
        if expected_request not in proxy.requests[before:]:
            failures.append(f"the proxy did not see the context's request for {expected_request}")
        if "error" not in contexts["wrong"]:
            failures.append("a context's rejected password fell back to a direct connection")
    finally:
        proxy.close()
        target.shutdown()

    for failure in failures:
        print(f"FAIL: {failure}")
    if failures:
        return 1
    print("PASS: authenticated socks5h works at launch and per context, and proxy setup errors fail closed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
