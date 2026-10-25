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

[`webgl-headless-egl.patch`](../browser/patches/webgl-headless-egl.patch)
changes the Linux offscreen factory to request Mesa's EGL provider when
`MOZ_HEADLESS` is set. EGL reaches either the swrast device or
`EGL_PLATFORM_SURFACELESS_MESA`, producing a real GL ES context on llvmpipe
without X11 or a GPU.

The GTK-only changes in `gfxPlatform::InitWebGLConfig()` stop the failed X11
probe from vetoing WebGL and the variables that gate native context creation.
They leave hardware acceleration off, as it should be in a headless process,
and do not run on macOS or Windows.

The patch deliberately does not flip `gfxVars::UseEGL()`. That flag also
controls DMABUF, hardware video decoding, the EGL render compositor and the
compositor's shared context. Those subsystems do not need to change for an
offscreen WebGL context.

`webgl-headless-egl.patch` has no source dependency on
[`webgl-spoofing.patch`](../browser/patches/webgl-spoofing.patch). The patches
touch disjoint files and apply in file-name order. Together they make the
headless context both real and consistent with the identity's recorded GPU;
either half missing is a detectable browser.

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
