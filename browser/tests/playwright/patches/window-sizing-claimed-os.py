r"""
A Windows or macOS identity's window frame measures as stock Firefox's on it.

A page can measure the frame around its content area: outerWidth - innerWidth,
outerHeight - innerHeight, and where the content sits in the window
(mozInnerScreenX/Y - screenX/Y, or an event's screenX - clientX). Those came
from the host's real window, so a Windows identity on Linux reported GTK's
frame: 86x192 under XWayland and 52x137 on Wayland, with the content 43,149 into
the window, where stock Firefox 159 on Windows 11 measures 16x93 and 8,85 (a
normal window at 100% scale: 8px resize borders, the tab strip and navigation
toolbar above the content).

window-sizing-claimed-os.patch reports the frame from the real content area plus
the claimed OS's insets (window.frameLeft/Top/Right/Bottom, which the launcher
sets for a Windows or macOS identity on another host, per display scale), in
every frame of the page: a cross-site iframe, which Fission puts in another
process, reads the same outer size, and its screen points sit at its offset
inside the top page's content.

Cases:
  * a normal Windows window at 100%: 16x93, content at 8,85;
  * the same at 125% (a scale fpgen draws): 14x92, content at 7,85;
  * a Windows window the launcher drew maximized: stock's maximized geometry,
    outer the available area plus 16x16 at -8,-8, content at the available
    area's origin plus the 85px of toolbars;
  * a macOS window: no side frame, 85px of toolbars;
and for the first, the same after a viewport change.

A fullscreen window has no frame (outer == inner). It is not checked here: on
this display, with no window manager, a window never enters fullscreen.

The window opens on the guard's private Xvfb display, with no window manager.

    python browser/tests/playwright/patches/window-sizing-claimed-os.py
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from helpers import hidden_display, launch_kwargs  # noqa: E402

# Setting any window.* key leaves the window's geometry to the caller (the
# launcher no longer fits the drawn window to the display), so the size is set
# too, inside the guard's 1400x900 display.
SPOOFED = {"window.screenX": 300, "window.screenY": 200,
           "window.outerWidth": 1000, "window.outerHeight": 650}

# (left, top, right, bottom) content insets in the window.
# Stock Firefox 159, Windows 11, 1920x1080 at 100%, a normal window: inner
# 1280x887, outer 1296x980, mozInnerScreenX/Y = screenX/Y + 8 / + 85.
WINDOWS_NORMAL = (8, 85, 8, 8)
# fpgen's records at 125%: 14px of borders, the same 85px of toolbars.
WINDOWS_125 = (7, 85, 7, 7)
# Maximized: the top border hangs off the screen above the toolbars.
WINDOWS_MAXIMIZED = (8, 93, 8, 8)
MACOS = (0, 85, 0, 0)

# A screen whose available area the maximized window is drawn to fill, at the
# launcher's modern-screen floor (raise_screen_to_modern_floor), which would
# otherwise enlarge it past the drawn window.
SCREEN = (1366, 768)

# CamoufoxWindow.sys.mjs holds the startup size for 5 s from the window opening.
HOLD_MS = 5500

TOP_URL = "https://top.camoufox.test/"
FRAME_URL = "https://frame.camoufox.test/"
IFRAME_AT = (50, 40)

RECORDER = """<script>
const geometry = () => ({screenX, screenY, mozInnerScreenX, mozInnerScreenY,
                         outerWidth, outerHeight, innerWidth, innerHeight,
                         availLeft: screen.availLeft, availTop: screen.availTop,
                         availWidth: screen.availWidth, availHeight: screen.availHeight});
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


def maximized_fingerprint() -> dict:
    """A drawn Windows identity whose window is maximized, as fpgen records one:
    outer the available area plus 16x16, at -8,-8."""
    from camoufox.fingerprints import generate_fingerprint

    fp = generate_fingerprint(os="windows")
    width, height = SCREEN
    fp["screen"].update(width=width, height=height, availWidth=width,
                        availHeight=height - 48, availLeft=0, availTop=0)
    fp["window"].update(outerWidth=width + 16, outerHeight=height - 48 + 16,
                        screenX=-8, screenY=-8)
    return fp


def probe(resize: bool = False, **kwargs) -> dict:
    from camoufox.sync_api import Camoufox

    with hidden_display(), Camoufox(**launch_kwargs(headless=False, i_know_what_im_doing=True,
                                                    **kwargs)) as browser:
        page = browser.new_page()
        # A context route: the cross-site iframe loads in another process.
        page.context.route("https://*.camoufox.test/**", serve)
        page.goto(TOP_URL)
        page.frame_locator("iframe").locator("body").wait_for(state="attached")
        # CamoufoxWindow.sys.mjs resizes the window for 5 s after it opens; a
        # page and its iframe measured across one of those resizes differ.
        page.wait_for_timeout(HOLD_MS)
        result = {"first": measure(page)}
        if resize:
            page.set_viewport_size({"width": 800, "height": 500})
            result["resized"] = measure(page)
        return result


