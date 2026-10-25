"""
Verify a context's font and voice lists hold in every content process.

NewContext() hands each context its own font list and speech voices through
window setters (setFontList, setSpeechVoices). The first document to call a
setter marks it used for the whole context, in storage every process shares,
so later documents in the context never call it again. The lists themselves
were kept in a per-process static map, so a document of the same context that
landed in another content process found no list and showed the launch-level
fonts and voices instead. An OffscreenCanvas in a worker has no document, so
its text was measured with the launch-level fonts, and once a worker had
measured, so was the text on its page's main thread.

The probe gives one context the full Windows list except one visible font
through an init script, then opens it on several loopback addresses. The list
is over 4 KiB, the size above which Firefox does not sync a string pref to a
content process. Each address is its own site; the parent's ProcessIsolation
log must show two of them isolated apart, so the guard cannot pass by using one
content process. Each page reports which launch-level fonts and voices it can
see, measuring fonts on an OffscreenCanvas in a worker first and then on one on
its main thread.

What PASS means: every page of the context, and a worker on each, sees the
same fonts and voices as the first, and fewer than the launch level does.

    python browser/tests/playwright/patches/context-lists-across-processes.py
"""

import asyncio
import json
import os
import re
import shutil
import sys
import tempfile
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from helpers import resolve_binary  # noqa: E402

CAMOUFOX = Path(__file__).resolve().parents[4] / "python" / "src" / "camoufox"

HOSTS = [f"127.0.0.{n}" for n in range(1, 9)]

PROBE = """async ({fonts, probe}) => {
  // document.fonts.check() is true for any font that needs no download,
  // installed or not, so measure: a font is there if it changes the width of
  // the text against both fallbacks.
  const visible = fonts => {
    const ctx = new OffscreenCanvas(1, 1).getContext('2d');
    const width = font => { ctx.font = font; return ctx.measureText('mmmmmmmmmmlli10OQ@#').width; };
    const base = ['monospace', 'serif'].map(g => [g, width(`72px ${g}`)]);
    return fonts.filter(f => base.some(([g, w]) => width(`72px "${f}", ${g}`) !== w));
  };
  const code = 'onmessage = e => postMessage((' + visible.toString() + ')(e.data))';
  const w = new Worker(URL.createObjectURL(new Blob([code])));
  w.postMessage(fonts);
  // The worker measures first: its lookups are what leaked into the main thread's.
  const workerFonts = await new Promise(r => { w.onmessage = e => r(e.data); });
  let voices = speechSynthesis.getVoices();
  if (!voices.length)
    voices = await new Promise(r => {
      speechSynthesis.onvoiceschanged = () => r(speechSynthesis.getVoices());
      setTimeout(() => r(speechSynthesis.getVoices()), 2000);
    });
  return {fonts: visible(fonts), probeVisible: visible([probe]).length === 1,
          workerFonts, voices: voices.map(v => v.name).sort()};
}"""


