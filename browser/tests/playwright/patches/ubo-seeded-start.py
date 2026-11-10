"""
Verify the bundled uBlock Origin starts like a warm install on a fresh profile:
it loads the selfie the build generated (scripts/fetch-ubo.py seed) instead of
compiling every list, and saves it so a kept profile's next launch starts warm
too.

Every launch is a fresh profile, which uBO treats as a fresh install. Unseeded,
it compiles its lists for 10-25 s, and its blocking webRequest listener answers
no request meanwhile, so a page's own same-origin requests stalled 8-21 s and
filtering began 9-24 s after the page loaded. A warm install (stock Firefox with
uBO's saved selfie) stalls 1-3 s at most and filters within 1-2 s.

A local page fetches itself every 250 ms and the ad script every 500 ms, through
a proxy that refuses every CONNECT: the ad fetch can only succeed as uBO's
redirect to its neutered surrogate, so its first success is when uBO filters.

    seeded   the build carries camoufox-seed/ beside its uBO
    stall    no same-origin request waits over STALL_S in the first OBSERVE_S
    filters  uBO filters within FILTER_S of the page's navigation
    kept     the same, on a second launch of a profile kept past uBO's selfie
             delay: the seed was saved to storage, not read once and lost

    python browser/tests/playwright/patches/ubo-seeded-start.py
"""

import http.server
import json
import queue
import shutil
import socket
import sys
import tempfile
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from helpers import resolve_binary  # noqa: E402

OBSERVE_S = 20
STALL_S = 4.0
FILTER_S = 8.0
# Past uBO's selfieDelayInSeconds (53), when the seed layer saves what it served.
KEEP_OPEN_S = 75
AD_URL = "https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js"
PAGE = """<!doctype html><body><script>
let n = 0;
const report = d => fetch('/r', {method: 'POST', body: JSON.stringify(d)});
function tick() {
  n++;
  report({k: 'tick', sent: Date.now()});
  if (n % 2 === 1) {
    const sent = Date.now();
    fetch('AD_URL?' + n, {mode: 'no-cors', cache: 'no-store'})
      .then(() => 'loaded', () => 'error')
      .then(r => report({k: 'ad', sent, r}));
  }
  setTimeout(tick, 250);
}
report({k: 'load', nav: performance.timeOrigin});
setTimeout(tick, 250);
</script></body>""".replace("AD_URL", AD_URL)


def serve(reports: queue.Queue):
    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(PAGE.encode())

        def do_POST(self):
            data = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
            data["arrived"] = time.time() * 1000
            reports.put(data)
            self.send_response(204)
            self.end_headers()

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def refusing_proxy() -> socket.socket:
    def handle(conn):
        with conn:
            conn.recv(4096)
            conn.sendall(b"HTTP/1.1 502 Bad Gateway\r\nContent-Length: 0\r\n\r\n")

    def accept():
        while True:
            try:
                conn, _ = sock.accept()
            except OSError:
                return
            threading.Thread(target=handle, args=(conn,), daemon=True).start()

    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    sock.listen()
    threading.Thread(target=accept, daemon=True).start()
    return sock


def observe(context, url: str, reports: queue.Queue) -> dict:
    while not reports.empty():
        reports.get()
    page = context.pages[0] if context.pages else context.new_page()
    page.goto(url, wait_until="commit", timeout=120000)
    seen = []
    end = time.monotonic() + OBSERVE_S
    while time.monotonic() < end:
        try:
            seen.append(reports.get(timeout=0.5))
        except queue.Empty:
            pass
    nav = next((d["nav"] for d in seen if d["k"] == "load"), None)
    ticks = [d for d in seen if d["k"] == "tick"]
    ads = sorted((d for d in seen if d["k"] == "ad"), key=lambda d: d["sent"])
    filtered = next((d["sent"] for d in ads if d["r"] == "loaded"), None)
    return {
        "ticks": len(ticks),
        "stall_s": max(((d["arrived"] - d["sent"]) / 1000 for d in ticks), default=None),
        "filters_s": (filtered - nav) / 1000 if filtered is not None and nav is not None else None,
    }


def verdicts(name: str, got: dict) -> list:
    failures = []
    if not got["ticks"]:
        failures.append(f"{name}: the page reported nothing -- check is vacuous")
        return failures
    if got["stall_s"] > STALL_S:
        failures.append(f"{name}: a same-origin request waited {got['stall_s']:.1f}s (limit {STALL_S}s)")
    if got["filters_s"] is None:
        failures.append(f"{name}: uBO did not filter within {OBSERVE_S}s of the page")
    elif got["filters_s"] > FILTER_S:
        failures.append(f"{name}: uBO filtered {got['filters_s']:.1f}s after the page (limit {FILTER_S}s)")
    return failures


def main() -> int:
    from camoufox.addons import DefaultAddons, get_addon_path
    from camoufox.sync_api import Camoufox

    binary = resolve_binary()
    seed = Path(get_addon_path(DefaultAddons.UBO.name, binary), "camoufox-seed", "index.json")
    if not seed.is_file():
        print(f"FAIL: the build carries no uBO seed at {seed} (scripts/fetch-ubo.py seed)")
        return 1

    reports: queue.Queue = queue.Queue()
    srv = serve(reports)
    proxy = refusing_proxy()
    profile = tempfile.mkdtemp(prefix="ubo-seeded-")
    url = f"http://127.0.0.1:{srv.server_address[1]}/"
    kwargs = dict(headless=True, executable_path=str(binary), i_know_what_im_doing=True, geoip=False,
                  persistent_context=True, user_data_dir=profile,
                  proxy={"server": f"http://127.0.0.1:{proxy.getsockname()[1]}"})
    results = {}
    try:
        started = time.monotonic()
        with Camoufox(**kwargs) as context:
            results["fresh"] = observe(context, url, reports)
            time.sleep(max(0.0, KEEP_OPEN_S - (time.monotonic() - started)))
        with Camoufox(**kwargs) as context:
            results["kept"] = observe(context, url, reports)
    finally:
        proxy.close()
        srv.shutdown()
        shutil.rmtree(profile, ignore_errors=True)

    failures = []
    for name, got in results.items():
        stall = f"{got['stall_s']:.1f}s" if got["stall_s"] is not None else "-"
        filters = f"{got['filters_s']:.1f}s" if got["filters_s"] is not None else "never"
        print(f"{name}: longest same-origin wait {stall}, uBO filters {filters} after the page")
        failures += verdicts(name, got)
    print()
    if failures:
        for f in failures:
            print(f"FAIL: {f}")
        return 1
    print("PASS: uBO starts from its bundled selfie and keeps it.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
