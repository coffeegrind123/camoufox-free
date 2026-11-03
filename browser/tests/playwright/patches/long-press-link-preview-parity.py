r"""
Verify a long press on a link opens Link Preview, as stock Firefox does.

Stock Firefox 158 and 159 ship browser.ml.linkPreview.enabled = true with
longPress = true (longPressMs 1000). Holding the primary button on a link opens
the preview card and fetches the link target with an anonymous request that
carries `x-firefox-ai: 1` (LinkPreviewChild.fetchHTML). Measured on stock 159.0
on Windows 11: the page sees the same pointer, mouse, click and focus events
with the feature on or off, but the target's server sees that request only
with it on. Turning the feature off therefore makes a long press observable
from the network, so camoufox keeps the stock default.

The guard launches camoufox through Playwright, headed on a private Xvfb display,
with Marionette also enabled so the chrome document can be inspected. It holds
the mouse on a link for twice the long-press delay and asserts the
#link-preview-panel is open. A second launch with the feature turned off
asserts the same press opens no panel, so the check is not vacuous.

    python browser/tests/playwright/patches/long-press-link-preview-parity.py
"""

import http.server
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from helpers import Marionette, free_port, hidden_display, marionette_args, marionette_env, resolve_binary  # noqa: E402

PAGE = b'<!DOCTYPE html><html><body><a id="a" href="/article" style="font-size:40px">A link</a></body></html>'
PANEL = 'return document.getElementById("link-preview-panel")?.state ?? null;'


def serve():
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(PAGE)))
            self.end_headers()
            self.wfile.write(PAGE)

        def log_message(self, *args):
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def panel_after_long_press(binary: Path, url: str, prefs: dict):
    from camoufox.sync_api import Camoufox

    port = free_port()
    with Camoufox(headless=False, executable_path=str(binary), args=marionette_args(), env=marionette_env(),
                  firefox_user_prefs={"marionette.port": port, **prefs}, i_know_what_im_doing=True) as browser:
        page = browser.new_page()
        page.goto(url)
        box = page.locator("#a").bounding_box()
        page.mouse.move(box["x"] + 10, box["y"] + box["height"] / 2)
        page.mouse.down()
        time.sleep(2)
        m = Marionette(port)
        try:
            return m.js(PANEL)
        finally:
            m.close()
            page.mouse.up()


def main() -> int:
    binary = resolve_binary()
    server = serve()
    url = f"http://127.0.0.1:{server.server_port}/"
    try:
        with hidden_display():
            default = panel_after_long_press(binary, url, {})
            disabled = panel_after_long_press(binary, url, {"browser.ml.linkPreview.enabled": False})
    finally:
        server.shutdown()

    print(f"  default: #link-preview-panel {default}; feature turned off: {disabled}")
    failures = []
    if disabled is not None:
        failures.append(f"with the feature off the press still opened a panel ({disabled}) -- the check is vacuous")
    if default != "open":
        failures.append(f"a long press on a link opened no Link Preview panel ({default}); stock Firefox opens one")
    for failure in failures:
        print(f"FAIL: {failure}")
    if failures:
        return 1
    print("PASS: a long press on a link opens the Link Preview panel, as in stock Firefox.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
