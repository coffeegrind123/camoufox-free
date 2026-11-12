"""
A driver's move off the page leaves it where the pointer goes, as a mouse does.

page.mouse.move() to a point outside the viewport took the pointer to the
chrome window's own origin, so the page's mouseout and pointerout always said
the pointer left at the window's top-left corner: (0, -85) for a Windows
identity, whichever edge it was sent through. Stock Firefox 159 on Linux, by
OS (XTest) motion, leaves where the pointer crosses: up into the toolbar at
its own x, or off the side of the window at its own y. The move now takes the
pointer toward the point it was sent to (MouseDispatch.leaveContent).

Checked on a private Xvfb display, headed: a move up into the toolbar strip,
then one off the right edge, each from a point inside the page.

    python browser/tests/playwright/patches/driven-exit-point.py
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from helpers import hidden_display, launch_kwargs  # noqa: E402

PAGE = '<!doctype html><body style="margin:0;height:1200px"></body>'
# Installed through evaluate(), which runs in an isolated world: a page
# script's own globals are not visible from there, its listeners' DOM events are.
RECORD = """() => {
  window.__out = [];
  for (const t of ['mouseout', 'pointerout'])
    addEventListener(t, e => { if (!e.relatedTarget) __out.push([t, e.clientX, e.clientY]); }, true);
}"""

INSIDE = (350, 350)
# Into the toolbar strip above the content, at the same x.
UP = (350, -40)


def exits(page, to):
    page.mouse.move(*INSIDE)
    page.wait_for_timeout(300)
    page.evaluate("window.__out = []")
    page.mouse.move(*to)
    page.wait_for_timeout(500)
    return page.evaluate("window.__out")


def main() -> int:
    from camoufox.sync_api import Camoufox

    failures = []
    with hidden_display(), Camoufox(**launch_kwargs(headless=False, os="windows",
                                                    i_know_what_im_doing=True)) as browser:
        page = browser.new_page()
        page.set_content(PAGE)
        page.evaluate(RECORD)
        width = page.evaluate("innerWidth")
        up = exits(page, UP)
        side_to = (width + 400, INSIDE[1])
        side = exits(page, side_to)

    # The pointer moves in device pixels, so under a fractional drawn scale or
    # zoom the page reads its own coordinate back to within a CSS pixel
    # (350.2 for 350), in stock Firefox as here.
    def near(a, b):
        return abs(a - b) < 1

    for name, got, check in (
        ("up into the toolbar", up, lambda x, y: near(x, UP[0]) and y < 0),
        ("off the right edge", side, lambda x, y: x >= width - 1 and near(y, INSIDE[1])),
    ):
        if not got:
            failures.append(f"{name}: the page saw no mouseout/pointerout")
            continue
        bad = [e for e in got if not check(e[1], e[2])]
        if bad:
            failures.append(f"{name}: left at {[(e[0], e[1], e[2]) for e in bad]}")

    for f in failures:
        print(f"FAIL: {f}")
    if failures:
        return 1
    print(f"PASS: the pointer leaves the page where it was moved: up {json.dumps(up)}, side {json.dumps(side)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
