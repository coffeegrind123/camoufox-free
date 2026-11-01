"""
Verify a context that claims another GPU reports that GPU's WebGL limits,
extensions and shader precisions, not the launch GPU's.

setWebGLVendor/setWebGLRenderer gave a context its own GPU name, but
getParameter's limits, getSupportedExtensions() and getShaderPrecisionFormat()
kept answering from the launch's CAMOU_CONFIG tables. A page read one GPU's
name beside another GPU's limits: a pairing no real device reports.
setWebGLConfig (webgl-spoofing.patch) hands a context its GPU's tables.

The browser launches as one recorded Linux GPU. A context then claims another
whose tables differ, through the setters an init script calls, and opens pages
on two sites (two content processes). Each page reads WebGL on its main thread,
in a data document and on an OffscreenCanvas in a dedicated worker.

What PASS means: every reading in the context reports the context GPU's name,
limits, extensions and precision; a page of the default context reports the
launch GPU's, so the two differ and the check is not vacuous.

    python browser/tests/playwright/patches/context-webgl-tables.py
"""

import asyncio
import json
import sys
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from helpers import resolve_binary  # noqa: E402

HOSTS = ["127.0.0.1", "127.0.0.2"]

# The WebGL1 limits webgl-spoofing.patch answers from the identity's tables.
LIMITS = [3379, 3386, 3408, 33901, 33902, 34024, 34076, 34921, 34930, 35660, 35661, 36347, 36348, 36349]
VERTEX_HIGH_FLOAT = "35633,36338"

# Run in the page's main world (mw:): page.evaluate's isolated world reads a
# typed array (MAX_VIEWPORT_DIMS, the *_RANGE limits) through an Xray, which
# refuses to copy it.
PROBE = f"""mw:(async () => {{
  const read = (gl) => {{
    if (!gl) return null;
    const info = gl.getExtension('WEBGL_debug_renderer_info');
    const limits = {{}};
    for (const p of {LIMITS}) {{
      const v = gl.getParameter(p);
      limits[p] = v && typeof v === 'object' ? Array.from(v) : v;
    }}
    const f = gl.getShaderPrecisionFormat(gl.VERTEX_SHADER, gl.HIGH_FLOAT);
    return {{
      vendor: info && gl.getParameter(info.UNMASKED_VENDOR_WEBGL),
      renderer: info && gl.getParameter(info.UNMASKED_RENDERER_WEBGL),
      limits, extensions: gl.getSupportedExtensions(),
      precision: f && [f.rangeMin, f.rangeMax, f.precision],
    }};
  }};
  const out = {{page: read(document.createElement('canvas').getContext('webgl'))}};
  const dataDoc = document.implementation.createHTMLDocument('');
  out.dataDocument = read(dataDoc.createElement('canvas').getContext('webgl'));
  const src = 'const read = ' + read.toString() +
    '; postMessage(read(new OffscreenCanvas(8, 8).getContext("webgl")))';
  const worker = new Worker(URL.createObjectURL(new Blob([src])));
  out.worker = await new Promise(r => {{
    worker.onmessage = e => r(e.data); worker.onerror = e => r(String(e.message));
  }});
  return JSON.stringify(out);
}})()"""


