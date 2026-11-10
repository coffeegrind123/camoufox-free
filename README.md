# camoufox-free

A fork of [Camoufox](https://github.com/daijro/camoufox), the Firefox build
that spoofs device fingerprints in C++. For what Camoufox is, its features and
how to build it, read [upstream's README](https://github.com/daijro/camoufox#readme).

This fork follows upstream `main` and pins Firefox `159.0.1` / Camoufox `beta.35`
in [`browser/upstream.sh`](browser/upstream.sh). The current release, and the
only one published, is
[`v159.0.1-beta.35-cg.14`](https://github.com/coffeegrind123/camoufox-free/releases/tag/v159.0.1-beta.35-cg.14),
built from [70dbf55](https://github.com/coffeegrind123/camoufox-free/commit/70dbf558040eb9204dd77409490fd20df8c34aa9).
Everything listed below is in it. Fixes are offered upstream when appropriate.

> [!NOTE]
> Under development. Test a release against your own targets before relying on it.

## What this fork adds

### Rendering as the claimed OS

For an identity whose OS is not the host's. Offered upstream in
[#896](https://github.com/daijro/camoufox/pull/896).

- **Per-script font fallback** follows the claimed OS's tables and `font.*`
  defaults, so Thai, emoji, Mongolian and other scripts draw with the faces
  stock Firefox uses there. Where stock's Windows table names a face Windows 10
  and 11 no longer ship (Lao UI, Euphemia), the face Windows' own system
  fallback draws follows it (Leelawadee UI, Gadugi). ([7c8e6a9](https://github.com/coffeegrind123/camoufox-free/commit/7c8e6a9d8b3312846c26fe8e31984c10a1d3d6c6))
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

- **WebGL1 reports WebGL2's value for every shared parameter.** Firefox 156+
  creates both on one GL profile; fpgen recorded 146, where they differ, and
  CreepJS flags any mirrored parameter that does (two Linux records differed in
  `ALIASED_POINT_SIZE_RANGE`). Both launchers copy every shared non-string
  parameter. Offered upstream in [#1020](https://github.com/daijro/camoufox/pull/1020). ([5e59245](https://github.com/coffeegrind123/camoufox-free/commit/5e59245d0c542570df95514ef6bac295958db288))
- **OffscreenCanvas has no WebGL2 where the device has none.** For a device
  recorded without WebGL2, a canvas element offered none but OffscreenCanvas
  did, with the host's real parameters under the spoofed renderer name, which
  CreepJS flags. It now follows `webgl.enable-webgl2`, which stock never turns
  off. Offered upstream in [#1022](https://github.com/daijro/camoufox/pull/1022). ([c313578](https://github.com/coffeegrind123/camoufox-free/commit/c313578b39b5377530adee05b158e41584ec64b9), guard
  [offscreen-webgl2-follows-canvas.py](browser/tests/playwright/patches/offscreen-webgl2-follows-canvas.py))
- **A repaired display scale keeps the display.** fpgen records some ratios
  with a browser zoom folded in (1.0909 for 110%), which shrinks every CSS size.
  The coherence repair moved the ratio to a real scaling step but kept the
  shrunken sizes, so a 1920x1080 monitor was claimed as 1760x990 at 100%, and a
  fullscreen window measured 1920x1080 against `screen.width` 1760. The geometry
  is now rescaled with the ratio, including a ratio the launcher draws from
  fpgen itself, which used to skip the repair. A screen the caller sets is
  never rescaled. Offered upstream in [#1003](https://github.com/daijro/camoufox/pull/1003).
  ([357cd48](https://github.com/coffeegrind123/camoufox-free/commit/357cd487113dad9a858a8e4ff7773e9cc141817c), [52b234f](https://github.com/coffeegrind123/camoufox-free/commit/52b234f29ba359dd7d2e2ae00743d3ee74f998d1), [1d1640b](https://github.com/coffeegrind123/camoufox-free/commit/1d1640bcc8de582f4ce49726258ee57c8fc9bff2), [#27](https://github.com/coffeegrind123/camoufox-free/pull/27))
- **Large per-context values cross content processes.** Firefox does not sync a
  string pref over 4 KiB. Font and voice lists over 3 KiB are stored in chunks
  and reassembled from a generation header, so every content-process page and
  worker sees the context's own lists. A context font list replaces the launch
  list instead of intersecting it. ([efcb4c6](https://github.com/coffeegrind123/camoufox-free/commit/efcb4c6c192dc20228995625616661a943f00ce3))
- **A context keeps voice names that hold a comma.** A context's voice list
  was passed comma-separated, and Windows names hold commas ("Microsoft Hanhan -
  Chinese (Traditional, Taiwan)"), so one such name emptied the context's whole
  voice list. It is one name per line now. Ported from introvert's
  [17e739f](https://github.com/introvert/camoufox/commit/17e739f9b2cf15d56742f2d196da636df13d1db6).
  ([patch](browser/patches/speech-voices-spoofing.patch), guard
  [context-voice-names.py](browser/tests/playwright/patches/context-voice-names.py))
- **Context identity and proxy settings stay isolated.** Proxy credentials are
  isolated per container/private context, and a NewContext behind a proxy
  derives its WebRTC IP, timezone, locale and geolocation from that proxy's
  exit IP. Context viewports are bounded by the shared launch window. The
  proxy exit placement is offered upstream in
  [#990](https://github.com/daijro/camoufox/pull/990).
  ([b84880a](https://github.com/coffeegrind123/camoufox-free/commit/b84880ae39c173aa8250d377b8e0679689c4cad2), [3777eaf](https://github.com/coffeegrind123/camoufox-free/commit/3777eaf09cc91a2eb1d7d1522a425785d8b23353))
- **Re-setting a context's proxy keeps its storage.** Dropping the old
  proxy's cached login went through Gecko's "forget this context's data"
  signal, so the page lost its sessionStorage and push subscriptions
  mid-session. Only the proxy auth cache is cleared now, on a topic of its own.
  ([66cb54c](https://github.com/coffeegrind123/camoufox-free/commit/66cb54c5cd402ff25720d7b53705a6ef4aff3f46))
- **Context-only proxies carry the browser's own traffic.** With a proxy per
  context and none for the launch, connections no page owns (the push
  websocket, media plugin update checks) went out direct from the host's
  address. They now take a proxied context's proxy; a page's own request keeps
  its context's. ([58e3760](https://github.com/coffeegrind123/camoufox-free/commit/58e3760a83d04efa30982288f5ff00c61da0af1e), guard
  [context-proxy-browser-traffic.py](browser/tests/playwright/patches/context-proxy-browser-traffic.py))
- **Authenticated SOCKS5 proxies fail closed.** Upstream passes SOCKS5
  credentials to Juggler (`CAMOU_PROXY_AUTH`, and a per-context init script).
  On top of that transport, `socks5h` and credentials in the proxy URL are
  accepted, a port is required, a caller's `CAMOU_PROXY_CREDENTIALS` map
  (`host:port` to credentials) is still honoured and cleared after reading,
  and a setup error fails the request closed instead of falling back to the
  host's direct connection. Ported from
  liasica's [2f0be40](https://github.com/liasica/camoufox/commit/2f0be400e53b88bb9b00b3faf2356503ae9dbfab).
  ([29b467f](https://github.com/coffeegrind123/camoufox-free/commit/29b467fd6fa2e7f82b85a3a2b43eb9eea183c4ce))
- **A proxy set through prefs resolves names at the proxy.** Upstream's #997
  removed `network.proxy.socks_remote_dns`, so a SOCKS proxy given in
  `firefox_user_prefs` (or a system proxy) would resolve DNS on the host.
  ([camoufox.cfg](browser/settings/camoufox.cfg), [2a48d607](https://github.com/coffeegrind123/camoufox-free/commit/2a48d6072738d8ac47d428e34bbac130ae0735e2))
- **A GPU-less Linux host still claims a drawn GPU.** Upstream's #1006 makes a
  Linux identity on a host that renders in software report `llvmpipe`. Not
  taken until the public detectors are compared on both.
  ([2a48d607](https://github.com/coffeegrind123/camoufox-free/commit/2a48d6072738d8ac47d428e34bbac130ae0735e2))
- **EME on for Windows identities.** With EME off, Firefox's "EME has been
  preffed off" error is one only Linux Firefox gives. Upstream's
  [#894](https://github.com/daijro/camoufox/pull/894) leaves EME off, on the
  grounds that a Linux build cannot deliver Windows' PlayReady key system. ([1a43e61](https://github.com/coffeegrind123/camoufox-free/commit/1a43e61878b66ffa66334ee30c38a846842a0f19))
- **uBlock Origin starts warm on a fresh profile.** Every launch is a fresh
  uBO install, which compiles all its lists for 10–25 s while its webRequest
  listener answers nothing, so a page's own requests stalled 9–17 s whatever
  `suspendUntilListsAreLoaded` says (upstream keeps that hold on too). The
  release now carries the selfie its own browser compiled, and a first run
  loads it as a long-used install does: ready in 2–4 s, no request held over
  2 s. It is saved into the profile, so a kept profile's next launch starts warm
  too. `suspendUntilListsAreLoaded` is also false in the bundled uBO's own
  defaults (there is no `policies.json`).
  ([dacdda3](https://github.com/coffeegrind123/camoufox-free/commit/dacdda34ead3e11cfc94a10c25a06e4ebf127859), guard
  [ubo-seeded-start.py](browser/tests/playwright/patches/ubo-seeded-start.py),
  [fetch-ubo.py](browser/scripts/fetch-ubo.py), [41a9903](https://github.com/coffeegrind123/camoufox-free/commit/41a9903048c011b9fc9aa38aa9786d72d922a94d), [2a48d607](https://github.com/coffeegrind123/camoufox-free/commit/2a48d6072738d8ac47d428e34bbac130ae0735e2))
- **Network and automation protocol fixes.** Routed requests keep Firefox's
  original header order; UA, Accept-Language and per-scheme Accept-Encoding
  stay coherent; DNT and context locale are stable across navigation.
  A failed promise-reaction attach rejects immediately instead of leaving
  Juggler hanging. The header order fix is offered upstream in
  [#989](https://github.com/daijro/camoufox/pull/989).
  ([a645377](https://github.com/coffeegrind123/camoufox-free/commit/a645377641887a9443c5e6be0d0f7e1e209eed39), [3cebf99](https://github.com/coffeegrind123/camoufox-free/commit/3cebf99c8f486c211a5502099c9ecfdc91164813))
- **Per-context locale follows every scope.** A context's locale reaches
  `Intl`, `navigator.languages`, Accept-Language q-values, isolated worlds,
  dedicated/shared/service workers, AudioWorklets, requests without a browsing
  context, and built-in strings. Changing one context does not overwrite the
  launch locale or another context. ([1bd1dc3](https://github.com/coffeegrind123/camoufox-free/commit/1bd1dc3c2d263bff41abcbb07d50f965129d3e5c), [a173ea1](https://github.com/coffeegrind123/camoufox-free/commit/a173ea1673b0f9af17ab645b337f687c1ea79c4f))
- **A context lists and speaks with its own voices** (a Linux context its speech-dispatcher grid, inside any launch). A context's voices only
  filtered the voices the launch registered, so a de-DE context in an en-US
  Windows launch listed no German voice, where a German Windows lists its
  language pack's. Contexts now draw their voices for their locale, the
  launchers pass every voice of the manifests as `voices:pool`, and the
  browser shows each context the voices it lists, in its order. Pages of a
  context without a list still see only the launch's voices, and an utterance
  is matched only among the voices its page can list. Ported from introvert's
  [4de36ca](https://github.com/introvert/camoufox/commit/4de36ca1b3e1b544368a31a3617f896a9b7951d9)
  and [17e739f](https://github.com/introvert/camoufox/commit/17e739f9b2cf15d56742f2d196da636df13d1db6).
  (guard [context-voice-pool.py](browser/tests/playwright/patches/context-voice-pool.py))
- **Pinned viewport and GPU behaviour are deterministic.** A config that pins
  `window.innerWidth`/`innerHeight` no longer deadlocks viewport updates.
  Explicit `webgl_config` replaces a preset's GPU as one complete pair in both
  launchers. ([1fcfad6](https://github.com/coffeegrind123/camoufox-free/commit/1fcfad6245cf91797d80d3943903cbf46ec3b017), [6932314](https://github.com/coffeegrind123/camoufox-free/commit/6932314b3b76380af9ab4c714d069c02f9e7f2be))
- **A context reports its own GPU's WebGL limits.** A `NewContext` that claimed
  another GPU named that GPU in `UNMASKED_RENDERER_WEBGL`, but its
  `getParameter` limits, `getSupportedExtensions()` and
  `getShaderPrecisionFormat()` stayed the launch GPU's, a pairing no real device
  reports. `setWebGLConfig` gives each context its GPU's tables, in pages,
  iframes and workers, and both launchers send them; upstream's
  [#888](https://github.com/daijro/camoufox/pull/888) lookup reads only the
  launch's tables. Ported from introvert's
  [a44e6d1](https://github.com/introvert/camoufox/commit/a44e6d15fa0ce6df438615434d0b12ee5cdd4490).
  (guard [context-webgl-tables.py](browser/tests/playwright/patches/context-webgl-tables.py))
- **Corrupt font data fails closed.** A damaged `groups.json`, or one whose
  group directories are missing with no per-OS directory either, refuses the
  launch instead of widening the scan to every OS's fonts (the missing-groups
  case ported from lang315's
  [2479033](https://github.com/lang315/camoufox/commit/24790332a7a442f988f28c3ca2331e2629273997)). Windows font-unit rates and
  essential-font aliases are regenerated from the pinned fpgen model.
- **Font aliases only where the claimed OS resolves them.** The font bundle
  added every fonts.conf alias to every base and to the essential floor, so
  every macOS draw reported names whose absence marks newer macOS versions,
  and every Linux draw reported Calibri and Cambria without their
  metric-compatible targets. A base now carries an alias only where that OS
  version resolves it, and the essential floor is what every base shares.
  Ported from introvert's
  [d44921e](https://github.com/introvert/camoufox/commit/d44921e7e8103486aa8ef1232edee1ce5089d3e9).
  ([ae1f515](https://github.com/coffeegrind123/camoufox-free/commit/ae1f51504418287b2f8dbedc4650073f72e48207))
- **Launcher failures are bounded and explicit.** Transient downloads retry
  429/5xx/connection failures, and the host GPU probe has a 30-second deadline
  that reports the executable and display it was probing instead of hanging;
  the probe deadline is offered upstream in
  [#985](https://github.com/daijro/camoufox/pull/985).
  ([6fee36f](https://github.com/coffeegrind123/camoufox-free/commit/6fee36f05286233ea8c854faca4e53123fd283b6), [d5e2850](https://github.com/coffeegrind123/camoufox-free/commit/d5e28506cf2bca5a7d1a70083fa29bd5f3c2e3f8))
- **A late window-manager frame keeps the identity's window size.** An X11
  window manager can set its frame (`_NET_FRAME_EXTENTS`) after the window
  maps. Firefox adds it to `outerWidth/outerHeight` without a resize event, so
  the startup hold that keeps the identity's size never ran, and the outer size
  could exceed `screen.width`. The hold now also checks on a timer. Offered
  upstream in [#973](https://github.com/daijro/camoufox/pull/973).
  ([e2f61ee](https://github.com/coffeegrind123/camoufox-free/commit/e2f61eeeab04c977d839930237a8a4c94f529ee8), guard
  [startup-size-frame-extents.py](browser/tests/playwright/patches/startup-size-frame-extents.py))
- **The startup size holds through a late toolbar reflow.** The toolbars
  can shrink a few hundred ms after startup with no resize event; the hold took
  the unchanged outer size for a fit and left the content area 12 px too tall
  (1000x662 for 1000x650). It now checks the content area too. Offered
  upstream in [#973](https://github.com/daijro/camoufox/pull/973).
  ([4b5a4aa](https://github.com/coffeegrind123/camoufox-free/commit/4b5a4aa0c76beb2354bd3311d8d3f7f1c270958b))
- **A Windows or macOS identity's window frame measures as stock's.** A page
  can measure the frame around its content area (`outerWidth - innerWidth`,
  `mozInnerScreenX - screenX`), and it came from the host: GTK's 86x192 under
  XWayland, with the content 43,149 into the window, where stock Firefox on
  Windows measures 16x93 and 8,85. A page now reads the real content area plus
  the claimed OS's frame at its display scale, in a cross-site iframe too, and
  no frame in fullscreen. A Windows identity drawn maximized gets stock's
  maximized geometry (outer the available area plus the borders, at minus the
  border), and a window maximized later goes back to the identity's size. The
  frame follows the window's state: maximized while the real window is or its
  content fills the available area, the normal frame once a resize leaves it
  (it kept the maximized frame at -8,-8 at any size), and no frame at 0,0 in
  fullscreen. ([patch](browser/patches/window-sizing-claimed-os.patch),
  [zz-window-presentation.patch](browser/patches/zz-window-presentation.patch),
  [3924094](https://github.com/coffeegrind123/camoufox-free/commit/39240942ecd1e20088209001414b64a1d621d4b5), guard
  [window-sizing-claimed-os.py](browser/tests/playwright/patches/window-sizing-claimed-os.py))
- **Screen coordinates hold where the window manager won't move the window.**
  Upstream's #997 moves the real window to the identity's position and reports
  the real one. Where the window manager places the launch's window elsewhere,
  `window.screenX/Y`, `mozInnerScreenX/Y` and event `screenX/Y` still report
  the identity's position, consistently; a popup a page opened reports where it
  really is. The getter costs what stock's does (getter-cost-parity.py).
  ([031108e](https://github.com/coffeegrind123/camoufox-free/commit/031108e0ed85469d834a9847bb5edcc17a4fcd84), [2a48d607](https://github.com/coffeegrind123/camoufox-free/commit/2a48d6072738d8ac47d428e34bbac130ae0735e2), [96e66d86](https://github.com/coffeegrind123/camoufox-free/commit/96e66d86794e3652134a30eec73e9bc164aebfbd), guard
  [window-screen-origin.py](browser/tests/playwright/patches/window-screen-origin.py))
- **A humanized curve leaves the page as a real pointer does.** A point
  outside the viewport was skipped with no event, so a curve that strayed off
  the page left the cursor frozen at the edge with no `mouseout`, then
  reappearing elsewhere, mid-page when a slow frame coalesced the re-entry.
  The pointer now moves off the content (over the toolbar when it left through
  the top) and re-enters with `mouseover`, and a page's first move redraws a
  path that climbs out of the page. Ported onto upstream's #997 input design;
  the page exit is offered upstream in
  [#987](https://github.com/daijro/camoufox/pull/987), and the guard's check
  that moves arrive at refresh ticks in
  [#978](https://github.com/daijro/camoufox/pull/978).
  ([MouseDispatch.js](browser/additions/juggler/input/MouseDispatch.js), guard
  [humanize-mouse-trajectory.py](browser/tests/playwright/patches/humanize-mouse-trajectory.py))
- **Humanized moves report like a 125 Hz mouse.** They were resampled to
  60 Hz, but `pointerrawupdate` and `getCoalescedEvents()` show every report:
  stock under a real mouse shows about two per frame, 8 ms apart, humanize one,
  16 ms apart. Steps now go out at 125 Hz on their due time.
  ([e5dc64a](https://github.com/coffeegrind123/camoufox-free/commit/e5dc64a9c4270e5db81dbf65b0471f3ea3142411))
- **A driven move off the page leaves where it goes.** `page.mouse.move()` to a
  point outside the viewport reported every exit at the window's top-left
  corner, (0, -85) for a Windows identity. It now leaves where it crosses, as
  stock does. ([9d0c36e](https://github.com/coffeegrind123/camoufox-free/commit/9d0c36e88ee10abab1480e5fc472463913cea5e7), guard
  [driven-exit-point.py](browser/tests/playwright/patches/driven-exit-point.py))
- **A drag follows the claimed OS.** Juggler emulated GTK's drag for every
  identity. A Windows identity's drag now keeps hover on the source until the
  drop and fires `drag`/`dragover` on Windows' timer while the button is held,
  as stock 159 on Windows 11 does; macOS gets its own.
  ([14e0b87](https://github.com/coffeegrind123/camoufox-free/commit/14e0b874da20bda313b9c16e3dc65af07c8d7fbb), guard
  [driven-drag-windows.py](browser/tests/playwright/patches/driven-drag-windows.py))
- **A context reports the launch's core count.** NewContext drew a fresh
  `navigator.hardwareConcurrency` for each context, while the launch reports
  the host's cores (`fix_hardware_concurrency`), which a page can measure with
  workers. Contexts now report the launch's value, in both launchers. Ported
  from introvert's
  [17e739f](https://github.com/introvert/camoufox/commit/17e739f9b2cf15d56742f2d196da636df13d1db6).
  ([f47173c](https://github.com/coffeegrind123/camoufox-free/commit/f47173c5d2c79a0172a1e23586805c815cbb2eed), [9105041](https://github.com/coffeegrind123/camoufox-free/commit/910504119347980a668293db79a2c1b7c181f849),
  tests [Python](python/tests/test_context_geometry.py), [TypeScript](typescript/tests/context-geometry.test.ts))
- **A context's language list keeps its first entry as the locale.** Given
  Playwright's `locale="de, en-US, en"`, a context reported the list in
  `navigator.languages` and Accept-Language, but every place that reads a
  locale took the whole list: Intl fell back to en-GB in pages and workers, and
  realm overrides read `de` for `de-DE, de, …`. The first entry is now the
  locale wherever one is read, and built-in strings are negotiated from the
  whole list. Ported from introvert's
  [4e1dde8](https://github.com/introvert/camoufox/commit/4e1dde86f5cfd8eb24afedef189ac976fed8df75).
  ([patch](browser/patches/zzz-context-locale.patch), guard
  [context-locale-follows.py](browser/tests/playwright/patches/context-locale-follows.py))
- **Webcompat interventions follow the claimed OS.** Firefox's webcompat
  add-on picked its per-site fixes by the host's OS, so a Windows identity on
  Linux sent some sites a macOS UA, `sec-ch-ua-platform: "Linux"` or a Chrome
  UA stock Windows never sends. The launcher sets its platform override to the
  claimed OS. ([09b5fc6](https://github.com/coffeegrind123/camoufox-free/commit/09b5fc6bf897143eedd57d73b8b8e0a936d2ad1d))
- **The search region follows the locale's region.** Stock learns it from a
  network lookup the launch turns off; unset, every identity got the
  region-less engine list and the DoH rollout never decided. ([2723224](https://github.com/coffeegrind123/camoufox-free/commit/2723224cbc9bcee2e156042f203a7a8154450d95))

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

- **uBlock Origin's selected filter lists are the ten in its bundle.** Upstream
  bundles uBO and stops it updating lists, but uBO still selected regional lists
  for the browser's locale on first run and downloaded them before pages
  loaded. `fetch-ubo.py` turns off that regional selection in the bundled
  uBO. Ported from lang315.
  ([fetch-ubo.py](browser/scripts/fetch-ubo.py), [9ec4708](https://github.com/coffeegrind123/camoufox-free/commit/9ec47080a87288f1227945ccc71170df07b3ce94), [2a48d607](https://github.com/coffeegrind123/camoufox-free/commit/2a48d6072738d8ac47d428e34bbac130ae0735e2))
- **The bundled uBlock Origin is a committed release.** Upstream bundles AMO's
  newest at build time. uBO 1.76.0 changed the global order of every page
  after the first (`RegExp`), where stock and 1.75.4 do not, so
  [`data/ubo.json`](browser/scripts/data/ubo.json) pins the release by
  sha256 and a bump is a reviewed commit. Offered upstream in
  [#1012](https://github.com/daijro/camoufox/pull/1012). ([73921940](https://github.com/coffeegrind123/camoufox-free/commit/739219402277874bec6326ad80bce4c5c9587327))
- **The release build checks uBO as a user that owns no file.** Every guard
  ran as the owner on the unpackaged build, so none saw a zip that hid uBO
  from another user. The build now unzips the release and installs the
  launcher as root, then runs the uBO guard as a user that owns neither. The
  guard names an unreadable addon, and fails when a page load still takes
  over 10 s once uBO is ready. Upstream merged the staging and packaging fix
  this guards, from [#1002](https://github.com/daijro/camoufox/pull/1002).
  ([a494551](https://github.com/coffeegrind123/camoufox-free/commit/a494551287ec0585163f89607440fbb24aaa237d))
- **DuckDuckGo is the default search engine.** Upstream's #997 restored
  stock's engines and default. This fork keeps stock's engine list and makes
  DuckDuckGo the default, in the search service's own engine selection, where a
  page can't read it.
  ([search-default-duckduckgo.patch](browser/patches/search-default-duckduckgo.patch), [6e24feb](https://github.com/coffeegrind123/camoufox-free/commit/6e24feb8b621bfdd794d1745105f08596a907040), [2a48d607](https://github.com/coffeegrind123/camoufox-free/commit/2a48d6072738d8ac47d428e34bbac130ae0735e2))
- **Linux x86_64 releases built by this repo's CI**
  ([`build.yml`](.github/workflows/build.yml)), with sha256 digests. No PyPI or
  npm packages are published, and upstream's release train doesn't run. ([b70dc6c](https://github.com/coffeegrind123/camoufox-free/commit/b70dc6c52c1605ad8bcf7c7770cf99d2235dd8a0))
- **Releases are tag-driven and do not wait for Tests.** Pushing a matching
  `v<version>-<release>-cg.<n>` tag starts the release workflow; pushing to
  `main` does not create a release. The release workflow fails before building
  unless the tag names the pinned browser and its commit is on `main` with a
  successful `All tests passed` check.
- **Link Preview stays on, as stock ships it.** Upstream's #966 turned
  `browser.ml.linkPreview.enabled` off. On stock 159.0 a long press on a link
  fetches the link target anonymously with `x-firefox-ai: 1`; with the feature
  off that request never happens, which the target's server can see. Page
  events are the same either way. ([e449d72](https://github.com/coffeegrind123/camoufox-free/commit/e449d72970ee56e9a45474eb82520999c1a68505), guard
  [long-press-link-preview-parity.py](browser/tests/playwright/patches/long-press-link-preview-parity.py))
- **`canvas_noise` defaults to `False`:** the canvas is never covered.
  `canvas_noise=None` gives upstream's automatic cover. ([38ef536](https://github.com/coffeegrind123/camoufox-free/commit/38ef536579a3b1284929dfaf544dfb6e124a217e))
- **`low_bandwidth=1..3` for proxies billed per byte.** Level 1 is a 2 GiB
  disk cache, which a page cannot see; level 2 adds Firefox's cellular media
  preload, no link prefetch and no web fonts, and warns; level 3 also blocks
  images. It needs `enable_cache` and intercepts no request, since a route
  turns the context's cache off. Python and TypeScript. ([252d706](https://github.com/coffeegrind123/camoufox-free/commit/252d706d0ad5b6f3e92f1320d2fc8460b2b2f552))
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
`CAMOUFOX_CLOBBER=1 make dir` for a clean rebuild. Every build links with
cross-language LTO and the PGO profile Mozilla trained for the same Firefox,
which `make dir` fetches ([`browser/scripts/pgo.py`](browser/scripts/pgo.py));
ccache does not cache the LTO link, so an incremental build still relinks
libxul. The optional Docker build can use sccache and persistent
compiler-cache volumes without changing release flags. Patch authoring and regeneration are covered in
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
camoufox fetch camoufoxfree/158.0.1-beta.34-cg.12
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
