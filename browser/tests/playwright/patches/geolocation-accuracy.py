"""
Verify a position given without an accuracy reports one a device would
(geolocation-spoofing.patch).

The launch's `geolocation:*` keys and Playwright's per-context `geolocation`
option both give coordinates without an accuracy, and no device reports 0.
The launch's position had an estimate from the coordinates' precision; a
context's reported accuracy 0.

What PASS means: both report the width of their coordinates' last decimal place
in metres, a degree of longitude being 111,320 m at the equator, and an accuracy
the caller gave is kept.

    python browser/tests/playwright/patches/geolocation-accuracy.py
"""

import functools
import http.server
import math
import sys
import tempfile
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from helpers import launch_kwargs  # noqa: E402

LAUNCH = (48.8566, 2.3522)
CONTEXT = (35.6762, 139.6503)

READ = """() => new Promise((resolve, reject) => navigator.geolocation.getCurrentPosition(
  p => resolve([p.coords.latitude, p.coords.longitude, p.coords.accuracy]),
  e => reject(new Error(e.message))))"""


def estimate(latitude: float, longitude: float) -> float:
    decimals = min(len(repr(v).split(".")[1]) for v in (latitude, longitude))
    return 111320 * math.cos(math.radians(latitude)) / 10 ** decimals


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


def main() -> int:
    from camoufox.sync_api import Camoufox

    site = tempfile.mkdtemp()
    Path(site, "p.html").write_text("<!doctype html><body>x</body>")
    srv = http.server.ThreadingHTTPServer(
        ("127.0.0.1", 0), functools.partial(Quiet, directory=site))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{srv.server_address[1]}/p.html"

    config = {"geolocation:latitude": LAUNCH[0], "geolocation:longitude": LAUNCH[1]}
    cases = {
        "launch": ({}, [*LAUNCH, estimate(*LAUNCH)]),
        "context": ({"geolocation": dict(zip(("latitude", "longitude"), CONTEXT))},
                    [*CONTEXT, estimate(*CONTEXT)]),
        "given": ({"geolocation": {"latitude": CONTEXT[0], "longitude": CONTEXT[1], "accuracy": 25}},
                  [*CONTEXT, 25]),
    }
    failures = []
    try:
        with Camoufox(**launch_kwargs(config=config, i_know_what_im_doing=True)) as browser:
            for name, (options, expected) in cases.items():
                context = browser.new_context(permissions=["geolocation"], **options)
                page = context.new_page()
                page.goto(url)
                got = page.evaluate(READ)
                print(f"  {name:8}: {got}  (expected {expected})")
                if not all(math.isclose(g, e, rel_tol=1e-9) for g, e in zip(got, expected)):
                    failures.append(f"{name}: reports {got}, expected {expected}")
                context.close()
    finally:
        srv.shutdown()

    print()
    if failures:
        for f in failures:
            print(f"FAIL: {f}")
        return 1
    print("PASS: every position reports an accuracy, estimated when none was given.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
