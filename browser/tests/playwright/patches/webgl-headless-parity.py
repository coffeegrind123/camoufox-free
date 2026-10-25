"""
Verify that WebGL looks the same headless as it does headful.

Firefox decides whether WebGL exists from gfxInfo, and gfxInfo gets its answer
from the glxtest probe, which opens an X connection before it does anything
else. Headless has no X server, so the probe dies with "Unable to open a
connection to the X server", GfxInfo blocks most features by default, and the
X11_EGL feature is force-disabled because the probe never reported EGL. UseEGL
then stays false, GLContextProviderLinux::CreateHeadless() picks GLX, GLX wants
the display that is missing, and canvas.getContext('webgl') returns null.

None of Camoufox's WebGL spoofing applies to that. The spoof layer lives inside
ClientWebGLContext -- parameters, extensions, precision formats, context
attributes -- so it only ever rewrites a context that was created. With no
context there is nothing to rewrite, and a browser that claims a GPU in every
other signal while having no WebGL at all is a louder tell than any renderer
string would be.

patches/webgl-headless-egl.patch takes the EGL provider directly when headless
and stops a display-less probe from vetoing WebGL. EGL reaches Mesa's swrast
device, or EGL_PLATFORM_SURFACELESS_MESA where there is no render node, and
either gives a real GL ES context on llvmpipe with no X server and no hardware.

Needs Mesa's EGL and DRI drivers on Linux (libegl1, libegl-mesa0 and
libgl1-mesa-dri on Debian and Ubuntu; mesa-libEGL and mesa-dri-drivers on
Fedora). libxul dlopens libEGL.so.1 rather than linking it, so without them the
browser still starts and only WebGL fails. No GPU is involved: the rasterizer
is llvmpipe, on the CPU.

The native-headless launch removes DISPLAY and WAYLAND_DISPLAY from its child
environment. Xvfb is NOT required. Where Xvfb happens to be installed the test
also probes a virtual display and compares the two key for key; where it is
not, that half is skipped and says so.

Run against a specific build:
    python browser/tests/playwright/patches/webgl-headless-parity.py --binary /path/to/camoufox-bin
(or CAMOUFOX_EXECUTABLE_PATH, or the in-tree build; see helpers.resolve_binary.)

What PASS means:
    * headless hands the page a real context, for WebGL 1 and for WebGL 2 when
      the sampled GPU has it;
    * that context compiles, links and draws, and reads back the colour the
      shader wrote, so it renders rather than merely reporting well;
    * every value a fingerprinter can read -- vendor, renderer, both unmasked
      strings, limits, extension list, shader precision -- is the pinned GPU's
      rather than the host's;
    * every extension the spoofed list advertises actually resolves, so the list
      is not sitting on top of a driver that lacks those extensions;
    * and the shader translator reports the same target in both modes, which is
      the one place the EGL and GLX paths could visibly differ: it is read
      through WEBGL_debug_shaders, exposed to content by default;
    * and, where a virtual display is available, headful agrees key for key.

The framebuffer hash is reported only: Camoufox does not spoof rendered
pixels, so a host with a real GPU draws differently from llvmpipe. Context
attributes are compared headless against headful but not against the
fingerprint: fpgen records none, so the launcher sets none.
"""

import asyncio
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any, Dict

sys.path.insert(0, str(Path(__file__).resolve().parent))
from helpers import resolve_binary  # noqa: E402

from camoufox.async_api import AsyncCamoufox  # noqa: E402
from camoufox.webgl import recorded_devices, webgl_for_gpu  # noqa: E402

# Pinned rather than sampled at random, so a failure names one GPU and is
# reproducible. fpgen records exactly one Firefox-on-Linux device behind this
# GPU (checked in _run), so webgl_for_gpu() returns the config the launcher
# injects whatever seed either side draws with.
VENDOR = "NVIDIA Corporation"
RENDERER = "NVIDIA GeForce GTX 980, or similar"