class Quiet(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def tables_of(device):
    """The config keys setWebGLConfig takes: every table, without the names."""
    return {k: v for k, v in device.items() if k not in ("webGl:vendor", "webGl:renderer", "webGl2Enabled")}


def expected(device):
    params = device["webGl:parameters"]
    precision = device["webGl:shaderPrecisionFormats"][VERTEX_HIGH_FLOAT]
    return {
        "vendor": device["webGl:vendor"],
        "renderer": device["webGl:renderer"],
        "limits": {str(p): params[str(p)] for p in LIMITS if params.get(str(p)) is not None},
        "extensions": device["webGl:supportedExtensions"],
        "precision": [precision["rangeMin"], precision["rangeMax"], precision["precision"]],
    }


def mismatches(label, out, want):
    failures = []
    for scope, got in out.items():
        where = f"{label} {scope}"
        if not isinstance(got, dict):
            failures.append(f"{where}: no WebGL context ({got!r})")
            continue
        for key in ("vendor", "renderer", "extensions", "precision"):
            if got[key] != want[key]:
                failures.append(f"{where}: {key} {got[key]!r}, expected {want[key]!r}")
        for pname, value in want["limits"].items():
            if got["limits"].get(pname) != value:
                failures.append(f"{where}: parameter {pname} {got['limits'].get(pname)!r}, expected {value!r}")
    return failures


def pick_gpus():
    """A launch GPU and a context GPU whose tables differ in the extension
    list and in at least one limit, so each half of the check can fail."""
    from camoufox.coherence import gpu_fits_os
    from camoufox.fingerprints import is_software_renderer
    from camoufox.webgl import firefox_gpus, webgl_for_gpu

    gpus = sorted(gpu for gpu in firefox_gpus("lin")
                  if not is_software_renderer(gpu[1]) and gpu_fits_os(gpu[1], "lin"))
    launch_want = expected(webgl_for_gpu("lin", *gpus[0], seed=0))
    for gpu in gpus[1:]:
        device = webgl_for_gpu("lin", *gpu, seed=0)
        want = expected(device)
        if want["extensions"] != launch_want["extensions"] and want["limits"] != launch_want["limits"]:
            return gpus[0], device
    raise SystemExit("FAIL: no two recorded Linux GPUs differ in both extensions and limits -- check is vacuous")


async def run(binary, launch_gpu, device, port):
    import orjson
    from playwright.async_api import async_playwright

    from camoufox.async_api import AsyncNewBrowser
    from camoufox.utils import _camou_config_blob, launch_options
    from camoufox.virtdisplay import VirtualDisplay

    # A real WebGL context needs a display.
    display = VirtualDisplay()
    opts = launch_options(os="linux", webgl_config=launch_gpu, headless=False,
                          virtual_display=display.get(), executable_path=str(binary),
                          main_world_eval=True, i_know_what_im_doing=True)
    # The tables the launch drew for its GPU, as the browser reads them.
    launch = orjson.loads(_camou_config_blob(opts))
    failures = []
    try:
        async with async_playwright() as pw:
            browser = await AsyncNewBrowser(pw, from_options=opts)
            try:
                page = await browser.new_page()
                await page.goto(f"http://{HOSTS[0]}:{port}/")
                failures += mismatches("launch", json.loads(await page.evaluate(PROBE)), expected(launch))

                context = await browser.new_context()
                tables = json.dumps(tables_of(device), sort_keys=True)
                await context.add_init_script(
                    f"setWebGLVendor({json.dumps(device['webGl:vendor'])});"
                    f"setWebGLRenderer({json.dumps(device['webGl:renderer'])});"
                    f"setWebGLConfig({json.dumps(tables)});"
                )
                for host in HOSTS:
                    context_page = await context.new_page()
                    await context_page.goto(f"http://{host}:{port}/")
                    failures += mismatches(host, json.loads(await context_page.evaluate(PROBE)),
                                           expected(device))
            finally:
                await browser.close()
    finally:
        display.kill()
    if expected(launch)["extensions"] == expected(device)["extensions"]:
        failures.append("the launch and context GPUs list the same extensions -- check is vacuous")
    return failures


def main() -> int:
    launch_gpu, device = pick_gpus()
    server = ThreadingHTTPServer(("0.0.0.0", 0), partial(Quiet, directory=str(Path(__file__).resolve().parent / "assets")))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        failures = asyncio.run(run(resolve_binary(), launch_gpu, device, server.server_address[1]))
    finally:
        server.shutdown()
    print(f"  launch GPU:  {launch_gpu[1]}")
    print(f"  context GPU: {device['webGl:renderer']}")
    for failure in failures:
        print(f"FAIL: {failure}")
    if failures:
        return 1
    print(f"PASS: a context's pages on {len(HOSTS)} sites, its data documents and workers report its own "
          "GPU's limits, extensions and precision; the launch's page reports the launch GPU's")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
