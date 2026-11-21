"""
Driven presses count clicks as the claimed OS does.

The OS, not the page, decides a press's click count (`detail`): a press in
place soon after the last one counts up. People's recordings on stock 159.0
(private, a mouse and a touchpad on each OS) follow these rules, checked
against every recorded press:
- Windows: Firefox counts a press within 500 ms of the last one, unless the
  pointer moved 4 device pixels from the last release; Windows itself reports
  a press within 1 device pixel of the last single press as a double click,
  which sets the count to 2. Fifteen quick presses in place count
  1, 2, 3, 2, 3, ...
- macOS: a press within 500 ms and 3 points of the last one counts up, without
  bound.
- GTK counts 1, 2, 3 and starts again, within its default 400 ms and 5 pixels.
A driven press always reported the clickCount the client sent: 1 for every
page.click(), however quick and wherever.

The guard presses in place under each identity, then presses after a pause
and after a move, and checks every count.

    python browser/tests/playwright/patches/driven-click-count.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from helpers import hidden_display, resolve_binary  # noqa: E402

PAGE = """<!doctype html><html><body style="margin:0;width:800px;height:600px"><script>
  const seen = [];
  for (const type of ['mousedown', 'mouseup', 'click'])
    addEventListener(type, (e) => {
      seen.push([type, e.detail, e.timeStamp]);
      document.body.dataset.seen = JSON.stringify(seen);
    }, true);
</script></body></html>"""
PRESSES = 8
# With every press inside the OS's window, the in-place presses count:
#   windows 1, 2, 3, 2, 3, 2, 3, 2   macos 1, 2, ..., 8   linux 1, 2, 3, 1, 2, 3, 1, 2
# A press is soon when it comes within the window of the one before. The guard
# applies each OS's rule to the gaps the page saw, not to the 60 ms it waits:
# on a busy runner a gap passed GTK's 400 ms and the count rightly started again
# (daijro/camoufox run 44575692624: linux 1, 2, 3, 1, 2, 1, 2, 3).
CLICK_MS = {"windows": 500, "macos": 500, "linux": 400}
# Within this of the window, either answer passes: the page's stamps (on the
# Windows tick) are not the times the browser counted from.
EDGE_MS = 25


def next_counts(os_name, count, soon):
    """The counts the OS may give a press in place after one counted `count`;
    `soon` is True, False, or None when the gap is too near the window to say."""
    def one(is_soon):
        if not is_soon:
            return 1
        if os_name == "windows":
            # Windows' own double click for a press by the last single press
            # (counted 1 or 3); Firefox counts up any other.
            return 2 if count in (1, 3) else count + 1
        if os_name == "macos":
            return count + 1
        return count + 1 if count < 3 else 1
    return {one(True), one(False)} if soon is None else {one(soon)}


def in_place_failures(os_name, presses):
    """Presses [(count, timeStamp)] in place that the OS would not count so."""
    bad = []
    for i, (count, t) in enumerate(presses):
        if i == 0:
            allowed = {1}
        else:
            gap = t - presses[i - 1][1]
            window = CLICK_MS[os_name]
            soon = None if abs(gap - window) <= EDGE_MS else gap < window
            allowed = next_counts(os_name, presses[i - 1][0], soon)
        if count not in allowed:
            if i:
                bad.append(f"press {i + 1} counted {count} {round(t - presses[i - 1][1])} ms after the last, "
                           f"the OS {sorted(allowed)}")
            else:
                bad.append(f"press 1 counted {count}, the OS 1")
    return bad


def probe(binary, os_name):
    from camoufox.sync_api import Camoufox

    with Camoufox(executable_path=str(binary), headless=False, os=os_name, i_know_what_im_doing=True) as browser:
        page = browser.new_page()
        page.set_content(PAGE)
        page.mouse.move(200, 200)
        for _ in range(PRESSES):
            page.mouse.click(200, 200)
            page.wait_for_timeout(60)
        page.wait_for_timeout(700)
        page.mouse.click(200, 200)
        page.mouse.move(260, 200)
        page.mouse.click(260, 200)
        page.wait_for_timeout(100)
        return page.evaluate("() => JSON.parse(document.body.dataset.seen || '[]')")


def main() -> int:
    failures = []
    with hidden_display("1920x1080"):
        seen = {os_name: probe(resolve_binary(), os_name) for os_name in CLICK_MS}
    for os_name in CLICK_MS:
        presses = [(d, ts) for t, d, ts in seen[os_name] if t == "mousedown"]
        downs = [d for d, _ in presses]
        if len(downs) != PRESSES + 2:
            failures.append(f"{os_name}: {len(downs)} presses reached the page, {PRESSES + 2} were sent")
            continue
        for bad in in_place_failures(os_name, presses[:PRESSES]):
            failures.append(f"{os_name}: {bad} (counts {downs})")
        # After a 700 ms pause, and after a move away, a press starts again.
        if downs[PRESSES:] != [1, 1]:
            failures.append(f"{os_name}: presses after a pause and after a move counted {downs[PRESSES:]}, the OS [1, 1]")
        for kind in ("mouseup", "click"):
            got = [d for t, d, _ in seen[os_name] if t == kind]
            if got != downs:
                failures.append(f"{os_name}: {kind} detail {got}, its press counted {downs}")
    for failure in failures:
        print(f"FAIL: {failure}")
    if failures:
        return 1
    print("PASS: driven presses count clicks as each OS does")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
