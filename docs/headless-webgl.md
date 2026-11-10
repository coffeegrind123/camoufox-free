# Native headless WebGL

Firefox's native headless mode (`headless=True`) previously returned `null`
from both `canvas.getContext("webgl")` and `canvas.getContext("webgl2")` when
`DISPLAY` was unset. The browser still advertised a GPU through the spoofed
navigator and WebGL identity, but no page could obtain a context for that
identity to describe.

The cause is in Firefox's graphics initialization, not in the fingerprint
layer. `gfxInfo` asks the GLX test probe for a driver, and that probe opens an
X connection first. Without a display the probe fails, `gfxInfo` disables
WebGL, `UseEGL` remains false, and `GLContextProviderLinux::CreateHeadless()`
falls back to GLX, which needs the display that is absent.

## Implementation

[`headless-software-webgl.patch`](../browser/patches/headless-software-webgl.patch)
(upstream's, from Firefox 159's stock-parity work) gives the GPU probe a
headless mode: a headless launch with neither `DISPLAY` nor `WAYLAND_DISPLAY`
runs `gfxtest glx -e`, which probes Mesa's software GL through
`EGL_PLATFORM_SURFACELESS_MESA` and needs no display. `GfxInfo` then keeps that
launch's WebGL on Mesa's software EGL device (llvmpipe) rather than the first
device EGL enumerates. A headless launch that does have a display probes it,
as stock does.

The same probe result also restores what an empty `gfxInfo` took away beyond
WebGL: WebRTC's H264 video codecs.

The fork carried its own `webgl-headless-egl.patch` for this until
2026-11-10. It forced the EGL provider on every headless launch, a display or
not. Built with upstream's patch alone, headless WebGL equalled a headed launch
on Xvfb key for key, framebuffer hash included, with and without a display;
built with the fork's alone, WebRTC lost H264 headless. The fork's patch was
redundant and was dropped.

`headless-software-webgl.patch` has no source dependency on
[`webgl-spoofing.patch`](../browser/patches/webgl-spoofing.patch). Together they
make the headless context both real and consistent with the identity's
recorded GPU; either half missing is a detectable browser.

## Runtime dependencies

`libxul` loads `libEGL.so.1` dynamically. Without Mesa's EGL and DRI packages
the browser starts, but native-headless WebGL still returns `null`.

```sh
# Debian, Ubuntu
apt-get install -y libegl1 libegl-mesa0 libgl1-mesa-dri

# Fedora, RHEL, Amazon Linux
dnf install -y mesa-libEGL mesa-dri-drivers
```

Xvfb is not a dependency of native headless mode.

## Guard

[`webgl-headless-parity.py`](../browser/tests/playwright/patches/webgl-headless-parity.py)
is registered in the `parity` patch-guard group. Its native-headless launch
removes both `DISPLAY` and `WAYLAND_DISPLAY`, pins one recorded GPU, and checks
that:

- WebGL 1 exists and WebGL 2 exists whenever the recorded GPU supports it;
- vertex and fragment shaders compile, the program links, and a triangle draws
  the expected pixel colour on readback;
- the vendor, renderer, unmasked strings, limits, extensions and shader
  precision match the pinned identity;
- every extension in the spoofed list actually resolves; and
- when Xvfb is installed, the virtual-display comparison agrees on every
  asserted value, including context attributes. Context attributes are not
  compared with the fingerprint because fpgen does not record them.

Run it without a display:

```sh
env -u DISPLAY -u WAYLAND_DISPLAY \
  python3 -m ci.run_patch_guards --binary /path/to/camoufox-bin \
  --only webgl-headless-parity
```

The guard itself removes those variables from the browser's environment, so
`xvfb-run` around the patch-guard job cannot hide an accidental X11 dependency.

The framebuffer hash is reported but not asserted. Camoufox spoofs the WebGL
identity, not the rasterizer's pixels; a host GPU and llvmpipe can legitimately
draw the same scene differently.
