r"""
Every screen coordinate a page can read agrees with the spoofed window.screenX/Y.

window.screenX/Y report the identity's position, but mozInnerScreenX/Y and the
screenX/Y of mouse and touch events were computed from the real window. Wherever
the real window is not at the spoofed position (any X11 desktop that places it,
a second monitor), the page could read the real position and see that

    mozInnerScreenY - screenY

is larger than the whole window's chrome. Stock places the content area inside
the window, and an event's screenX - clientX equals mozInnerScreenX. An event the
page constructs keeps the screen point it was given.

Launch moves the first window to the identity's position (CamoufoxWindow.sys.mjs
holds it there for 5 s), so on its own the real and spoofed positions agree and
nothing here would be exercised. Once the hold has ended the guard moves the
real window elsewhere through Xlib, as a window manager or the user would, and
reads the real position back from the X server to prove the move happened.
The first window keeps reporting the identity's screenX/Y after that move.

    python browser/tests/playwright/patches/window-screen-origin.py
"""

import ctypes
import ctypes.util
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from helpers import hidden_display, launch_kwargs  # noqa: E402

# Setting any window.* key leaves the window's geometry to the caller (the
# launcher no longer fits the drawn window to the display), so the size is set
# too, inside the guard's 1400x900 display.
SPOOFED = {"window.screenX": 300, "window.screenY": 200,
           "window.outerWidth": 1000, "window.outerHeight": 650}

# Where the guard puts the real window once the startup hold is over: away from
# SPOOFED, inside the 1400x900 display.
REAL = (40, 30)
# CamoufoxWindow.sys.mjs moves the first window back to the identity's
# position for 5 s after it opens.
POSITION_HOLD_S = 6


class _X:
    """The few Xlib calls needed to move the browser's top-level window."""

    def __init__(self):
        name = ctypes.util.find_library("X11")
        if not name:
            raise SystemExit("FAIL: libX11 not found -- cannot move the real window, check is vacuous")
        self.lib = ctypes.CDLL(name)
        self.lib.XOpenDisplay.restype = ctypes.c_void_p
        self.lib.XOpenDisplay.argtypes = [ctypes.c_char_p]
        self.lib.XDefaultRootWindow.restype = ctypes.c_ulong
        self.lib.XDefaultRootWindow.argtypes = [ctypes.c_void_p]
        self.lib.XQueryTree.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.POINTER(ctypes.c_ulong),
                                        ctypes.POINTER(ctypes.c_ulong),
                                        ctypes.POINTER(ctypes.POINTER(ctypes.c_ulong)),
                                        ctypes.POINTER(ctypes.c_uint)]
        self.lib.XGetGeometry.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.POINTER(ctypes.c_ulong),
                                          ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int),
                                          ctypes.POINTER(ctypes.c_uint), ctypes.POINTER(ctypes.c_uint),
                                          ctypes.POINTER(ctypes.c_uint), ctypes.POINTER(ctypes.c_uint)]
        self.lib.XMoveWindow.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_int, ctypes.c_int]
        self.lib.XSync.argtypes = [ctypes.c_void_p, ctypes.c_int]
        self.lib.XFree.argtypes = [ctypes.c_void_p]
        self.lib.XCloseDisplay.argtypes = [ctypes.c_void_p]
        self.dpy = self.lib.XOpenDisplay(None)
        if not self.dpy:
            raise SystemExit("FAIL: cannot open the X display -- check is vacuous")
        self.root = self.lib.XDefaultRootWindow(self.dpy)

    def geometry(self, window):
        root, x, y = ctypes.c_ulong(), ctypes.c_int(), ctypes.c_int()
        w, h, border, depth = ctypes.c_uint(), ctypes.c_uint(), ctypes.c_uint(), ctypes.c_uint()
        self.lib.XGetGeometry(self.dpy, window, ctypes.byref(root), ctypes.byref(x), ctypes.byref(y),
                              ctypes.byref(w), ctypes.byref(h), ctypes.byref(border), ctypes.byref(depth))
        return x.value, y.value, w.value, h.value

    def largest_top_level(self):
        """With no window manager, the browser window is the root's largest child."""
        root, parent = ctypes.c_ulong(), ctypes.c_ulong()
        children, count = ctypes.POINTER(ctypes.c_ulong)(), ctypes.c_uint()
        self.lib.XQueryTree(self.dpy, self.root, ctypes.byref(root), ctypes.byref(parent),
                            ctypes.byref(children), ctypes.byref(count))
        windows = [children[i] for i in range(count.value)]
        if children:
            self.lib.XFree(children)
        if not windows:
            raise SystemExit("FAIL: no top-level window on the display -- check is vacuous")
        return max(windows, key=lambda win: self.geometry(win)[2] * self.geometry(win)[3])

    def move(self, window, x, y):
        self.lib.XMoveWindow(self.dpy, window, x, y)
        self.lib.XSync(self.dpy, 0)

    def close(self):
        self.lib.XCloseDisplay(self.dpy)


