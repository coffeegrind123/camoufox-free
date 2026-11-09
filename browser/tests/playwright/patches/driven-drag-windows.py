"""
A driver's drag under a Windows identity reaches the page as an OLE drag does.

Juggler's drag session is synthesized, so how a drag reaches the page is
emulated, and it emulated GTK's for every identity: the first motion took the
pointer from the window (pointerout, mouseout and four leaves each, related
target null), and drag/dragover fired only on motion. Stock Firefox 159 on
Windows 11 (a real drag, SendInput) shows no window exit: hover stays on the
source until the drop (the pointercancel at dragstart still sends its
pointerout). And OLE calls DragOver on a timer while the button is
held, so drag and dragover keep coming every 59-77 ms with the pointer still.
The emulation now follows the claimed OS (PageHandler._dragPlatform).

Checked on a private Xvfb display, headed, Windows identity: press on a
draggable element, move onto a drop target, hold still 500 ms, release.

    python browser/tests/playwright/patches/driven-drag-windows.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from helpers import hidden_display, launch_kwargs  # noqa: E402

PAGE = """<!doctype html><body style="margin:0">
<div id="src" draggable="true" style="position:absolute;left:40px;top:180px;width:80px;height:40px;background:#cde"></div>
<div id="dst" style="position:absolute;left:260px;top:180px;width:160px;height:120px;background:#edc"></div>
</body>"""

# Installed through evaluate(), which runs in an isolated world: its listeners
# get the page's DOM events.
RECORD = """() => {
  window.__ev = [];
  const who = (t) => t ? (t.id || t.nodeName.toLowerCase()) : null;
  const dst = document.getElementById('dst');
  dst.addEventListener('dragover', (e) => e.preventDefault());
  dst.addEventListener('drop', (e) => e.preventDefault());
  for (const t of ['dragstart', 'drag', 'dragover', 'drop', 'dragend', 'pointerout', 'mouseout', 'mouseleave'])
    addEventListener(t, (e) => __ev.push([t, who(e.target), who(e.relatedTarget), performance.now()]), true);
}"""

HOLD_MS = 500


def main() -> int:
    from camoufox.sync_api import Camoufox

    with hidden_display(), Camoufox(**launch_kwargs(headless=False, os="windows",
                                                    i_know_what_im_doing=True)) as browser:
        page = browser.new_page()
        page.set_content(PAGE)
        page.evaluate(RECORD)
        page.mouse.move(80, 200)
        page.wait_for_timeout(200)
        page.mouse.down()
        page.mouse.move(90, 205)
        page.mouse.move(200, 220, steps=4)
        page.mouse.move(320, 230, steps=4)
        page.wait_for_timeout(100)
        held_from = page.evaluate("performance.now()")
        page.wait_for_timeout(HOLD_MS)
        held_to = page.evaluate("performance.now()")
        page.mouse.up()
        page.wait_for_timeout(300)
        events = page.evaluate("__ev")

    names = [e[0] for e in events]
    failures = []
    if "dragstart" not in names or "drop" not in names:
        failures.append(f"no complete drag: {names}")
    else:
        start, drop = names.index("dragstart"), names.index("drop")
        # A pointerout at dragstart is the pointercancel's, which stock Windows
        # sends too; only GTK's window exit adds mouseout and mouseleave.
        exits = [e for e in events[start:drop] if e[0] in ("mouseout", "mouseleave") and e[2] is None]
        if exits:
            failures.append(f"the drag took the pointer from the window, as GTK does: {exits[:4]}")
        ticks = [e for e in events if e[0] == "drag" and held_from <= e[3] <= held_to]
        if len(ticks) < 4:
            failures.append(f"{len(ticks)} drag events in {HOLD_MS} ms held still; OLE fires one every 59-77 ms")

    for f in failures:
        print(f"FAIL: {f}")
    if failures:
        return 1
    print(f"PASS: a Windows identity's drag has no window exit and keeps firing while held "
          f"({sum(1 for n in names if n == 'drag')} drag, {sum(1 for n in names if n == 'dragover')} dragover)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
