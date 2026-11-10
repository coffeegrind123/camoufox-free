#!/usr/bin/env python3
"""Bundle uBlock Origin, the default addon, into a build.

Every package carries AMO's newest uBO release as an extracted addon under
addons/UBO/ (Contents/Resources/addons/UBO/ on macOS), which both launchers load
from beside the binary. So the uBO a user runs, and the filter lists it blocks
with, is the one the release was tested with, and a new uBO release reaches users with
the next browser release without anyone bumping a pin.

The bundled copy keeps its packaged filter lists (freeze_lists), by editing
three defaults in uBO's own source:

- autoUpdate is false. Every launch is a fresh profile, and uBO's own default
  downloads every list from its CDNs within a minute of each launch, which a
  long-lived install does not.
- A first run selects only the lists uBO enables by default, which are the ones
  its package carries. uBO would also select regional lists for the browser's
  locale and download them before pages load.
- suspendUntilListsAreLoaded is false: requests are not held while uBO compiles
  its lists on a fresh profile (1-45 s), which a page could time.

A policy cannot set these: any policies.json puts Firefox in enterprise mode,
which pages and the network can tell (DNS over HTTPS stands down, for one).

A fresh profile also starts uBO the way a fresh install does: it compiles every
list before it filters, 10-25 s in which its blocking webRequest listener
answers nothing, so every request a page makes stalls (8-21 s measured), where a
warm install loads its saved engine (its "selfie") in 1-3 s. So the bundled
copy carries that selfie (seed_layer, `seed`): a build generates it once with
its own browser, and on a profile's first run uBO reads it from the package
wherever its storage has nothing, then saves it, as it would its own.

The release is pinned in data/ubo.json (version, AMO URL, sha256), so a new uBO
reaches the browser only as a reviewed commit. uBO's code runs in every page
and can change what a page observes: 1.76.0 moved RegExp in the global order
of every tab after the first (main-world-eval-globals.py), where stock and
1.75.4 keep it in place. A release hands the same pin to its tests and to every
build through CAMOUFOX_UBO; without it, `stage` uses data/ubo.json.

    scripts/fetch-ubo.py resolve      # print the committed pin (JSON); `pin` step output
    scripts/fetch-ubo.py newest       # print AMO's newest release as a pin, to review a bump
    scripts/fetch-ubo.py stage DIR    # extract the pinned release into DIR/addons/UBO/
    scripts/fetch-ubo.py seed BINARY  # generate the selfie with that build (Linux; needs the camoufox package)
    scripts/fetch-ubo.py inject ZIP SEED  # add a generated seed to a packaged release
"""
import argparse, hashlib, io, json, os, shutil, sys, tempfile, time, urllib.request, zipfile

# Each (file, uBO's own line, our line): userSettingsDefault.autoUpdate and
# hiddenSettingsDefault.suspendUntilListsAreLoaded in js/background.js, and the
# regional branch of autoSelectRegionalFilterLists in js/storage.js.
FROZEN_DEFAULTS = (
    (
        os.path.join("js", "background.js"),
        "    autoUpdate: true,\n",
        "    autoUpdate: false,\n",
    ),
    (
        os.path.join("js", "background.js"),
        "    suspendUntilListsAreLoaded: vAPI.Net.canSuspend(),\n",
        "    suspendUntilListsAreLoaded: false,\n",
    ),
    (
        os.path.join("js", "storage.js"),
        "        if ( this.listMatchesEnvironment(list) ) {\n",
        "        if ( false && this.listMatchesEnvironment(list) ) {\n",
    ),
)

# The selfie a profile's first run reads: index.json and one file per storage
# key, so the extension reads only the keys uBO asks for, as text, never one
# 50 MB JSON document.
SEED_DIR = "camoufox-seed"