def check(name: str, result: dict, insets: tuple, failures: list,
          expect_outer=None, expect_position=None) -> None:
    left, top, right, bottom = insets
    page, frame = result["top"], result["frame"]
    g = page["geometry"]
    want = (left + right, top + bottom)
    got = (g["outerWidth"] - g["innerWidth"], g["outerHeight"] - g["innerHeight"])
    if got != want:
        failures.append(f"{name}: outer - inner = {got[0]}x{got[1]}, stock {want[0]}x{want[1]}")
    if expect_outer and (g["outerWidth"], g["outerHeight"]) != expect_outer:
        failures.append(f"{name}: outer size {g['outerWidth']}x{g['outerHeight']}, "
                        f"stock {expect_outer[0]}x{expect_outer[1]}")
    if expect_position and (g["screenX"], g["screenY"]) != expect_position:
        failures.append(f"{name}: screenX/Y {g['screenX']},{g['screenY']}, "
                        f"stock {expect_position[0]},{expect_position[1]}")
    for axis, inset in (("X", left), ("Y", top)):
        offset = g[f"mozInnerScreen{axis}"] - g[f"screen{axis}"]
        if abs(offset - inset) > 1:
            failures.append(f"{name}: mozInnerScreen{axis} - screen{axis} = {offset}, stock {inset}")
        e = page["event"]
        if abs(e[f"screen{axis}"] - e[f"client{axis}"] - g[f"mozInnerScreen{axis}"]) > 1:
            failures.append(f"{name}: event screen{axis} - client{axis} = "
                            f"{e[f'screen{axis}'] - e[f'client{axis}']}, but mozInnerScreen{axis} = "
                            f"{g[f'mozInnerScreen{axis}']}")

    f = frame["geometry"]
    if (f["outerWidth"], f["outerHeight"]) != (g["outerWidth"], g["outerHeight"]):
        failures.append(f"{name}: the cross-site iframe reads outer {f['outerWidth']}x"
                        f"{f['outerHeight']}, its page {g['outerWidth']}x{g['outerHeight']}")
    for axis, at in (("X", IFRAME_AT[0]), ("Y", IFRAME_AT[1])):
        want_at = g[f"mozInnerScreen{axis}"] + at
        if abs(f[f"mozInnerScreen{axis}"] - want_at) > 1:
            failures.append(f"{name}: the iframe's mozInnerScreen{axis} = "
                            f"{f[f'mozInnerScreen{axis}']}, its place in the page is {want_at}")
        e = frame["event"]
        if abs(e[f"screen{axis}"] - e[f"client{axis}"] - f[f"mozInnerScreen{axis}"]) > 1:
            failures.append(f"{name}: an iframe event's screen{axis} - client{axis} = "
                            f"{e[f'screen{axis}'] - e[f'client{axis}']}, but the iframe's "
                            f"mozInnerScreen{axis} = {f[f'mozInnerScreen{axis}']}")


def main() -> int:
    failures: list = []
    results = {}

    results["windows"] = normal = probe(resize=True, os="windows", config=SPOOFED)
    check("Windows, normal", normal["first"], WINDOWS_NORMAL, failures,
          expect_outer=(SPOOFED["window.outerWidth"], SPOOFED["window.outerHeight"]))
    check("Windows, after a viewport change", normal["resized"], WINDOWS_NORMAL, failures)

    results["windows-125"] = scaled = probe(
        os="windows", config={**SPOOFED, "window.devicePixelRatio": 1.25})
    check("Windows at 125%", scaled["first"], WINDOWS_125, failures)

    results["windows-maximized"] = maximized = probe(os="windows",
                                                     fingerprint=maximized_fingerprint())
    g = maximized["first"]["top"]["geometry"]
    check("Windows, maximized", maximized["first"], WINDOWS_MAXIMIZED, failures,
          expect_outer=(g["availWidth"] + 16, g["availHeight"] + 16),
          expect_position=(g["availLeft"] - 8, g["availTop"] - 8))

    results["macos"] = mac = probe(os="macos", config=SPOOFED)
    check("macOS", mac["first"], MACOS, failures)

    print(json.dumps(results))
    for failure in failures:
        print(f"FAIL: {failure}")
    if failures:
        return 1
    print("PASS: the window frame, in the page and a cross-site iframe, measures as stock's "
          "on the claimed OS: normal, scaled, maximized and macOS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