def move_real_window(x, y):
    """Move the browser's real window to x, y and return where X says it is."""
    display = _X()
    try:
        window = display.largest_top_level()
        display.move(window, x, y)
        time.sleep(1)
        return list(display.geometry(window)[:2])
    finally:
        display.close()


PAGE = """<body style="margin:0"><div style="width:400px;height:300px"></div><script>
const geometry = () => ({screenX, screenY, mozInnerScreenX, mozInnerScreenY,
                         outerWidth, outerHeight, innerWidth, innerHeight});
addEventListener('mousedown', e => {
  const made = new MouseEvent('mousedown', {screenX: 5, screenY: 7});
  document.body.dataset.result = JSON.stringify({geometry: geometry(),
    event: {screenX: e.screenX, screenY: e.screenY, clientX: e.clientX, clientY: e.clientY},
    constructed: [made.screenX, made.screenY]});
});
</script></body>"""


def probe() -> dict:
    from camoufox.sync_api import Camoufox

    with hidden_display(), Camoufox(**launch_kwargs(headless=False, os="windows",
                                                    config=SPOOFED,
                                                    i_know_what_im_doing=True)) as browser:
        page = browser.new_page()
        page.set_content(PAGE)
        time.sleep(POSITION_HOLD_S)
        real = move_real_window(*REAL)
        page.mouse.click(120, 80)
        page.wait_for_function("document.body.dataset.result")
        result = json.loads(page.get_attribute("body", "data-result"))
        result["real"] = real
        return result


def main() -> int:
    result = probe()
    g, e = result["geometry"], result["event"]
    print(json.dumps(result))
    failures = []
    if result["real"] != list(REAL):
        failures.append(f"the real window is at {result['real']} after moving it to {list(REAL)}, "
                        "so real and spoofed positions may agree and the check proves nothing")
    if (g["screenX"], g["screenY"]) != (SPOOFED["window.screenX"], SPOOFED["window.screenY"]):
        failures.append(f"screenX/Y are {g['screenX']},{g['screenY']}, not the spoofed "
                        f"position after the real window moved")
    for axis, outer, inner in (("X", "outerWidth", "innerWidth"), ("Y", "outerHeight", "innerHeight")):
        offset = g[f"mozInnerScreen{axis}"] - g[f"screen{axis}"]
        chrome = g[outer] - g[inner]
        if not 0 <= offset <= chrome:
            failures.append(f"mozInnerScreen{axis} - screen{axis} = {offset}, outside the "
                            f"window's {chrome}px of chrome")
        client = e[f"client{axis}"]
        if abs(e[f"screen{axis}"] - client - g[f"mozInnerScreen{axis}"]) > 1:
            failures.append(f"event screen{axis} - client{axis} = {e[f'screen{axis}'] - client}, "
                            f"but mozInnerScreen{axis} = {g[f'mozInnerScreen{axis}']}")
    if result["constructed"] != [5, 7]:
        failures.append(f"new MouseEvent({{screenX: 5, screenY: 7}}) reads {result['constructed']}")
    for failure in failures:
        print(f"FAIL: {failure}")
    if failures:
        return 1
    print("PASS: mozInnerScreenX/Y and event screen coordinates follow the spoofed window position")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
