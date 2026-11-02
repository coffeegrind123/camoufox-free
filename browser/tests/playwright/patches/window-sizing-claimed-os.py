r"""
A Windows identity's window frame measures as stock Windows Firefox's.

A page can measure the frame around its content area: outerWidth - innerWidth,
outerHeight - innerHeight, and where the content sits in the window
(mozInnerScreenX/Y - screenX/Y, or an event's screenX - clientX). Those came
from the host's real window, so a Windows identity on Linux reported GTK's
frame: 86x192 under XWayland and 52x137 on Wayland, with the content 43,149 into
the window, where stock Firefox 159 on Windows 11 measures 16x93 and 8,85 (a
normal window at 100% scale: 8px resize borders, the tab strip and navigation
toolbar above the content).

window-sizing-claimed-os.patch reports the frame from the real content area plus
the claimed OS's insets (window.frameLeft/Top/Right/Bottom, set by the launcher
for a Windows identity on another host), in every frame of the page: a
cross-site iframe, which Fission puts in another process, reads the same outer
size, and its screen points sit at its offset inside the top page's content.

The window opens on the guard's private Xvfb display, with no window manager.

    python browser/tests/playwright/patches/window-sizing-claimed-os.py
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from helpers import hidden_display, launch_kwargs  # noqa: E402

# Stock Firefox 159, Windows 11, 1920x1080 at 100% scale, a normal window:
# inner 1280x887, outer 1296x980, mozInnerScreenX/Y = screenX/Y + 8 / + 85.
WINDOWS_FRAME = {"left": 8, "top": 85, "right": 8, "bottom": 8}

# Setting any window.* key leaves the window's geometry to the caller (the
# launcher no longer fits the drawn window to the display), so the size is set
# too, inside the guard's 1400x900 display.
SPOOFED = {"window.screenX": 300, "window.screenY": 200,
           "window.outerWidth": 1000, "window.outerHeight": 650}

TOP_URL = "https://top.camoufox.test/"
FRAME_URL = "https://frame.camoufox.test/"
IFRAME_AT = (50, 40)

RECORDER = """<script>
const geometry = () => ({screenX, screenY, mozInnerScreenX, mozInnerScreenY,
                         outerWidth, outerHeight, innerWidth, innerHeight});
addEventListener('mousedown', e => {
  const result = {geometry: geometry(),
    event: {screenX: e.screenX, screenY: e.screenY, clientX: e.clientX, clientY: e.clientY}};
  if (window.top === window) {
    document.body.dataset.result = JSON.stringify(result);
  } else {
    parent.postMessage(JSON.stringify(result), '*');
  }
});
</script>"""

TOP_PAGE = f"""<body style="margin:0"><iframe src="{FRAME_URL}"
  style="position:absolute;left:{IFRAME_AT[0]}px;top:{IFRAME_AT[1]}px;width:300px;height:200px;border:0"></iframe>
