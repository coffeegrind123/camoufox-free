"""
Verify that navigator.doNotTrack and the DNT request header share one config.

The launcher's pref mapping could only represent DNT "1" or unset, so an
explicit "0" came back as "unspecified". The browser patch reads the config
directly, and only "1" sends a DNT header. Values this fork does not model,
such as "0" and "unspecified", are observable in the page but send no header.

    python browser/tests/playwright/patches/do-not-track.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from helpers import launch_kwargs  # noqa: E402

URL = "https://do-not-track.test/"
CASES = (
    (None, "unspecified", None),
    ("0", "0", None),
    ("1", "1", "1"),
    ("unspecified", "unspecified", None),
)


def probe(value):
    from camoufox.sync_api import Camoufox

    options = launch_kwargs(os="linux", i_know_what_im_doing=True)
    if value is not None:
        options["config"] = {"navigator.doNotTrack": value}
    headers = {}
    with Camoufox(**options) as browser:
        page = browser.new_page()

        def fulfill(route):
            headers.update(route.request.all_headers())
            route.fulfill(body="<title>DNT</title>", content_type="text/html")

        page.route(URL, fulfill)
        page.goto(URL)
        getter = page.evaluate("navigator.doNotTrack")
    return getter, headers.get("dnt")


def main() -> int:
    failures = []
    for configured, expected_getter, expected_header in CASES:
        getter, header = probe(configured)
        label = "unset" if configured is None else configured
        print(f"  {label:11} -> navigator.doNotTrack={getter!r}, DNT={header!r}")
        if getter != expected_getter:
            failures.append(f"{label}: getter is {getter!r}, expected {expected_getter!r}")
        if header != expected_header:
            failures.append(f"{label}: DNT header is {header!r}, expected {expected_header!r}")

    print()
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}")
        return 1
    print("PASS: navigator.doNotTrack and the DNT header follow the configured value.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