# GL enums, as the sampled parameters key them.
GL = {
    "VENDOR": "7936",
    "RENDERER": "7937",
    "VERSION": "7938",
    "GLSL": "35724",
    "UNMASKED_VENDOR": "37445",
    "UNMASKED_RENDERER": "37446",
    "MAX_TEXTURE_SIZE": "3379",
    "MAX_RENDERBUFFER_SIZE": "34024",
    "MAX_VIEWPORT_DIMS": "3386",
    "ALIASED_LINE_WIDTH_RANGE": "33902",
}
# FRAGMENT_SHADER, HIGH_FLOAT.
FRAG_HIGH_FLOAT_KEY = "35632,36338"

# The shader writes vec4(0.2, 0.7, 0.4, 1.0); these are those floats as bytes.
EXPECTED_PIXEL = [51, 178, 102, 255]

# Reported side by side but never asserted; see the module docstring.
UNASSERTED = ("fbHash",)

PROBE = r"""
(function () {
  var A = function (v) {
    try { return Array.prototype.slice.call(v); } catch (e) { return String(v); }
  };
  var out = {};
  ['webgl', 'webgl2'].forEach(function (type) {
    var c = document.createElement('canvas');
    c.width = 256; c.height = 256;
    var reason = null;
    c.addEventListener('webglcontextcreationerror', function (e) {
      reason = e.statusMessage || '(empty)';
    });
    var gl = null;
    try { gl = c.getContext(type, {preserveDrawingBuffer: true}); }
    catch (e) { reason = 'threw: ' + e.message; }
    if (!gl) { out[type] = {context: null, creationError: reason}; return; }

    var dbg = gl.getExtension('WEBGL_debug_renderer_info');
    var r = {
      context: gl.constructor.name,
      VERSION: gl.getParameter(gl.VERSION),
      GLSL: gl.getParameter(gl.SHADING_LANGUAGE_VERSION),
      VENDOR: gl.getParameter(gl.VENDOR),
      RENDERER: gl.getParameter(gl.RENDERER),
      UNMASKED_VENDOR: dbg ? gl.getParameter(dbg.UNMASKED_VENDOR_WEBGL) : null,
      UNMASKED_RENDERER: dbg ? gl.getParameter(dbg.UNMASKED_RENDERER_WEBGL) : null,
      MAX_TEXTURE_SIZE: gl.getParameter(gl.MAX_TEXTURE_SIZE),
      MAX_RENDERBUFFER_SIZE: gl.getParameter(gl.MAX_RENDERBUFFER_SIZE),
      MAX_VIEWPORT_DIMS: A(gl.getParameter(gl.MAX_VIEWPORT_DIMS)),
      ALIASED_LINE_WIDTH_RANGE: A(gl.getParameter(gl.ALIASED_LINE_WIDTH_RANGE)),
      extensions: (gl.getSupportedExtensions() || []).slice().sort(),
      attrs: gl.getContextAttributes()
    };
    var p = gl.getShaderPrecisionFormat(gl.FRAGMENT_SHADER, gl.HIGH_FLOAT);
    r.FRAG_HIGH_FLOAT = p ? [p.rangeMin, p.rangeMax, p.precision] : null;

    // Every extension the browser advertises must actually resolve. A name in
    // getSupportedExtensions() that getExtension() returns null for is a spoofed
    // list sitting on top of a driver that does not have it, which is one
    // getExtension call to catch.
    var listed = gl.getSupportedExtensions() || [];
    r.unresolvable = listed.filter(function (n) { return gl.getExtension(n) === null; });

    // Draw, then read it back: a context that reports well but renders nothing
    // is worse than no context at all.
    var vs = gl.createShader(gl.VERTEX_SHADER);
    gl.shaderSource(vs, 'attribute vec2 p; void main(){ gl_Position = vec4(p,0.0,1.0); }');
    gl.compileShader(vs);
    var fs = gl.createShader(gl.FRAGMENT_SHADER);
    gl.shaderSource(fs, 'precision mediump float; void main(){ gl_FragColor = vec4(0.2,0.7,0.4,1.0); }');
    gl.compileShader(fs);
    r.vsOk = gl.getShaderParameter(vs, gl.COMPILE_STATUS);
    r.fsOk = gl.getShaderParameter(fs, gl.COMPILE_STATUS);
    var pr = gl.createProgram();
    gl.attachShader(pr, vs); gl.attachShader(pr, fs); gl.linkProgram(pr);
    r.linkOk = gl.getProgramParameter(pr, gl.LINK_STATUS);
    gl.useProgram(pr);
    var buf = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, buf);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-0.8,-0.8, 0.8,-0.8, 0.0,0.8]), gl.STATIC_DRAW);
    var loc = gl.getAttribLocation(pr, 'p');
    gl.enableVertexAttribArray(loc);
    gl.vertexAttribPointer(loc, 2, gl.FLOAT, false, 0, 0);
    gl.clearColor(0, 0, 0, 1);
    gl.clear(gl.COLOR_BUFFER_BIT);
    gl.drawArrays(gl.TRIANGLES, 0, 3);
    var px = new Uint8Array(4);
    gl.readPixels(128, 100, 1, 1, gl.RGBA, gl.UNSIGNED_BYTE, px);
    r.centerPixel = A(px);
    r.glError = gl.getError();

    // The shader translator names its own target. A desktop GL backend emits
    // "#version 450"; an ES backend emits an ESSL header. Headless takes the EGL
    // path and headful takes GLX, so this is where the two could diverge in a
    // way a page can read, through an extension that is exposed by default.
    var ds = gl.getExtension('WEBGL_debug_shaders');
    r.debug_shaders = !!ds;
    r.glslTarget = ds
      ? (ds.getTranslatedShaderSource(vs) || '').split('\n')[0]
      : null;

    var all = new Uint8Array(256 * 256 * 4);
    gl.readPixels(0, 0, 256, 256, gl.RGBA, gl.UNSIGNED_BYTE, all);
    var h = 2166136261;
    for (var i = 0; i < all.length; i++) { h ^= all[i]; h = Math.imul(h, 16777619); }
    r.fbHash = (h >>> 0).toString(16);

    out[type] = r;
  });
  document.documentElement.setAttribute('data-webgl', JSON.stringify(out));
})();
"""