# js/cachestorage.js: a last layer under uBO's own two (its IndexedDB cache and
# storage.local). It answers only on a first run (start.js sets the flag where
# uBO handles a first install), and serves the engine selfie only for the list
# selection it was made from. What it served is saved to storage.local once uBO
# would have saved its own selfie, so a kept profile's next launch reads it from
# storage like any warm install.
SEED_LAYER = """\
    // camoufox: the selfie bundled with this build (camoufox-seed/), for a
    // profile's first run, so uBO starts like a warm install rather than
    // compiling every list while its webRequest listener holds each request.
    const seed = (( ) => {
        const base = '/camoufox-seed/';
        const served = new Map();
        let index;
        const readIndex = ( ) => {
            if ( index === undefined ) {
                index = fetch(`${base}index.json`).then(r => r.json()).catch(reason => {
                    ubolog(`camoufox seed: ${reason}`);
                    return null;
                });
            }
            return index;
        };
        const sameSelection = (a, b) => Array.isArray(a) && Array.isArray(b) &&
            a.length === b.length && a.every(k => b.includes(k));
        // uBO reads a cache entry only if its asset registry names it, and a
        // session that compiled nothing may never save its registry: the
        // stored one gets the seed's entries it lacks.
        const persist = async ( ) => {
            const entries = Object.fromEntries(served);
            served.clear();
            if ( µb.selfieIsInvalid || Object.keys(entries).length === 0 ) { return; }
            try {
                const idx = await readIndex();
                const bin = await api.get('assetCacheRegistry');
                const registry = Object.assign(
                    structuredClone(idx.registry),
                    bin && bin.assetCacheRegistry
                );
                await extensionStorage.set(entries);
                await api.set({ assetCacheRegistry: registry });
            } catch (reason) {
                ubolog(`camoufox seed: ${reason}`);
            }
        };
        const readOne = async (idx, key) => {
            if ( key === 'assetCacheRegistry' ) {
                return structuredClone(idx.registry);
            }
            if ( Object.hasOwn(idx.files, key) === false ) { return; }
            if (
                key.startsWith('cache/selfie/static') &&
                sameSelection(µb.selectedFilterLists, idx.selectedFilterLists) === false
            ) {
                return;
            }
            const text = await fetch(base + idx.files[key]).then(r => r.text()).catch(reason => {
                ubolog(`camoufox seed: ${reason}`);
            });
            if ( typeof text !== 'string' || text === '' ) { return; }
            if ( served.size === 0 ) {
                vAPI.defer.once(µb.hiddenSettings.selfieDelayInSeconds * 1000).then(persist);
            }
            served.set(key, text);
            return text;
        };
        return {
            name: 'camoufoxSeed',
            async get(keys) {
                const out = {};
                if ( µb.camoufoxSeed !== true ) { return out; }
                const idx = await readIndex();
                if ( idx === null ) { return out; }
                await Promise.all(keys.map(async key => {
                    const value = await readOne(idx, key);
                    if ( value !== undefined ) { out[key] = value; }
                }));
                return out;
            },
        };
    })();

"""

SEED_EDITS = (
    (
        os.path.join("js", "start.js"),
        "    if ( lastVersionInt === 0 ) {\n        vAPI.net.unsuspend({ all: true, discard: true });\n",
        "    if ( lastVersionInt === 0 ) {\n        µb.camoufoxSeed = true;\n"
        "        vAPI.net.unsuspend({ all: true, discard: true });\n",
    ),
    (
        os.path.join("js", "cachestorage.js"),
        "    const api = {\n        get(argbin) {\n",
        SEED_LAYER + "    const api = {\n        get(argbin) {\n",
    ),
    (
        os.path.join("js", "cachestorage.js"),
        "                return exGet(extensionStorage, wanted, outbin);\n            }).then(wanted => {\n",
        "                return exGet(extensionStorage, wanted, outbin);\n            }).then(wanted => {\n"
        "                if ( wanted === undefined ) { return; }\n"
        "                return exGet(seed, wanted, outbin);\n            }).then(wanted => {\n",
    ),
)

# What a seed must hold: the engine selfie (staticMain lists the lists it was
# compiled from), the PSL and redirect-resource selfies uBO also reads at start,
# and the two format numbers uBO checks before trusting any of them.
SEED_KEYS = (
    "cache/selfie/staticMain",
    "cache/selfie/staticExtFilteringEngine",
    "cache/selfie/staticNetFilteringEngine",
    "cache/selfie/public_suffix_list.dat",
    "cache/selfie/redirectEngine/resources",
    "compiledMagic",
    "selfieMagic",
)

# Added to start.js of a throwaway copy only, by `seed`: once uBO is ready it
# saves its selfie and posts what it stored, with the list selection and its
# asset registry (deserialized; uBO only reads a cache entry the registry names).
SEED_HOOK_ANCHOR = "µb.isReadyResolve();\n"
SEED_HOOK = """
(async ( ) => {
    await µb.selfieManager.create();
    const stored = await browser.storage.local.get(null);
    const { assetCacheRegistry } = await cacheStorage.get('assetCacheRegistry');
    await fetch(SINK, {
        method: 'POST',
        body: JSON.stringify({
            version: vAPI.app.version,
            selectedFilterLists: µb.selectedFilterLists,
            registry: assetCacheRegistry,
            stored,
        }),
    });
})();
"""
SEED_TIMEOUT_S = 300