class Quiet(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def context_origins(logdir: Path, port: int):
    """Context id -> origin -> isolation behaviours from the parent log."""
    parent = "".join(p.read_text(errors="replace") for p in logdir.glob("cfx-main*"))
    by_context = {}
    pattern = re.compile(
        rf"Using IsolationBehavior (\w+) for http://([^:/\s]+):{port}(\S*)")
    for match in pattern.finditer(parent):
        behavior, host, suffix = match.groups()
        if "font-fallback.html?context" not in suffix:
            continue
        line_start = parent.rfind("\n", 0, match.start()) + 1
        line_end = parent.find("\n", match.end())
        line = parent[line_start:len(parent) if line_end < 0 else line_end]
        context = re.search(r"userContextId=(\d+)", line)
        if not context:
            continue
        origins = by_context.setdefault(context.group(1), {})
        origins.setdefault(host, set()).add(behavior)
    return by_context


async def main() -> int:
    from camoufox.async_api import AsyncCamoufox

    candidates = sorted(set(json.loads((CAMOUFOX / "fonts.json").read_text())["win"]))
    root = Path(__file__).resolve().parent / "assets"
    server = ThreadingHTTPServer(("0.0.0.0", 0), partial(Quiet, directory=str(root)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    port = server.server_address[1]
    work = Path(__file__).resolve().parents[4] / ".ci-work"
    work.mkdir(exist_ok=True)
    logdir = Path(tempfile.mkdtemp(prefix="cross-process-log-", dir=work))
    old_log = os.environ.get("MOZ_LOG")
    old_log_file = os.environ.get("MOZ_LOG_FILE")
    os.environ["MOZ_LOG"] = "ProcessIsolation:4,sync,append"
    os.environ["MOZ_LOG_FILE"] = str(logdir / "cfx%PID")
    origins = {}

    try:
        # The launch level allows every candidate; the context narrows both lists.
        async with AsyncCamoufox(headless=True, os="windows", config={"fonts": candidates},
                                 i_know_what_im_doing=True,
                                 executable_path=str(resolve_binary())) as browser:
            launch_page = await browser.new_page()
            await launch_page.goto(f"http://{HOSTS[0]}:{port}/font-fallback.html?launch")
            launch = await launch_page.evaluate(
                PROBE, {"fonts": candidates, "probe": candidates[0]})
            probe = next((font for font in launch["fonts"]
                          if font not in {"Courier New", "Times New Roman"}), None)
            if probe is None:
                print("  FAIL: the launch level exposed no font that the context can omit")
                return 1
            # Keep every launch-level family but one. The joined value is over
            # Firefox's 4 KiB pref limit, so only chunked storage carries it.
            fonts = [font for font in candidates if font != probe]
            voices = launch["voices"][:1]

            context = await browser.new_context()
            await context.add_init_script(
                f"if (typeof setFontList === 'function') setFontList({json.dumps(','.join(fonts))});"
                f"if (typeof setSpeechVoices === 'function') setSpeechVoices({json.dumps(','.join(voices))});"
            )
            seen = {}
            for host in HOSTS:
                page = await context.new_page()
                await page.goto(
                    f"http://{host}:{port}/font-fallback.html?context=1")
                seen[host] = await page.evaluate(
                    PROBE, {"fonts": candidates, "probe": probe})
        origins = context_origins(logdir, port)
    finally:
        if old_log is None:
            os.environ.pop("MOZ_LOG", None)
        else:
            os.environ["MOZ_LOG"] = old_log
        if old_log_file is None:
            os.environ.pop("MOZ_LOG_FILE", None)
        else:
            os.environ["MOZ_LOG_FILE"] = old_log_file
        shutil.rmtree(logdir, ignore_errors=True)
    server.shutdown()

    size = len(",".join(fonts).encode())
    print(f"  context list: {len(fonts)} names, {size} bytes joined; omitted {probe!r}")
    if size <= 4096:
        print("  FAIL: the context list is not over 4 KiB, so this run cannot see a "
              "value Firefox refuses to sync")
        return 1
    isolated = max(origins.values(), key=len, default={})
    print(f"  isolation for the context: "
          f"{ {host: sorted(behaviours) for host, behaviours in isolated.items()} }")
    if len(isolated) < 2:
        print("  FAIL: the parent log does not show the context on two isolated origins")
        return 1
    if any(behaviours & {"Parent", "Anywhere"} for behaviours in isolated.values()):
        print("  FAIL: a context origin was not isolated from the others")
        return 1
    if len(launch["voices"]) < 2:
        print(f"  FAIL: the launch level has {len(launch['voices'])} voices; narrowing needs two")
        return 1
    # The first page is the reference: it is where the lists were set, and a
    # listed font's aliases (Helvetica for Arial) show there as on Windows.
    passed = True
    first = seen[HOSTS[0]]
    if first["probeVisible"] or probe in first["fonts"]:
        passed = False
        print(f"  FAIL fonts: the context still exposes the omitted font {probe!r}")
    for kind in ("fonts", "voices"):
        if len(first[kind]) >= len(launch[kind]):
            passed = False
            print(f"  FAIL {kind}: the context list did not apply on {HOSTS[0]} "
                  f"({len(first[kind])} of the launch-level {len(launch[kind])})")
        for host in HOSTS[1:]:
            if seen[host][kind] != first[kind]:
                passed = False
                extra = sorted(set(seen[host][kind]) - set(first[kind]))
                print(f"  FAIL {kind} on {host}: {len(seen[host][kind])} visible, "
                      f"{len(first[kind])} on {HOSTS[0]}; extra: {extra[:5]}")
    for host in HOSTS:
        if seen[host]["workerFonts"] != seen[host]["fonts"]:
            passed = False
            extra = sorted(set(seen[host]["workerFonts"]) - set(seen[host]["fonts"]))
            print(f"  FAIL fonts in a worker on {host}: {len(seen[host]['workerFonts'])} visible, "
                  f"{len(seen[host]['fonts'])} on its main thread; extra: {extra[:5]}")
    if passed:
        print(f"  PASS: {len(HOSTS)} sites, and a worker on each, all see the context's "
              f"{len(first['fonts'])} fonts and {len(first['voices'])} voice, of {len(launch['fonts'])} and "
              f"{len(launch['voices'])}")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
