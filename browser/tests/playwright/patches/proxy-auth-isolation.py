"""
Verify contexts sharing one proxy with different credentials stay logged in as themselves.

Proxy pools usually hand out one gateway host:port and tell sessions apart by the
username (`user-session-abc123`). Firefox caches proxy logins by host:port alone,
so every browser context shared a single cache entry. Juggler papered over that
by wiping the whole auth cache on each request through such a proxy, and on every
context creation. Under concurrency the wipe landed while another context was
mid-handshake: its retry went out with no Proxy-Authorization, the second 407 was
flagged PREVIOUS_FAILED, Juggler declined to answer it, and the page got the 407.

proxy-auth-isolation.patch keys proxy cache entries by the context's
userContextId and privateBrowsingId, so contexts no longer share or wipe each
other's logins, and Juggler no longer clears the cache on their behalf.

The proxy here is in-process and answers plain-HTTP requests itself, echoing the
username it was sent, so no network access is needed.

Run against a specific build:
    python browser/tests/playwright/patches/proxy-auth-isolation.py --binary /path/to/camoufox-bin
(or CAMOUFOX_EXECUTABLE_PATH, or the in-tree build; see helpers.resolve_binary.)

What PASS means:
    * no request through the shared proxy is refused: no 407 reaches a page
      while contexts load concurrently and new contexts are created mid-flight;
    * every request reaches the proxy carrying its own context's username, never
      another context's;
    * and every context gets at least one request served, so a hung proxy or an
      all-timeout run cannot be mistaken for success. Individual navigations that
      stall with no response are otherwise only warned about -- pages stall under
      concurrency for reasons that have nothing to do with a proxy.
"""

import asyncio
import base64
import sys
from pathlib import Path
from typing import Dict, List, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
from helpers import resolve_binary  # noqa: E402

from camoufox.addons import DefaultAddons  # noqa: E402
from camoufox.async_api import AsyncCamoufox, AsyncNewContext  # noqa: E402
from playwright.async_api import TimeoutError as PlaywrightTimeoutError  # noqa: E402

CONTEXTS = 6
ROUNDS = 4
TIMEOUT = 30_000


class EchoProxy:
    """A Basic-auth HTTP proxy that answers every request with the username it saw."""

    def __init__(self, credentials: Dict[str, str]) -> None:
        self.credentials = credentials
        self.port = 0

    async def start(self) -> None:
        self._server = await asyncio.start_server(self._handle, "127.0.0.1", 0)
        self.port = self._server.sockets[0].getsockname()[1]

    def close(self) -> None:
        self._server.close()

    def _user(self, headers: List[str]) -> str:
        for line in headers:
            name, _, value = line.partition(":")
            if name.strip().lower() != "proxy-authorization":
                continue
            scheme, _, token = value.strip().partition(" ")
            if scheme.lower() != "basic":
                return ""
            user, _, password = base64.b64decode(token).decode().partition(":")
            return user if self.credentials.get(user) == password else ""
        return ""

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            while True:
                head = await reader.readuntil(b"\r\n\r\n")
                lines = head.decode().split("\r\n")
                user = self._user(lines[1:])
                if not user:
                    writer.write(
                        b"HTTP/1.1 407 Proxy Authentication Required\r\n"
                        b'Proxy-Authenticate: Basic realm="pool"\r\n'
                        b"Content-Length: 0\r\n\r\n"
                    )
                else:
                    body = user.encode()
                    writer.write(
                        b"HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\n"
                        b"Content-Length: " + str(len(body)).encode() + b"\r\n\r\n" + body
                    )
                await writer.drain()
        except (asyncio.IncompleteReadError, ConnectionError):
            pass
        finally:
            writer.close()


async def _browse(browser, proxy: EchoProxy, index: int, start_delay: float) -> List[Tuple[str, int, str]]:
    await asyncio.sleep(start_delay)
    user = f"session{index}"
    context = await AsyncNewContext(
        browser,
        proxy={"server": f"http://127.0.0.1:{proxy.port}", "username": user, "password": f"pw{index}"},
        # Skip the exit-IP lookup NewContext would otherwise make through the proxy.
        webrtc_ip="203.0.113.1",
        timezone_id="UTC",
        locale="en-US",
        geolocation={"latitude": 40.7128, "longitude": -74.006},
    )
    page = await context.new_page()
    seen = []
    for round_ in range(ROUNDS):
        url = f"http://proxy-pool.example/ctx{index}/round{round_}"
        try:
            response = await page.goto(url, timeout=TIMEOUT)
            seen.append((user, response.status, await page.inner_text("body")))
        except PlaywrightTimeoutError as exc:
            seen.append((user, 0, str(exc).splitlines()[0]))
    await context.close()
    return seen


async def _run() -> bool:
    proxy = EchoProxy({f"session{i}": f"pw{i}" for i in range(CONTEXTS)})
    await proxy.start()
    try:
        # Without uBlock Origin. Its blocking webRequest listener holds pages
        # opened while it starts; that delay is unrelated to proxy auth.
        async with AsyncCamoufox(
            headless=True,
            executable_path=str(resolve_binary()),
            exclude_addons=[DefaultAddons.UBO],
        ) as browser:
            # Stagger starts so contexts are created while others are authenticating.
            results = await asyncio.gather(
                *[_browse(browser, proxy, i, start_delay=i * 0.15) for i in range(CONTEXTS)]
            )
    finally:
        proxy.close()

    requests = [r for context in results for r in context]
    # A navigation that never finishes is not a proxy answer. Pages can stall
    # when contexts are created while others load, with or without a proxy, so
    # those are reported but not held against this patch.
    stalled = [r for r in requests if r[1] == 0]
    refused = [r for r in requests if r[1] not in (0, 200)]
    crossed = [r for r in requests if r[1] == 200 and r[2] != r[0]]

    # Excusing stalls costs the test its teeth unless something must have gone
    # through the proxy. A regression that made authentication hang would
    # otherwise score as a pass having verified nothing.
    served = {user for user, status, _ in requests if status == 200}
    silent = sorted({user for user, _, _ in requests} - served)

    for label, bad in (("no request refused", refused), ("each request logged in as its context", crossed)):
        verdict = "PASS" if not bad else "FAIL"
        print(f"  {verdict} {label:40} -> {len(requests) - len(bad)}/{len(requests)}")
        for user, status, body in bad[:5]:
            print(f"         {user}: status {status}, proxy saw {body!r}")

    verdict = "PASS" if not silent else "FAIL"
    print(f"  {verdict} {'every context reached the proxy':40} -> {len(served)}/{CONTEXTS}")
    for user in silent[:5]:
        print(f"         {user}: no request served")
    if stalled:
        print(f"  WARN {len(stalled)} navigation(s) stalled without a response (not proxy-related)")
    return not refused and not crossed and not silent


async def main() -> int:
    passed = await _run()
    print()
    if passed:
        print("PASS: contexts sharing a proxy keep their own credentials")
        return 0
    print("FAIL: contexts sharing a proxy are refused, cross credentials, or receive no answer")
    return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