AMO_ADDON = "https://addons.mozilla.org/api/v5/addons/addon/ublock-origin/"
PIN_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "ubo.json")
GUID = "uBlock0@raymondhill.net"
ADDON_DIR = os.path.join("addons", "UBO")


def get(url, timeout):
    """GET with retries: a CDN hiccup should not fail a release."""
    for attempt in range(4):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "camoufox-build"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
                return resp.read()
        except OSError as e:
            if attempt == 3:
                raise
            print(f"{url}: {e}; retrying", file=sys.stderr)
            time.sleep(5 * (attempt + 1))


def pin_from_amo(addon):
    """The pin for an AMO addon record's current release."""
    if addon["guid"] != GUID:
        raise SystemExit(f"{AMO_ADDON} is {addon['guid']}, not {GUID}")
    version = addon["current_version"]
    algorithm, _, digest = version["file"]["hash"].partition(":")
    if algorithm != "sha256":
        raise SystemExit(f"AMO hashes uBlock Origin {version['version']} with {algorithm}, not sha256")
    return {"version": version["version"], "url": version["file"]["url"], "sha256": digest}


def check_pin(pin, source):
    missing = {"version", "url", "sha256"} - pin.keys()
    if missing:
        raise SystemExit(f"{source} lacks {sorted(missing)}: {pin}")
    if not pin["url"].startswith("https://addons.mozilla.org/"):
        raise SystemExit(f"{source}: {pin['url']} is not an AMO download")
    return pin


def resolve():
    """The committed pin (data/ubo.json). No network: a uBO release on AMO
    changes nothing until someone measures it and commits the bump."""
    with open(PIN_FILE, encoding="utf-8") as f:
        return check_pin(json.load(f), PIN_FILE)


def newest():
    """AMO's newest release as a pin, the candidate for a reviewed bump."""
    return pin_from_amo(json.loads(get(AMO_ADDON, 30)))


def pin_from_env():
    """CAMOUFOX_UBO, the pin a release resolved once; None when unset."""
    raw = os.environ.get("CAMOUFOX_UBO", "").strip()
    if not raw:
        return None
    return check_pin(json.loads(raw), "CAMOUFOX_UBO")


def freeze_lists(addon_dir):
    """Edit the extracted uBO's defaults (FROZEN_DEFAULTS) so it keeps its
    packaged lists. Fails if uBO's source no longer has a line this edits,
    rather than shipping a uBO that downloads lists or holds requests."""
    edit_source(addon_dir, FROZEN_DEFAULTS, "FROZEN_DEFAULTS")


def seed_layer(addon_dir):
    """Edit the extracted uBO so a first run reads the bundled selfie
    (SEED_EDITS). Fails if uBO's source no longer has a line this edits,
    rather than shipping a seed nothing reads."""
    edit_source(addon_dir, SEED_EDITS, "SEED_EDITS")


def edit_source(addon_dir, edits, name):
    for rel, stock, ours in edits:
        path = os.path.join(addon_dir, rel)
        with open(path, encoding="utf-8") as f:
            source = f.read()
        if source.count(stock) != 1:
            first = stock.strip().splitlines()[0]
            raise SystemExit(f"{path}: expected one {first!r}; uBO changed, update {name}")
        with open(path, "w", encoding="utf-8") as f:
            f.write(source.replace(stock, ours))


def world_readable(root):
    """Set dirs 755 and files 644 under root, root included.

    mkdtemp makes root 0700, and os.replace keeps that mode, so without this
    addons/UBO is readable only by the build's user. A launcher running as
    anyone else (a Docker image's app user) then finds no addon and starts
    without uBO.
    """
    os.chmod(root, 0o755)
    for dirpath, dirs, files in os.walk(root):
        for name in dirs:
            os.chmod(os.path.join(dirpath, name), 0o755)
        for name in files:
            os.chmod(os.path.join(dirpath, name), 0o644)


def extract(xpi, pin, dest):
    """Unpack a verified XPI into dest, replacing whatever was there."""
    digest = hashlib.sha256(xpi).hexdigest()
    if digest != pin["sha256"]:
        raise SystemExit(f"uBlock Origin {pin['version']} from {pin['url']} has sha256 {digest}, "
                         f"expected {pin['sha256']}")
    with zipfile.ZipFile(io.BytesIO(xpi)) as z:
        manifest = json.loads(z.read("manifest.json"))
        gecko = manifest.get("browser_specific_settings", {}).get("gecko", {})
        if gecko.get("id") != GUID or manifest.get("version") != pin["version"]:
            raise SystemExit(f"{pin['url']} is {gecko.get('id')} {manifest.get('version')}, "
                             f"not {GUID} {pin['version']}")
        names = z.namelist()
        bad = [n for n in names if n.startswith("/") or ".." in n.split("/")]
        if bad:
            raise SystemExit(f"{pin['url']} has paths outside the addon: {bad[:5]}")
        # Into a sibling, then renamed into place, so an interrupted run never
        # leaves a manifest.json beside a half-written addon.
        parent = os.path.dirname(dest)
        os.makedirs(parent, exist_ok=True)
        tmp = tempfile.mkdtemp(prefix=".UBO.tmp-", dir=parent)
        try:
            z.extractall(tmp)
            freeze_lists(tmp)
            seed_layer(tmp)
            world_readable(tmp)
            shutil.rmtree(dest, ignore_errors=True)
            os.replace(tmp, dest)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


