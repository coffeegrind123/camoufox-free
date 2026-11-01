# Patch Dependencies

Quick reference for the shared infrastructure patches build on. `scripts/patch.py`
applies every `patches/**/*.patch` in order of file name, so the
`playwright/0-*` and `playwright/1-*` patches go first and the rest follow
alphabetically. Each patch is generated against a tree with every earlier one
applied, and many hunks use an earlier patch's lines as context, so they apply
only in that order. The dependencies below are the ones a patch needs to
compile.

## camoucfg (MaskConfig)

`additions/camoucfg/MaskConfig.hpp` reads the spoofing config (`CAMOU_CONFIG` /
`camoufox.cfg`) through `MaskConfig::GetBool()`, `GetString()`, `GetUint32()`
and friends. `GetBool()` is false for an unset key; `GetOptionalBool()` is for
the rare caller that must tell unset from false. `SpoofedOSFor()` is the one
reading of a `navigator.platform` as an OS. `GetSpoofedOS()` is the launch's,
for process-wide decisions only (`font-hijacker.patch`'s bundled fonts, the
WebRTC host socket's port range in `webrtc-ip-spoofing.patch`); anything a page
can observe asks `NavigatorManager::GetSpoofedOS()` (`navigator-spoofing.patch`)
for its own context's OS, which is that context's `navigator.platform` when it
set one and the launch's otherwise.
`scripts/sync_additions.py --baseline` copies it into the source tree before any patch
applies. A patch that calls MaskConfig from a directory whose `moz.build` does
not already see `/camoucfg` must add `LOCAL_INCLUDES += ["/camoucfg"]` itself.

Config keys are declared in `settings/properties.json`; a key a patch reads must
be listed there.

### Patches that read config

| Patch | Config keys |
|-------|-------------|
| `audio-context-spoofing.patch` | `AudioContext:sampleRate`, `AudioContext:outputLatency`, `AudioContext:maxChannelCount` |
| `chromeutil.patch` | `debug` |
| `cmap-unicode-ucs4-fallback.patch` | `navigator.platform` (through `GetSpoofedOS()`) |
| `fallback-fonts-claimed-os.patch` | `navigator.platform` (through `GetSpoofedOS()`) |
| `fingerprint-injection.patch` | `navigator.*`, `screen.*`, `window.*` |
| `font-metrics-windows.patch` | `fonts:metrics` |
| `font-hijacker.patch` | `fonts`, `navigator.platform` |
| `font-system-fonts-css2.patch` | `navigator.platform`, `window.devicePixelRatio` |
| `force-default-pointer.patch` | `navigator.maxTouchPoints` |
| `geolocation-spoofing.patch` | `geolocation:*` |
| `locale-spoofing.patch` | `locale:*`, `navigator.language` |
| `media-codec-spoofing.patch` | `media:spoof_codecs` (bypasses `PDMFactory::Supports()` in `MP4Decoder`/`MatroskaDecoder` so `canPlayType()`/`isTypeSupported()` don't leak system codec libraries, and answers `decodingInfo()` to match), `media:hwCodecs` (the video MIME types `decodingInfo()` reports power-efficient) |
| `media-device-spoofing.patch` | `mediaDevices:*` |
| `navigator-spoofing.patch` | `navigator.*` |
| `network-patches.patch` | `headers.*`, `navigator.userAgent` |
| `no-css-animations.patch` | `instantAnimations` |
| `privacy-signals-spoofing.patch` | `navigator.doNotTrack` |
| `screen-spoofing.patch` | `screen.*` |
| `system-ui-font-spoofing.patch` | `navigator.platform` |
| `timezone-spoofing.patch` | `timezone` |
| `touchscreen-fingerprint-spoofing.patch` | `navigator.maxTouchPoints` |
| `voice-spoofing.patch` | `voices`, `voices:blockIfNotDefined` |
| `webgl-spoofing.patch` | `webGl:*`, `webGl2:*` |
| `webgpu-limits-spoofing.patch` | `webGpu:limits` |
| `webrtc-ip-spoofing.patch` | `webrtc:ipv4`, `webrtc:ipv6`, `navigator.platform` |
| `window-screen-origin.patch` | `window.screenX`, `window.screenY` (moves `mozInnerScreenX/Y` and mouse and touch event `screenX/Y` with them) |
| `windows-keyboard.patch` | `input:windowsKeyboard` (launch-wide: the shortcut tables and GTK's key handling are process-level) |
| `zz-stock-cost-parity.patch` | `navigator.hardwareConcurrency`, `navigator.maxTouchPoints`, `screen.*`, `window.screenX`, `window.screenY` (re-orders the getters above so stock's work runs first) |

To regenerate the list: `grep -l 'MaskConfig::' patches/*.patch`.

### Includes another patch provides

Some patches call MaskConfig from a file or directory that an earlier patch
already set up, and do not add the include or `LOCAL_INCLUDES` themselves:

| Patch | Relies on |
|-------|-----------|
| `cmap-unicode-ucs4-fallback.patch` | `font-hijacker.patch` for `/camoucfg` in `gfx/thebes/moz.build` |
| `fallback-fonts-claimed-os.patch` | `font-hijacker.patch` for `/camoucfg` in `gfx/thebes/moz.build` |
| `font-metrics-windows.patch` | `font-hijacker.patch` for `/camoucfg` in `gfx/thebes/moz.build` |
| `force-default-pointer.patch` | `screen-spoofing.patch` for `MaskConfig.hpp` in `layout/style/nsMediaFeatures.cpp`; `font-hijacker.patch` for `/camoucfg` in `layout/style/moz.build` |
| `media-device-spoofing.patch` | `audio-context-spoofing.patch` for `/camoucfg` in `dom/media/moz.build` |
| `privacy-signals-spoofing.patch` | `navigator-spoofing.patch` for `MaskConfig.hpp` in `dom/base/Navigator.cpp`; `network-patches.patch` for `/camoucfg` in `netwerk/protocol/http/moz.build` |
| `system-ui-font-spoofing.patch` | `font-hijacker.patch` for `MaskConfig.hpp` in `gfx/thebes/gfxPlatformFontList.cpp` and `/camoucfg` in `gfx/thebes/moz.build` |
| `touchscreen-fingerprint-spoofing.patch` | `navigator-spoofing.patch` for `MaskConfig.hpp` in `dom/base/Navigator.cpp` |
| `font-list-spoofing.patch` | `anti-font-fingerprinting.patch` for `gfxFontGroup::mUserContextId` |
| `timezone-spoofing.patch`, `webrtc-ip-spoofing.patch` | `audio-fingerprint-manager.patch` for `RoverfoxStorageManager.h` in `dom/base/nsGlobalWindowInner.cpp` |
| `font-system-fonts-css2.patch`, `system-ui-font-spoofing.patch`, `webrtc-ip-spoofing.patch`, `zz-stock-cost-parity.patch` | `navigator-spoofing.patch` for `NavigatorManager::GetSpoofedOS()` |
| `windows-keyboard.patch` | `touchscreen-fingerprint-spoofing.patch` for `/camoucfg` in `dom/events/moz.build` |
| `window-screen-origin.patch` | `fingerprint-injection.patch` for `MaskConfig.hpp` in `dom/base/nsGlobalWindowInner.cpp` |
| `zz-stock-cost-parity.patch` | `cross-process-storage.patch` for `RoverfoxStorageManager::Generation()`; `screen-spoofing.patch` for `ScreenDimensionManager` in `dom/base/nsScreen.cpp` |

`zzz-context-locale.patch` applies last and depends on `locale-spoofing.patch`
for the default-locale hook, `navigator-spoofing.patch` for
`NavigatorManager`, `cross-process-storage.patch` for the context store, and
`network-patches.patch` for the request-header path it extends.

## Headless WebGL

`webgl-headless-egl.patch` has no source dependency on `webgl-spoofing.patch`.
It touches only `gfx/gl/GLContextProviderLinux.cpp` and
`gfx/thebes/gfxPlatform.cpp`, and applies in file-name order before the
spoofing patch without sharing either file. The two are one behavioural unit:
EGL creates a real context when `DISPLAY` is unset, and `webgl-spoofing.patch`
makes that context report the identity's GPU. The
`webgl-headless-parity.py` guard fails if either half is missing.

Linux needs Mesa's EGL and DRI drivers at runtime: `libegl1`, `libegl-mesa0`
and `libgl1-mesa-dri` on Debian/Ubuntu, or `mesa-libEGL` and
`mesa-dri-drivers` on Fedora/RHEL. `libxul` dlopens `libEGL.so.1`; without the
stack the browser starts but native-headless WebGL returns `null`. Xvfb is not
needed for native headless.

## RoverfoxStorageManager

Per-context values set from Playwright (WebRTC IP, timezone,
screen, navigator, WebGL, font list, voices, ...) are kept in
`RoverfoxStorageManager`, which `cross-process-storage.patch` adds under
`dom/base/` with its cross-process put/get IPC. Every content process reads it:
a context's documents can land in any of them, and only the first document
calls the setter. The same patch provides the guard and removal every setter
uses (`IsSetterOffered`, `MarkSetterUsed`, `RemoveSetter`), and
`window-setter-seal.patch` adds its seal check to `IsSetterOffered`.

`RoverfoxStorageManager::UserContextId()` is the one way a patch finds the
context a value is stored under: the principal of the node, document or window
at hand. A browsing context is not used, because a document created by
`document.implementation.createHTMLDocument()` or `DOMParser` has none, while it
shares its creator's principal. A value is stored only under its own context;
nothing writes a fallback copy under context 0.

`zzz-context-locale.patch` stores a context's Playwright `locale` as
`nav_locale_<userContextId>`. Worker scripts, shared and service worker
requests, and service workers without a browsing context read that key. The
context's process gets the locale as its default and app locale, covering
isolated worlds, worklets, form widgets and built-in strings.

## Backports

These patches carry upstream Firefox changes that `browser/upstream.sh`'s
version does not have yet. Drop each one when the Firefox it moves to ships
the change.

| Patch | Upstream change |
|-------|-----------------|
| `remote-security-settings.patch` | The startup import of the bundled OneCRL list into certificate storage, from mozilla-firefox's `release` branch ([Bug 2084311](https://bugzilla.mozilla.org/show_bug.cgi?id=2084311)). Firefox 158.0.1 ships the matching `security-state/onecrl.json` dump. Camoufox turns Remote Settings off, so without the import a fresh profile has no revocations. |

## Playwright

Everything else is written against a tree that already has
`playwright/0-playwright.patch` and `playwright/1-leak-fixes.patch` applied.

`proxy-auth-isolation.patch` is paired with Juggler's proxy routing in
`additions/juggler/NetworkObserver.js` and `additions/juggler/TargetRegistry.js`.
The C++ patch keys proxy credentials by the channel's context; Juggler must route
that channel through its context's proxy and must not globally clear the auth
cache while other contexts are authenticating. `TargetRegistry.setProxy()` clears
`clear-origin-attributes-data` only for its own `userContextId` when replacing an
existing proxy.

`NetworkObserver.js` also constructs SOCKS and SOCKS4 proxies with
`nsIProtocolProxyService.newProxyInfoWithAuth`. Playwright rejects SOCKS5
credentials before Juggler receives a proxy, so the launchers remove them from
the Playwright proxy and export an endpoint-keyed `CAMOU_PROXY_CREDENTIALS`
map: `{"host:port": {"username": "...", "password": "..."}}`. They also
normalize Playwright's unrecognized `socks5h` scheme to `socks5`; Juggler sets
`TRANSPARENT_PROXY_RESOLVES_HOST`, so both resolve names at the proxy. Invalid
credential data or proxy construction produces an unusable proxy result instead
of returning `defaultProxyInfo`: Gecko resumes its filter chain with the default
when a channel filter throws, which would be a direct connection.