<script>addEventListener('message', e => document.body.dataset.frame = e.data);</script>
{RECORDER}</body>"""
FRAME_PAGE = f'<body style="margin:0;background:#eee">{RECORDER}</body>'


def serve(route) -> None:
    body = TOP_PAGE if route.request.url.startswith(TOP_URL) else FRAME_PAGE
    route.fulfill(status=200, content_type="text/html", body=body)


def measure(page) -> dict:
    page.evaluate("delete document.body.dataset.result; delete document.body.dataset.frame")
    page.mouse.click(20, 20)
    page.mouse.click(IFRAME_AT[0] + 30, IFRAME_AT[1] + 30)
    page.wait_for_function("document.body.dataset.result && document.body.dataset.frame")
    return {"top": json.loads(page.get_attribute("body", "data-result")),
            "frame": json.loads(page.get_attribute("body", "data-frame"))}


def probe() -> dict:
    from camoufox.sync_api import Camoufox

    with hidden_display(), Camoufox(**launch_kwargs(headless=False, os="windows",
                                                    config=SPOOFED,
                                                    i_know_what_im_doing=True)) as browser:
        page = browser.new_page()
        # A context route: the cross-site iframe loads in another process.
        page.context.route("https://*.camoufox.test/**", serve)
        page.goto(TOP_URL)
        page.frame_locator("iframe").locator("body").wait_for(state="attached")
        first = measure(page)
        page.set_viewport_size({"width": 800, "height": 500})
        resized = measure(page)
        return {"first": first, "resized": resized}


def check(name: str, result: dict, failures: list, expect_outer=None) -> None:
    top, frame = result["top"], result["frame"]
    g = top["geometry"]
    frame_x = WINDOWS_FRAME["left"] + WINDOWS_FRAME["right"]
    frame_y = WINDOWS_FRAME["top"] + WINDOWS_FRAME["bottom"]
    if (g["outerWidth"] - g["innerWidth"], g["outerHeight"] - g["innerHeight"]) != (frame_x, frame_y):
        failures.append(f"{name}: outer - inner = {g['outerWidth'] - g['innerWidth']}x"
                        f"{g['outerHeight'] - g['innerHeight']}, stock Windows {frame_x}x{frame_y}")
    if expect_outer and (g["outerWidth"], g["outerHeight"]) != expect_outer:
        failures.append(f"{name}: outer size {g['outerWidth']}x{g['outerHeight']}, "
                        f"the identity's is {expect_outer[0]}x{expect_outer[1]}")
    for axis, inset in (("X", WINDOWS_FRAME["left"]), ("Y", WINDOWS_FRAME["top"])):
        offset = g[f"mozInnerScreen{axis}"] - g[f"screen{axis}"]
        if abs(offset - inset) > 1:
            failures.append(f"{name}: mozInnerScreen{axis} - screen{axis} = {offset}, "
                            f"stock Windows {inset}")
        e = top["event"]
        if abs(e[f"screen{axis}"] - e[f"client{axis}"] - g[f"mozInnerScreen{axis}"]) > 1:
            failures.append(f"{name}: event screen{axis} - client{axis} = "
                            f"{e[f'screen{axis}'] - e[f'client{axis}']}, but mozInnerScreen{axis} = "
                            f"{g[f'mozInnerScreen{axis}']}")

    f = frame["geometry"]
    if (f["outerWidth"], f["outerHeight"]) != (g["outerWidth"], g["outerHeight"]):
        failures.append(f"{name}: the cross-site iframe reads outer {f['outerWidth']}x"
                        f"{f['outerHeight']}, its page {g['outerWidth']}x{g['outerHeight']}")
    for axis, at in (("X", IFRAME_AT[0]), ("Y", IFRAME_AT[1])):
        want = g[f"mozInnerScreen{axis}"] + at
        if abs(f[f"mozInnerScreen{axis}"] - want) > 1:
            failures.append(f"{name}: the iframe's mozInnerScreen{axis} = "
                            f"{f[f'mozInnerScreen{axis}']}, its place in the page is {want}")
        e = frame["event"]
        if abs(e[f"screen{axis}"] - e[f"client{axis}"] - f[f"mozInnerScreen{axis}"]) > 1:
            failures.append(f"{name}: an iframe event's screen{axis} - client{axis} = "
                            f"{e[f'screen{axis}'] - e[f'client{axis}']}, but the iframe's "
                            f"mozInnerScreen{axis} = {f[f'mozInnerScreen{axis}']}")


def main() -> int:
    result = probe()
    print(json.dumps(result))
    failures = []
    check("at launch", result["first"], failures,
          expect_outer=(SPOOFED["window.outerWidth"], SPOOFED["window.outerHeight"]))
    check("after a viewport change", result["resized"], failures)
    for failure in failures:
        print(f"FAIL: {failure}")
    if failures:
        return 1
    print("PASS: the window frame, in the page and a cross-site iframe, measures as stock Windows'")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