def _launch_kwargs(headless: Any) -> Dict[str, Any]:
    # The native-headless probe must fail if it accidentally reaches X11. The
    # virtual-display probe deliberately lets the launcher add DISPLAY back.
    env = {
        name: value
        for name, value in os.environ.items()
        if name not in ("DISPLAY", "WAYLAND_DISPLAY")
    }
    # canvas_noise=False: the pinned GPU is not the host's, which turns on random
    # readback, and this guard reads back pixels to check that WebGL renders.
    return dict(headless=headless, os="linux", webgl_config=(VENDOR, RENDERER),
                canvas_noise=False, env=env, executable_path=str(resolve_binary()))


def _check(results: Dict[str, Any], label: str, got: Any, expected: Any) -> None:
    ok = got == expected
    results[label] = ok
    verdict = "PASS" if ok else "FAIL"
    suffix = "" if ok else f" (expected {expected!r})"
    print(f"  {verdict} {label:52} -> {got!r}{suffix}")


async def _probe(headless: Any) -> Dict[str, Any]:
    async with AsyncCamoufox(**_launch_kwargs(headless)) as browser:
        page = await browser.new_page()
        await page.goto("data:text/html,<html><body>probe</body></html>")
        await page.evaluate(
            "(src) => { const s = document.createElement('script');"
            " s.textContent = src; document.body.appendChild(s); }",
            PROBE,
        )
        raw = await page.get_attribute("html", "data-webgl")
    if not raw:
        raise RuntimeError("probe wrote nothing")
    return json.loads(raw)