def stage(directory):
    pin = pin_from_env() or resolve()
    dest = os.path.join(directory, ADDON_DIR)
    extract(get(pin["url"], 120), pin, dest)
    print(f"uBlock Origin {pin['version']} -> {dest}")


def seed_from_dump(dump):
    """The seed (index, {file name: text}) for what the hooked uBO posted.
    Fails on a dump missing anything a first run needs, rather than shipping
    a seed uBO would reject and compile anyway."""
    stored, registry = dump["stored"], dump["registry"]
    missing = [k for k in SEED_KEYS if not isinstance(stored.get(k), str) or not stored[k]]
    unregistered = [k for k in SEED_KEYS if k.startswith("cache/") and k[len("cache/"):] not in registry]
    if missing or unregistered:
        raise SystemExit(f"uBO {dump['version']} stored no {missing} / registered no {unregistered}: "
                         "its selfie format changed, update SEED_KEYS")
    selection = dump["selectedFilterLists"]
    if not selection or not isinstance(selection, list):
        raise SystemExit(f"uBO {dump['version']} selected no filter lists: {selection!r}")
    files = {key: f"{n}.txt" for n, key in enumerate(SEED_KEYS)}
    index = {
        "ubo": dump["version"],
        "selectedFilterLists": selection,
        "registry": {k: registry[k] for k in registry if "cache/" + k in files},
        "files": files,
    }
    return index, {files[key]: stored[key] for key in SEED_KEYS}


def write_seed(parent, index, texts):
    """Write the seed into parent/SEED_DIR, replacing any, readable by all."""
    dest = os.path.join(parent, SEED_DIR)
    shutil.rmtree(dest, ignore_errors=True)
    os.makedirs(dest)
    with open(os.path.join(dest, "index.json"), "w", encoding="utf-8") as f:
        json.dump(index, f, separators=(",", ":"))
    for name, text in texts.items():
        with open(os.path.join(dest, name), "w", encoding="utf-8", newline="") as f:
            f.write(text)
    world_readable(dest)
    return dest


def addon_version(addon_dir):
    with open(os.path.join(addon_dir, "manifest.json"), encoding="utf-8") as f:
        return json.load(f)["version"]


def hooked_copy(addon_dir, dest, sink):
    """A copy of the bundled uBO that posts its selfie to sink once ready."""
    shutil.copytree(addon_dir, dest, ignore=shutil.ignore_patterns(SEED_DIR))
    path = os.path.join(dest, "js", "start.js")
    with open(path, encoding="utf-8") as f:
        source = f.read()
    if source.count(SEED_HOOK_ANCHOR) != 1:
        raise SystemExit(f"{path}: expected one {SEED_HOOK_ANCHOR.strip()!r}; uBO changed, update SEED_HOOK")
    hook = SEED_HOOK.replace("SINK", json.dumps(sink))
    with open(path, "w", encoding="utf-8") as f:
        f.write(source.replace(SEED_HOOK_ANCHOR, SEED_HOOK_ANCHOR + hook))


