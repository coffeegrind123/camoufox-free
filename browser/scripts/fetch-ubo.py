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

The release is pinned in data/ubo.json (version, AMO URL, sha256), so a new uBO
reaches the browser only as a reviewed commit. uBO's code runs in every page
and can change what a page observes: 1.76.0 moved RegExp in the global order
of every tab after the first (main-world-eval-globals.py), where stock and
1.75.4 keep it in place. A release hands the same pin to its tests and to every
build through CAMOUFOX_UBO; without it, `stage` uses data/ubo.json.

    scripts/fetch-ubo.py resolve      # print the committed pin (JSON); `pin` step output
    scripts/fetch-ubo.py newest       # print AMO's newest release as a pin, to review a bump
    scripts/fetch-ubo.py stage DIR    # extract the pinned release into DIR/addons/UBO/
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
    for rel, stock, frozen in FROZEN_DEFAULTS:
        path = os.path.join(addon_dir, rel)
        with open(path, encoding="utf-8") as f:
            source = f.read()
        if source.count(stock) != 1:
            raise SystemExit(f"{path}: expected one {stock.strip()!r}; "
                             "uBO changed, update FROZEN_DEFAULTS")
        with open(path, "w", encoding="utf-8") as f:
            f.write(source.replace(stock, frozen))


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


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("resolve")
    sub.add_parser("newest")
    p = sub.add_parser("stage")
    p.add_argument("directory", help="the build directory the launchers find files in (beside camoufox-bin)")
    args = parser.parse_args()
    if args.cmd == "resolve":
        pin = json.dumps(resolve(), separators=(",", ":"))
        print(pin)
        if os.environ.get("GITHUB_OUTPUT"):
            with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as fh:
                fh.write(f"pin={pin}\n")
    elif args.cmd == "newest":
        print(json.dumps(newest(), separators=(",", ":")))
    else:
        stage(args.directory)


if __name__ == "__main__":
    main()