def _assert_identity(results: Dict[str, Any], kind: str, got: Dict[str, Any],
                     fp: Dict[str, Any]) -> None:
    """What the page reads must be the pinned GPU, not the host's."""
    domain = "webGl2" if kind == "webgl2" else "webGl"
    params = fp[f"{domain}:parameters"]
    for name, enum in GL.items():
        if enum not in params:
            continue
        _check(results, f"{kind}.{name}", got[name], params[enum])
    _check(results, f"{kind}.extensions",
           got["extensions"], sorted(fp[f"{domain}:supportedExtensions"]))
    # A spoofed list is only convincing if every name in it resolves.
    _check(results, f"{kind}.every listed extension resolves", got["unresolvable"], [])
    spf = fp[f"{domain}:shaderPrecisionFormats"].get(FRAG_HIGH_FLOAT_KEY)
    if spf:
        _check(results, f"{kind}.FRAG_HIGH_FLOAT", got["FRAG_HIGH_FLOAT"],
               [spf["rangeMin"], spf["rangeMax"], spf["precision"]])


def _assert_renders(results: Dict[str, Any], mode: str, kind: str,
                    got: Dict[str, Any]) -> None:
    _check(results, f"{mode} {kind} compiles and links",
           [got["vsOk"], got["fsOk"], got["linkOk"]], [True, True, True])
    _check(results, f"{mode} {kind} draws the shader colour",
           got["centerPixel"], EXPECTED_PIXEL)


def _kinds(fp: Dict[str, Any]) -> Dict[str, bool]:
    """Which contexts the pinned GPU is supposed to offer."""
    return {"webgl": True, "webgl2": bool(fp["webGl2Enabled"])}


async def _run() -> bool:
    results: Dict[str, Any] = {}
    devices = len(recorded_devices("lin", VENDOR, RENDERER))
    if devices != 1:
        print(f"FAIL: fpgen records {devices} devices behind {RENDERER}; the guard needs exactly one")
        return False
    fp = webgl_for_gpu("lin", VENDOR, RENDERER)
    wanted = _kinds(fp)
    print(f"pinned GPU: {VENDOR} / {RENDERER}")
    print(f"webgl2 expected: {wanted['webgl2']}")
    print("native headless: DISPLAY and WAYLAND_DISPLAY unset")
    print()

    headless = await _probe(True)

    print("-- headless has a context at all --")
    for kind, should_exist in wanted.items():
        entry = headless.get(kind, {})
        _check(results, f"headless {kind} context",
               entry.get("context") is not None, should_exist)
        if entry.get("context") is None and should_exist:
            print(f"    creation error: {entry.get('creationError')}")
    print()

    if not all(results.values()):
        print("-- nothing further -- a context the page cannot get says nothing")
        return False

    print("-- headless renders, it does not just report --")
    for kind, should_exist in wanted.items():
        if should_exist:
            _assert_renders(results, "headless", kind, headless[kind])
    print()

    print("-- headless reports the pinned GPU, not the host --")
    for kind, should_exist in wanted.items():
        if should_exist:
            _assert_identity(results, kind, headless[kind], fp)
    print()

    if not shutil.which("Xvfb"):
        print("-- headful comparison -- skipped, no Xvfb on this host")
        print("   (the assertions above do not need one)")
        return all(results.values())

    virtual = await _probe("virtual")
    print("-- headful agrees key for key --")
    for kind, should_exist in wanted.items():
        if not should_exist:
            continue
        for key in sorted(headless[kind]):
            if key in UNASSERTED:
                continue
            _check(results, f"{kind}.{key} matches headful",
                   headless[kind][key], virtual[kind][key])
    print()
    print("-- reported, not asserted --")
    for kind, should_exist in wanted.items():
        if not should_exist:
            continue
        h, v = headless[kind]["fbHash"], virtual[kind]["fbHash"]
        note = "match" if h == v else "differ; the rendered image is not spoofed"
        print(f"  {kind} framebuffer hash: headless {h}, headful {v} ({note})")

    return all(results.values())


async def main() -> int:
    passed = await _run()
    print()
    if passed:
        print("PASS: headless WebGL is real, renders, and wears the pinned GPU")
        return 0
    print("FAIL: headless WebGL is missing or does not match the fingerprint")
    return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