def seed(binary, out=None):
    """Generate the bundled uBO's selfie with the build at binary, and write it
    beside that uBO, or into out (a user that can run the build but not write
    to it; `inject` then adds it to the package).

    The build's own browser runs a throwaway copy of its uBO on a fresh
    profile, with no seed, so it compiles its packaged lists as a first run
    does, then saves its selfie and posts it here. What uBO compiles depends on
    its own version and on what it detects of the browser (Firefox, :has()
    support), never on the OS, so one seed serves every platform's package.
    """
    import http.server, queue, threading  # noqa: E401 - only this command serves

    from camoufox.addons import DefaultAddons, get_addon_path
    from camoufox.sync_api import Camoufox

    addon = get_addon_path(DefaultAddons.UBO.name, binary)
    with open(os.path.join(addon, "js", "cachestorage.js"), encoding="utf-8") as f:
        if "const seed = (( ) => {" not in f.read():
            raise SystemExit(f"{addon} has no seed layer: stage it with this script first")

    posts = queue.Queue()

    class Sink(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_POST(self):
            posts.put(self.rfile.read(int(self.headers.get("Content-Length", 0))))
            self.send_response(204)
            self.end_headers()

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Sink)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    tmp = tempfile.mkdtemp(prefix="ubo-seed-")
    try:
        copy = os.path.join(tmp, "UBO")
        hooked_copy(addon, copy, f"http://127.0.0.1:{srv.server_address[1]}/")
        started = time.monotonic()
        with Camoufox(headless=True, executable_path=str(binary), i_know_what_im_doing=True, geoip=False,
                      addons=[copy], exclude_addons=[DefaultAddons.UBO]) as browser:
            browser.new_page()
            try:
                dump = json.loads(posts.get(timeout=SEED_TIMEOUT_S))
            except queue.Empty:
                raise SystemExit(f"uBO posted no selfie within {SEED_TIMEOUT_S}s") from None
    finally:
        srv.shutdown()
        shutil.rmtree(tmp, ignore_errors=True)

    if dump["version"] != addon_version(addon):
        raise SystemExit(f"the hooked uBO is {dump['version']}, the bundled one {addon_version(addon)}")
    index, texts = seed_from_dump(dump)
    dest = write_seed(out or addon, index, texts)
    size = sum(len(t.encode("utf-8")) for t in texts.values())
    print(f"uBlock Origin {index['ubo']} selfie ({len(index['selectedFilterLists'])} lists, "
          f"{size / 1e6:.1f} MB) after {time.monotonic() - started:.0f}s -> {dest}")


def inject(zip_path, seed_dir):
    """Add a generated seed to a packaged release, beside its uBO.

    Each platform's release is built on its own runner and only Linux can run
    its browser, so the Linux build generates the seed and the release adds it
    to every package. Fails unless the package bundles exactly one uBO, of the
    version the seed was made from, with no seed yet.
    """
    with open(os.path.join(seed_dir, "index.json"), encoding="utf-8") as f:
        index = json.load(f)
    names = ["index.json", *sorted(set(index["files"].values()))]
    with zipfile.ZipFile(zip_path) as z:
        manifests = [n for n in z.namelist() if n == "addons/UBO/manifest.json"
                     or n.endswith("/addons/UBO/manifest.json")]
        if len(manifests) != 1:
            raise SystemExit(f"{zip_path}: expected one addons/UBO/manifest.json, found {manifests}")
        prefix = manifests[0][: -len("manifest.json")] + SEED_DIR + "/"
        if any(n.startswith(prefix) for n in z.namelist()):
            raise SystemExit(f"{zip_path} already has {prefix}")
        version = json.loads(z.read(manifests[0]))["version"]
    if version != index["ubo"]:
        raise SystemExit(f"{zip_path} bundles uBO {version}, the seed is for {index['ubo']}")
    with zipfile.ZipFile(zip_path, "a", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        folder = zipfile.ZipInfo(prefix, date_time=time.localtime()[:6])
        folder.external_attr = (0o040755 << 16) | 0x10
        z.writestr(folder, b"")
        for name in names:
            info = zipfile.ZipInfo(prefix + name, date_time=time.localtime()[:6])
            info.external_attr = 0o100644 << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            with open(os.path.join(seed_dir, name), "rb") as f:
                z.writestr(info, f.read())
    print(f"{zip_path}: + {prefix} ({len(names)} files)")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("resolve")
    sub.add_parser("newest")
    p = sub.add_parser("stage")
    p.add_argument("directory", help="the build directory the launchers find files in (beside camoufox-bin)")
    p = sub.add_parser("seed")
    p.add_argument("binary", help="camoufox-bin of a build whose addons/UBO this script staged")
    p.add_argument("--out", help=f"write {SEED_DIR}/ here instead of beside the build's uBO")
    p = sub.add_parser("inject")
    p.add_argument("zip", help="a packaged release")
    p.add_argument("seed", help=f"a {SEED_DIR}/ directory `seed` wrote")
    args = parser.parse_args()
    if args.cmd == "resolve":
        pin = json.dumps(resolve(), separators=(",", ":"))
        print(pin)
        if os.environ.get("GITHUB_OUTPUT"):
            with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as fh:
                fh.write(f"pin={pin}\n")
    elif args.cmd == "newest":
        print(json.dumps(newest(), separators=(",", ":")))
    elif args.cmd == "seed":
        seed(args.binary, args.out)
    elif args.cmd == "inject":
        inject(args.zip, args.seed)
    else:
        stage(args.directory)


if __name__ == "__main__":
    main()
