# camoufox-free

A fork of [Camoufox](https://github.com/daijro/camoufox), the Firefox build
that spoofs device fingerprints in C++. For what Camoufox is, its features and
how to build it, read [upstream's README](https://github.com/daijro/camoufox#readme).

This fork follows upstream `main` and pins Firefox `158.0` / Camoufox `beta.33`
in [`browser/upstream.sh`](browser/upstream.sh). The newest published build is
[`v158.0-beta.33-cg.9`](https://github.com/coffeegrind123/camoufox-free/releases/tag/v158.0-beta.33-cg.9),
built from [f597fa6](https://github.com/coffeegrind123/camoufox-free/commit/f597fa67fe29030b38c10dab193679adf84c073d);
it predates
[PR #2](https://github.com/coffeegrind123/camoufox-free/pull/2), where the
current feature set was merged. The newest stable release remains
[`v152.0.4-beta.31-cg.4`](https://github.com/coffeegrind123/camoufox-free/releases/tag/v152.0.4-beta.31-cg.4).
Features below that landed after cg.9 require a newer build or a source
checkout. Fixes are offered upstream when appropriate.

> [!NOTE]
> Under development. Test a release against your own targets before relying on it.

## What this fork adds

### Rendering as the claimed OS

For an identity whose OS is not the host's. Offered upstream in
[#896](https://github.com/daijro/camoufox/pull/896).

- **Per-script font fallback** follows the claimed OS's tables and `font.*`
  defaults, so Thai, emoji, Mongolian and other scripts draw with the faces
  stock Firefox uses there. ([7c8e6a9](https://github.com/coffeegrind123/camoufox-free/commit/7c8e6a9d8b3312846c26fe8e31984c10a1d3d6c6))
- **Native headless WebGL** uses Mesa EGL with `DISPLAY` and
  `WAYLAND_DISPLAY` unset. WebGL returns real rendering output, and WebGL2 does
  so when the recorded GPU supports it, while both report the identity's pinned
  GPU. Linux needs Mesa's EGL and DRI packages (`libegl1`, `libegl-mesa0` and
  `libgl1-mesa-dri` on Debian/Ubuntu); Xvfb is not required. See
  [Native headless WebGL](docs/headless-webgl.md).
- **DirectWrite line metrics** for a Windows identity (`fonts:metrics`), so
  line boxes match Windows instead of FreeType. ([c8cd204](https://github.com/coffeegrind123/camoufox-free/commit/c8cd20423c9640bbb381fc33a293c33ccbbddadf), [6023d01](https://github.com/coffeegrind123/camoufox-free/commit/6023d01bd194ad38e1fae7a3660c0c02d5c200fa))
- **Subpixel glyph positions** for a Windows or macOS identity, so text and
  form-control widths match those OSes. ([806329a](https://github.com/coffeegrind123/camoufox-free/commit/806329ab64dcf271802b672b57cae1ca7ac34ec6))
- **macOS UCS4 cmaps** are read for a macOS identity, so Geneva, Apple Symbols
  and Heiti render instead of sitting unused in the font list. ([82092da](https://github.com/coffeegrind123/camoufox-free/commit/82092dac9937b7d87fd62cd64c84a4197f32ee0b))
- **Codecs:** `canPlayType()` and `mediaCapabilities.decodingInfo()` both
  answer as the claimed OS, with Windows' hardware codecs. ([8fa6bd8](https://github.com/coffeegrind123/camoufox-free/commit/8fa6bd86d751734ce2bd209aab4e01392aa7580e))
- **Windows system colours** (Highlight, AccentColor, dialog) instead of the
  host's GTK theme. ([51dfed2](https://github.com/coffeegrind123/camoufox-free/commit/51dfed22ff39a1bca9e1ab982b97b8c44292c534))

### Other browser fixes

- **Large per-context values cross content processes.** Firefox does not sync a
  string pref over 4 KiB. Font and voice lists over 3 KiB are stored in chunks
  and reassembled from a generation header, so every content-process page and
  worker sees the context's own lists. A context font list replaces the launch
  list instead of intersecting it. ([efcb4c6](https://github.com/coffeegrind123/camoufox-free/commit/efcb4c6c192dc20228995625616661a943f00ce3))
- **Context identity and proxy settings stay isolated.** Proxy credentials are
  isolated per container/private context, and a NewContext behind a proxy
  derives its WebRTC IP, timezone, locale and geolocation from that proxy's
  exit IP. Context viewports are bounded by the shared launch window. A guard
  also asserts that contexts never share Firefox's web-content process, so a
  cached font, locale or other context value cannot cross identities.
  ([b84880a](https://github.com/coffeegrind123/camoufox-free/commit/b84880ae39c173aa8250d377b8e0679689c4cad2), [3777eaf](https://github.com/coffeegrind123/camoufox-free/commit/3777eaf09cc91a2eb1d7d1522a425785d8b23353))
- **Authenticated SOCKS5 proxies.** Playwright rejects SOCKS5 credentials
  before Juggler receives the proxy, so the launchers pass them through an
  endpoint-scoped launch environment and Juggler builds the proxy with
  `newProxyInfoWithAuth`. This applies to launch-level proxies. Credentials
  passed to `NewContext` are rejected: put the endpoint in
  `CAMOU_PROXY_CREDENTIALS` and pass the context proxy without credentials.
  `socks5h` resolves names at the proxy. A setup error fails the request closed
  instead of falling back to the host's direct connection. Ported from
  liasica's [2f0be40](https://github.com/liasica/camoufox/commit/2f0be400e53b88bb9b00b3faf2356503ae9dbfab).
- **EME on for Windows identities.** With EME off, Firefox's "EME has been
  preffed off" error is one only Linux Firefox gives. ([1a43e61](https://github.com/coffeegrind123/camoufox-free/commit/1a43e61878b66ffa66334ee30c38a846842a0f19))
- **uBlock Origin doesn't hold requests** while it compiles its lists on a
  fresh profile (1–45 s). Requests in the first seconds go unfiltered.
  Upstream keeps the hold. ([41a9903](https://github.com/coffeegrind123/camoufox-free/commit/41a9903048c011b9fc9aa38aa9786d72d922a94d))
- **Network and automation protocol fixes.** Routed requests keep Firefox's
  original header order; UA, Accept-Language and per-scheme Accept-Encoding
  stay coherent; DNT and context locale are stable across navigation.
  WebSocket close arguments follow Firefox 158, and a failed promise-reaction
  attach rejects immediately instead of leaving Juggler hanging.
  ([a645377](https://github.com/coffeegrind123/camoufox-free/commit/a645377641887a9443c5e6be0d0f7e1e209eed39), [bf238e4](https://github.com/coffeegrind123/camoufox-free/commit/bf238e4a9f41f026674a0e6361f4ec496f5f542a), [3cebf99](https://github.com/coffeegrind123/camoufox-free/commit/3cebf99c8f486c211a5502099c9ecfdc91164813))
- **Per-context locale follows every scope.** A context's locale reaches
  `Intl`, `navigator.languages`, Accept-Language q-values, isolated worlds,
  dedicated/shared/service workers, AudioWorklets, requests without a browsing
  context, and built-in strings. Changing one context does not overwrite the
  launch locale or another context. ([1bd1dc3](https://github.com/coffeegrind123/camoufox-free/commit/1bd1dc3c2d263bff41abcbb07d50f965129d3e5c), [a173ea1](https://github.com/coffeegrind123/camoufox-free/commit/a173ea1673b0f9af17ab645b337f687c1ea79c4f))
- **Pinned viewport and GPU behaviour are deterministic.** A config that pins
  `window.innerWidth`/`innerHeight` no longer deadlocks viewport updates.
  Explicit `webgl_config` replaces a preset's GPU as one complete pair in both
  launchers. ([1fcfad6](https://github.com/coffeegrind123/camoufox-free/commit/1fcfad6245cf91797d80d3943903cbf46ec3b017), [6932314](https://github.com/coffeegrind123/camoufox-free/commit/6932314b3b76380af9ab4c714d069c02f9e7f2be))
- **Corrupt font data fails closed.** A damaged `groups.json` refuses the launch
  instead of widening the scan to every OS's fonts. Windows font-unit rates and
  essential-font aliases are regenerated from the pinned fpgen model.
- **Launcher failures are bounded and explicit.** Transient downloads retry
  429/5xx/connection failures, and the host GPU probe has a 30-second deadline
  that reports the executable and display it was probing instead of hanging.
  ([6fee36f](https://github.com/coffeegrind123/camoufox-free/commit/6fee36f05286233ea8c854faca4e53123fd283b6), [d5e2850](https://github.com/coffeegrind123/camoufox-free/commit/d5e28506cf2bca5a7d1a70083fa29bd5f3c2e3f8))
- **A late window-manager frame keeps the identity's window size.** An X11
  window manager can set its frame (`_NET_FRAME_EXTENTS`) after the window
  maps. Firefox adds it to `outerWidth/outerHeight` without a resize event, so
  the startup hold that keeps the identity's size never ran, and the outer size
  could exceed `screen.width`. The hold now also checks on a timer. Offered
  upstream in [#973](https://github.com/daijro/camoufox/pull/973).
  ([e2f61ee](https://github.com/coffeegrind123/camoufox-free/commit/e2f61eeeab04c977d839930237a8a4c94f529ee8), guard
  [startup-size-frame-extents.py](browser/tests/playwright/patches/startup-size-frame-extents.py))
- **Screen coordinates follow the spoofed window position.**
  `mozInnerScreenX/Y` and the `screenX/Y` of mouse and touch events came from
  the real window while `window.screenX/Y` reported the identity's, so wherever
  the window manager placed the window elsewhere (any X11 desktop), a page could
  read the real position. They now move with the spoofed position; browser code
  still gets the real one. Offered upstream in
  [#975](https://github.com/daijro/camoufox/pull/975).
  ([031108e](https://github.com/coffeegrind123/camoufox-free/commit/031108e0ed85469d834a9847bb5edcc17a4fcd84), guard
  [window-screen-origin.py](browser/tests/playwright/patches/window-screen-origin.py))
- **Humanized moves reach the page one per refresh frame.** Firefox
  coalesces a real mouse's motion into at most one `mousemove` per refresh
  tick, but Juggler's synthesized moves played on the trajectory's own clock:
  pages saw gaps of 5-13ms from Cursory and a steady ~22ms beat from mousecrack,
  most of them mid-frame. Each point now waits for the window's refresh and a
  frame sends the newest point due, as stock delivers a real mouse. Offered
  upstream in [#978](https://github.com/daijro/camoufox/pull/978).
  ([MouseDispatch.js](browser/additions/juggler/input/MouseDispatch.js), guard
  [humanize-mouse-trajectory.py](browser/tests/playwright/patches/humanize-mouse-trajectory.py))

### Kept here after upstream declined

- **`gpu_passthrough=True`.** A Linux container on Windows can render on the
  host's real GPU through WSL's D3D12 driver while claiming Windows Firefox on
  that GPU. The canvas stays uncovered, and WebGPU reports Windows' adapter
  limits. Declined in [#890](https://github.com/daijro/camoufox/pull/890):
  upstream's stated reason is that Mesa GL over D3D12 with FreeType draws
  differently from Windows' ANGLE and DirectWrite, and it asks for pixel
  comparisons against real Windows machines on the same GPU. ([aaf96d7](https://github.com/coffeegrind123/camoufox-free/commit/aaf96d7a94641757d88fff876dcd8b17d13b689a), [f7c27c8](https://github.com/coffeegrind123/camoufox-free/commit/f7c27c8681e55480b6f3f434b7a2e0e3a535598d))
- **`humanize_engine="mousecrack"`.** A second cursor engine, using
  [mousecrack](https://github.com/puffinsoft/mousecrack)'s trained network.
  Cursory stays the default. Declined in
  [#900](https://github.com/daijro/camoufox/pull/900): upstream would rather
  have one humanize engine, and by that PR's numbers Cursory was the more human
  of the two. ([529a730](https://github.com/coffeegrind123/camoufox-free/commit/529a730125862d65dd6085e05c398ae9bd2aabb4))
- **First humanized move** starts just inside the page's top edge, not at
  (0, 0). Left out of [#900](https://github.com/daijro/camoufox/pull/900):
  upstream's stated reason is that it changes Cursory's default for everyone
  and its entry point comes from chosen constants rather than recorded data.
  ([33f01dc](https://github.com/coffeegrind123/camoufox-free/commit/33f01dc5cacc9cc58aa1cf0e41a132a7e001ae9c))
- **Geolocation accuracy.** IP-derived positions are rounded to the database's
  precision and carry a city-scale accuracy in whole metres, instead of
  14 decimals and 6e-10 m. Declined in
  [#904](https://github.com/daijro/camoufox/pull/904): upstream's stated reason
  is that the shipped database has no `accuracy_radius` records, so the 1-10 km
  fallback is not drawn from real data. ([bb7bc29](https://github.com/coffeegrind123/camoufox-free/commit/bb7bc29fd5cf77167cbeffe7fbfbd1d9d0b63b10), [9954eac](https://github.com/coffeegrind123/camoufox-free/commit/9954eac531391b0ae56917dccab150dfe81fc568))
- **Fontconfig memo keyed by context.** One context's font allow-list no longer
  answers for other contexts in the same content process. Declined in
  [#942](https://github.com/daijro/camoufox/pull/942) because Firefox 158 gives
  each context its own content-process pool, so the leak cannot occur there;
  measured here as well (three contexts, three processes on 158). Kept as a
  defence should a later Firefox share the pools again. ([6950149](https://github.com/coffeegrind123/camoufox-free/commit/6950149e920820710122e176ab66bd14d66db4c4))
- **Storage puts sync from the main thread.** Left out of
  [#802](https://github.com/daijro/camoufox/pull/802), whose read side upstream
  merged: upstream's stated reason is that a worker starting before its
  process's main thread has used the storage would broadcast the launch-wide
  timezone fallback to every process. ([b481348](https://github.com/coffeegrind123/camoufox-free/commit/b481348b58bf4a6b6bcd4f59a7f348fe32720212))

### Build, releases and defaults

- **uBlock Origin is resolved once per release and bundled verified.** The
  release workflow passes AMO's newest uBO release to packaging as
  `CAMOUFOX_UBO`; `browser/scripts/fetch-ubo.py` checks its SHA-256, add-on ID
  and version, then stages it under `addons/UBO/`. Bundle updates stay disabled,
  and the selected filter lists are pinned to the ten lists inside that bundle,
  so a first run downloads no regional list before pages load.
  ([`build.yml`](.github/workflows/build.yml), [`policies.json`](browser/settings/distribution/policies.json), [7ac4b21](https://github.com/coffeegrind123/camoufox-free/commit/7ac4b2132c3a6f7d3ee1a5e821d01da5d31f9586))
- **Linux x86_64 releases built by this repo's CI**
  ([`build.yml`](.github/workflows/build.yml)), with sha256 digests. No PyPI or
  npm packages are published, and upstream's release train doesn't run. ([b70dc6c](https://github.com/coffeegrind123/camoufox-free/commit/b70dc6c52c1605ad8bcf7c7770cf99d2235dd8a0))
- **Releases are tag-driven and do not wait for Tests.** Pushing a matching
  `v<version>-<release>-cg.<n>` tag starts the release workflow; pushing to
  `main` does not create a release. The release workflow fails before building
  unless the tag names the pinned browser and its commit is on `main` with a
  successful `All tests passed` check.
- **Cross-language LTO and PGO** with a pinned profile, as stock Firefox builds
  ([`ci/pgo.py`](ci/pgo.py)). A release is refused until a profile is pinned.
  Upstream merged its own form of [#886](https://github.com/daijro/camoufox/pull/886)
  (`browser/scripts/pgo.py`); this fork builds with its own pipeline until the
  next upstream sync. ([3381943](https://github.com/coffeegrind123/camoufox-free/commit/3381943c57abebf06301bebee4e8f4a230781c44))
- **`canvas_noise` defaults to `False`:** the canvas is never covered.
  `canvas_noise=None` gives upstream's automatic cover. ([38ef536](https://github.com/coffeegrind123/camoufox-free/commit/38ef536579a3b1284929dfaf544dfb6e124a217e))
- **Stock-parity probe lab**
  ([`browser/tests/parity/`](browser/tests/parity)). It's a manual harness that
  diffs what a page sees in stock Firefox and in Camoufox, and it checks for
  leaks between contexts. ([9a9de49](https://github.com/coffeegrind123/camoufox-free/commit/9a9de495c1d223b7225ec4ee6eb05b0081b6968b))
- **Incremental local builds.** Prepared trees keep their object directory, and
  changed additions are synced without rewriting unchanged files. `make
  build-js`, `make build-cpp`, and strict `make verify-patches` reduce rebuild
  time without changing the release build.
  ([8960323](https://github.com/coffeegrind123/camoufox-free/commit/8960323299e7bb3905dad47f5c0353b156dd20af), [2dd90d6](https://github.com/coffeegrind123/camoufox-free/commit/2dd90d65fe7546b3a10cb730cf8124f0d348e80d))
- **Read-only PropertyTracer audit.** [`audit-property-tracer.py`](browser/scripts/audit-property-tracer.py)
  checks the 77 native source sites behind page-observable properties after a
  Firefox upgrade. It does not inject runtime tracing or shipping code. See
  [Property tracer source audit](docs/property-tracer-audit.md).
  ([8473213](https://github.com/coffeegrind123/camoufox-free/commit/84732136d0181a7796e6dfbbcec7c47f5427baf9))
- **CI and the TypeScript launcher.** The TypeScript unit and browser jobs run
  type checks, lint/build checks and Vitest, but are advisory: they use
  `continue-on-error` and are excluded from the workflow's aggregate gate. The
  package install job is restricted to upstream. `main` requires the aggregate
  `All tests passed` check, with force-pushes and branch deletion disabled. The
  TypeScript launcher is kept as upstream has it, but not every Python change
  is ported to it. ([f9e1994](https://github.com/coffeegrind123/camoufox-free/commit/f9e1994f29824bb0a58a192867e85fa7ba2cc5da), [6978636](https://github.com/coffeegrind123/camoufox-free/commit/697863638dbaa4f2c16635f62e6ae0797fbc9a17))

## Maintenance

- [CI pipeline](ci/README.md) documents every merge-gating suite, shard and
  artifact.
- [Fork and closed-PR scanning](AGENTS.md#fork-and-upstream-review) defines how
  external Camoufox work is inventoried, measured and accepted or rejected, and
  how this fork's own merged upstream pull requests are checked for drift
  (`python3 -m ci.upstream_pr_drift`).
- [Patch upgrading](docs/patch-upgrading-guide.md) covers Firefox and Playwright
  syncs, patch regeneration and the required replay checks.
- [PropertyTracer audit](docs/property-tracer-audit.md) rechecks the native
  source sites behind page-observable properties after Firefox upgrades.

## Building locally

The browser builds on Linux. From the repository root:

```bash
cd browser
make bootstrap                 # host packages and mach bootstrap, once
make dir                       # fetch Firefox, sync additions, apply every patch
make verify-patches compare=true
make build
make package-linux arch=x86_64
```

After editing Juggler, prefs, or copied resources, use `make build-js`. After
editing C++, use `make build-cpp`. `make sync` only copies changed additions
and settings. `make dir` preserves `obj-*` by default; use
`CAMOUFOX_CLOBBER=1 make dir` for a clean rebuild. The optional Docker build
can use sccache and persistent compiler-cache volumes without changing release
flags. Patch authoring and regeneration are covered in
[`docs/patch-upgrading-guide.md`](docs/patch-upgrading-guide.md).

## Installing

Each [release](https://github.com/coffeegrind123/camoufox-free/releases) is one
Linux x86_64 browser zip. There is no separate checksum asset; GitHub exposes
the zip's SHA-256 in the release asset's `digest` field. Install the launcher
from the commit the release tag points at, so the two agree about config
properties:

```bash
pip install --force-reinstall "camoufox[geoip] @ git+https://github.com/coffeegrind123/camoufox-free.git@<release commit>#subdirectory=python"
```

Every commit reports the same package version, hence `--force-reinstall`.
Unpack the zip, check its sha256 against the release's `digest`, and point the
launcher at it:

```python
from camoufox.sync_api import Camoufox

with Camoufox(executable_path="/opt/camoufox/camoufox-bin") as browser:
    page = browser.new_page()
    page.goto("https://example.com")
```

The launcher installs fpgen's model itself, pinned by URL and sha256. To
install it ahead of time, for example while building an image:

```bash
python -c "from camoufox.fpgen_model import ensure_fpgen_model; ensure_fpgen_model()"
```

`camoufox fetch` first consults a non-empty browser pin. This repository and
its source installs have an empty `browser-pin.json`, so bare `camoufox fetch`
still falls back to `official/stable` in
[`repos.yml`](python/src/camoufox/repos.yml). A stamped library release follows
its `CamoufoxFree` pin and fetches the matching fork tag. The fork source is
also available explicitly:

```bash
camoufox fetch camoufoxfree/158.0-beta.33-cg.9
```

The release zip can still be installed manually and passed through
`executable_path`, as shown above.

## Licensing

| Part | Licence |
|---|---|
| The browser (`browser/`) | [MPL-2.0](LICENSE) |
| Vendored Cursory trajectories | LGPLv3-or-later ([`NOTICE`](browser/additions/juggler/input/cursory/NOTICE)) |
| mousecrack's model and its port | MIT (`browser/additions/juggler/input/mousecrack/LICENSE`) |
| Python and TypeScript packages | MIT ([`python/LICENSE`](python/LICENSE), [`typescript/LICENSE`](typescript/LICENSE)) |
