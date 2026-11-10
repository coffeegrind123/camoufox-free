"""browser/scripts/fetch-ubo.py: every package bundles the uBlock Origin release
committed in browser/scripts/data/ubo.json, checked, and a release bundles the one
its tests ran with. AMO's newest is only a candidate for a reviewed bump."""

import hashlib
import importlib.util
import io
import json
import re
import zipfile
from pathlib import Path

import pytest
import yaml

from ci._util import BROWSER_ROOT, REPO_ROOT

spec = importlib.util.spec_from_file_location("fetch_ubo", BROWSER_ROOT / "scripts" / "fetch-ubo.py")
fetch_ubo = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fetch_ubo)

GUID = "uBlock0@raymondhill.net"


# The lines freeze_lists edits, as uBO's own source has them (gorhill/uBlock
# src/js/background.js and src/js/storage.js).
UBO_BACKGROUND = (
    "const hiddenSettingsDefault = {\n"
    "    suspendUntilListsAreLoaded: vAPI.Net.canSuspend(),\n"
    "};\n"
    "const userSettingsDefault = {\n"
    "    autoUpdate: true,\n"
    "};\n"
)
UBO_STORAGE = (
    "µb.autoSelectRegionalFilterLists = function(lists) {\n"
    "    for ( const key in lists ) {\n"
    "        if ( list.off !== true ) {\n"
    "            selectedListKeys.push(key);\n"
    "            continue;\n"
    "        }\n"
    "        if ( this.listMatchesEnvironment(list) ) {\n"
    "            selectedListKeys.push(key);\n"
    "            list.off = false;\n"
    "        }\n"
    "    }\n"
    "};\n"
)

# The lines seed_layer edits (gorhill/uBlock src/js/start.js and
# src/js/cachestorage.js).
UBO_START = (
    "const onVersionReady = async lastVersion => {\n"
    "    if ( lastVersionInt === 0 ) {\n"
    "        vAPI.net.unsuspend({ all: true, discard: true });\n"
    "        return;\n"
    "    }\n"
    "};\n"
    "µb.isReadyResolve();\n"
)
UBO_CACHESTORAGE = (
    "const cacheStorage = (( ) => {\n"
    "    const api = {\n"
    "        get(argbin) {\n"
    "            return exGet(cacheAPIs[fastCache], keysFromGetArg(argbin), outbin).then(wanted => {\n"
    "                if ( wanted === undefined ) { return; }\n"
    "                return exGet(extensionStorage, wanted, outbin);\n"
    "            }).then(wanted => {\n"
    "                if ( wanted === undefined ) { return; }\n"
    "            });\n"
    "        },\n"
    "    };\n"
    "})();\n"
)
SOURCES = {
    "background.js": UBO_BACKGROUND,
    "storage.js": UBO_STORAGE,
    "start.js": UBO_START,
    "cachestorage.js": UBO_CACHESTORAGE,
}


def xpi(version="1.76.0", guid=GUID, extra=()):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("manifest.json", json.dumps(
            {"version": version, "browser_specific_settings": {"gecko": {"id": guid}}}))
        for name, text in SOURCES.items():
            z.writestr(f"js/{name}", text)
        for name in extra:
            z.writestr(name, "")
    return buf.getvalue()


def amo(data, version="1.76.0", guid=GUID, algorithm="sha256"):
    digest = hashlib.sha256(data).hexdigest()
    return {"guid": guid, "current_version": {"version": version, "file": {
        "url": f"https://addons.mozilla.org/firefox/downloads/file/1/ublock_origin-{version}.xpi",
        "hash": f"{algorithm}:{digest}"}}}


def test_the_pin_is_amo_s_current_release():
    data = xpi()
    pin = fetch_ubo.pin_from_amo(amo(data))
    assert pin == {"version": "1.76.0", "sha256": hashlib.sha256(data).hexdigest(),
                   "url": "https://addons.mozilla.org/firefox/downloads/file/1/ublock_origin-1.76.0.xpi"}


def test_resolve_is_the_committed_pin_and_needs_no_network(monkeypatch):
    monkeypatch.setattr(fetch_ubo, "get", lambda url, timeout: pytest.fail(f"resolve fetched {url}"))
    pin = fetch_ubo.resolve()
    committed = json.loads((BROWSER_ROOT / "scripts" / "data" / "ubo.json").read_text())
    assert pin == committed
    assert re.fullmatch(r"[0-9a-f]{64}", pin["sha256"])
    assert pin["url"].startswith("https://addons.mozilla.org/")


def test_stage_without_a_release_pin_uses_the_committed_one(tmp_path, monkeypatch):
    data = xpi(version="1.75.4")
    pin = {"version": "1.75.4", "sha256": hashlib.sha256(data).hexdigest(),
           "url": "https://addons.mozilla.org/firefox/downloads/file/1/ublock_origin-1.75.4.xpi"}
    monkeypatch.delenv("CAMOUFOX_UBO", raising=False)
    monkeypatch.setattr(fetch_ubo, "resolve", lambda: pin)
    monkeypatch.setattr(fetch_ubo, "newest", lambda: pytest.fail("a build must not take AMO's newest"))
    monkeypatch.setattr(fetch_ubo, "get", lambda url, timeout: data if url == pin["url"] else pytest.fail(url))
    fetch_ubo.stage(str(tmp_path))
    assert json.loads((tmp_path / "addons" / "UBO" / "manifest.json").read_text())["version"] == "1.75.4"


def test_newest_reads_amo(monkeypatch):
    data = xpi()
    monkeypatch.setattr(fetch_ubo, "get", lambda url, timeout: json.dumps(amo(data)).encode()
                        if url == fetch_ubo.AMO_ADDON else pytest.fail(url))
    assert fetch_ubo.newest()["version"] == "1.76.0"


@pytest.mark.parametrize("pin", [{"version": "1", "url": "https://addons.mozilla.org/x.xpi"},
                                 {"version": "1", "sha256": "0" * 64, "url": "https://example.com/x.xpi"}])
def test_an_incomplete_or_foreign_pin_is_refused(pin):
    with pytest.raises(SystemExit):
        fetch_ubo.check_pin(pin, "test")


@pytest.mark.parametrize("record", [amo(b"", guid="evil@example.com"), amo(b"", algorithm="sha1")])
def test_another_addon_or_a_weaker_hash_is_refused(record):
    with pytest.raises(SystemExit):
        fetch_ubo.pin_from_amo(record)


def test_stage_extracts_the_pinned_release_beside_the_binary(tmp_path, monkeypatch):
    data = xpi()
    pin = fetch_ubo.pin_from_amo(amo(data))
    monkeypatch.setenv("CAMOUFOX_UBO", json.dumps(pin))
    monkeypatch.setattr(fetch_ubo, "resolve", lambda: pytest.fail("a release's pin must not be re-resolved"))
    monkeypatch.setattr(fetch_ubo, "get", lambda url, timeout: data if url == pin["url"] else pytest.fail(url))
    (tmp_path / "addons" / "UBO").mkdir(parents=True)
    (tmp_path / "addons" / "UBO" / "stale.js").write_text("")
    fetch_ubo.stage(str(tmp_path))
    ubo = tmp_path / "addons" / "UBO"
    assert json.loads((ubo / "manifest.json").read_text())["version"] == "1.76.0"
    assert sorted(p.name for p in ubo.iterdir()) == ["js", "manifest.json"], "the previous copy is replaced"
    # Its filter lists stay the packaged ones: uBO's own default downloads them
    # within a minute of every launch.
    assert "    autoUpdate: false,\n" in (ubo / "js" / "background.js").read_text()
    assert [p.name for p in (tmp_path / "addons").iterdir()] == ["UBO"], "no staging directory is left"


@pytest.mark.parametrize("data, pin_data, why", [
    (xpi(), xpi(version="1.76.1"), "sha256"),
    (xpi(guid="evil@example.com"), None, "not uBlock0"),
    (xpi(version="1.75.0"), None, "not uBlock0"),
    (xpi(extra=["../escape"]), None, "outside the addon"),
])
def test_a_download_that_is_not_the_pinned_release_is_refused(tmp_path, data, pin_data, why):
    pin = {"version": "1.76.0", "url": "u", "sha256": hashlib.sha256(pin_data or data).hexdigest()}
    with pytest.raises(SystemExit, match=why):
        fetch_ubo.extract(data, pin, str(tmp_path / "addons" / "UBO"))
    assert not (tmp_path / "addons" / "UBO").exists()


def test_packaging_bundles_it_where_the_launchers_look():
    package = (BROWSER_ROOT / "scripts" / "package.py").read_text(encoding="utf-8")
    assert "'fetch-ubo.py'), 'stage', target_dir" in package
    assert fetch_ubo.ADDON_DIR.replace("\\", "/") == "addons/UBO"


def test_bundled_ubo_keeps_its_packaged_lists_without_a_policy(tmp_path):
    """No policies.json (it puts Firefox in enterprise mode), so the bundled
    uBO's own defaults are edited: no list downloads, no request held while
    lists compile, and a first run selects only the lists uBO enables by
    default, which its package carries, never a regional one for the locale
    (camoufox-free#211)."""
    data = xpi()
    pin = {"version": "1.76.0", "url": "u", "sha256": hashlib.sha256(data).hexdigest()}
    ubo = tmp_path / "addons" / "UBO"
    fetch_ubo.extract(data, pin, str(ubo))
    background = (ubo / "js" / "background.js").read_text(encoding="utf-8")
    storage = (ubo / "js" / "storage.js").read_text(encoding="utf-8")

    assert "    autoUpdate: false,\n" in background
    assert "autoUpdate: true" not in background
    assert "    suspendUntilListsAreLoaded: false,\n" in background
    assert "vAPI.Net.canSuspend()" not in background
    # The regional branch can no longer select a list; the default-on branch is untouched.
    assert "        if ( this.listMatchesEnvironment(list) ) {\n" not in storage
    assert "        if ( false && this.listMatchesEnvironment(list) ) {\n" in storage
    assert "        if ( list.off !== true ) {\n            selectedListKeys.push(key);" in storage
    assert not (BROWSER_ROOT / "settings" / "distribution" / "policies.json").exists()


def test_a_release_bundles_the_ubo_its_tests_ran_with():
    """One resolve per build, handed to the package and the release notes."""
    workflows = REPO_ROOT / ".github" / "workflows"
    jobs = yaml.safe_load((workflows / "build.yml").read_text(encoding="utf-8"))["jobs"]
    pin = "${{ needs.ubo.outputs.pin }}"
    assert jobs["ubo"]["outputs"]["pin"] == "${{ steps.resolve.outputs.pin }}"
    assert any("fetch-ubo.py resolve" in s.get("run", "") for s in jobs["ubo"]["steps"])
    assert set(jobs["build"]["needs"]) == {"verify", "ubo"}
    assert jobs["build"]["env"]["CAMOUFOX_UBO"] == pin
    assert set(jobs["release"]["needs"]) == {"build", "ubo"}
    describe = next(s for s in jobs["release"]["steps"] if s.get("name") == "Name the bundled uBlock Origin")
    assert describe["env"]["UBO"] == pin

    tests = yaml.safe_load((workflows / "tests.yml").read_text(encoding="utf-8"))
    call = tests[True]["workflow_call"]["inputs"]  # PyYAML reads the `on:` key as True
    assert "ubo" in call
    resolve = tests["jobs"]["resolve"]
    assert resolve["outputs"]["ubo"] == "${{ steps.ubo.outputs.pin }}"
    step = next(s for s in resolve["steps"] if s.get("id") == "ubo")
    assert step["env"]["CAMOUFOX_UBO"] == "${{ inputs.ubo }}"
    build = tests["jobs"]["build"]["steps"]
    staged = [s for s in build if "fetch-ubo.py stage" in s.get("run", "")]
    assert len(staged) == 2, "both the built and the restored browser bundle this run's uBO"
    assert all(s["env"]["CAMOUFOX_UBO"] == "${{ needs.resolve.outputs.ubo }}" for s in staged)


def test_the_manifest_names_the_bundled_ubo():
    from ci import release

    pin = {"version": "1.76.0", "url": "u", "sha256": "0" * 64}
    assert release.manifest("v1", "d", "0" * 40, pin)["ubo"] == pin
    assert "ubo" not in release.manifest("v1", "d", "0" * 40)


def test_the_staged_addon_is_readable_by_every_user(tmp_path):
    """The launcher may run as a user that doesn't own the install (a Docker
    image's app user): a 0700 staging dir hid addons/UBO from it, so uBO never
    loaded."""
    data = xpi()
    pin = {"version": "1.76.0", "url": "u", "sha256": hashlib.sha256(data).hexdigest()}
    ubo = tmp_path / "addons" / "UBO"
    fetch_ubo.extract(data, pin, str(ubo))
    for path in [ubo, *ubo.rglob("*")]:
        mode = path.stat().st_mode & 0o777
        want = 0o755 if path.is_dir() else 0o644
        assert mode == want, f"{path.relative_to(tmp_path)} is {oct(mode)}, want {oct(want)}"


def test_duckduckgo_is_the_default_search_engine():
    """URL-bar searches go to DuckDuckGo. Stock's engines stay (no
    no-search-engines.patch, no SearchEngines policy, which would put Firefox in
    enterprise mode); search-default-duckduckgo.patch changes only the
    application default, to the "ddg" engine, where the configuration lists it.
    search-service-init.py checks the running browser against stock."""
    patches = BROWSER_ROOT / "patches"
    assert not (patches / "no-search-engines.patch").exists()
    assert not (BROWSER_ROOT / "settings" / "distribution" / "policies.json").exists()
    patch = (patches / "search-default-duckduckgo.patch").read_text(encoding="utf-8")
    files = re.findall(r"^diff --git a/(\S+)", patch, flags=re.M)
    assert files == ["toolkit/components/search/SearchEngineSelector.sys.mjs"]
    added = [line[1:].strip() for line in patch.splitlines()
             if line.startswith("+") and not line.startswith("+++")]
    code = [line for line in added if line and not line.startswith("//")]
    assert code == [
        'if (refinedSearchConfig.engines.some(e => e.identifier == "ddg")) {',
        'refinedSearchConfig.appDefaultEngineId = "ddg";',
        "}",
    ], "only the default may change: the engines and their order stay stock's"
    assert not [line for line in patch.splitlines() if line.startswith("-") and not line.startswith("---")]
    assert "127.0.0.1" not in patch


@pytest.mark.parametrize("rel, line", [
    ("background.js", "    autoUpdate: true,\n"),
    ("background.js", "    suspendUntilListsAreLoaded: vAPI.Net.canSuspend(),\n"),
    ("storage.js", "        if ( this.listMatchesEnvironment(list) ) {\n"),
])
def test_a_ubo_whose_default_moved_is_refused(tmp_path, rel, line):
    """Shipping a uBO that downloads lists or holds requests is worse than
    failing the build."""
    js = tmp_path / "js"
    js.mkdir()
    for name, text in SOURCES.items():
        (js / name).write_text(text.replace(line, "") if name == rel else text, encoding="utf-8")
    with pytest.raises(SystemExit, match="uBO changed"):
        fetch_ubo.freeze_lists(str(tmp_path))


def staged(tmp_path, version="1.76.0"):
    data = xpi(version=version)
    pin = {"version": version, "url": "u", "sha256": hashlib.sha256(data).hexdigest()}
    ubo = tmp_path / "addons" / "UBO"
    fetch_ubo.extract(data, pin, str(ubo))
    return ubo


def dump(version="1.76.0", **changes):
    stored = {key: f"UOSC_1 {key}" for key in fetch_ubo.SEED_KEYS}
    stored["cache/compiled/easylist"] = "UOSC_1 compiled"
    stored["selectedFilterLists"] = ["user-filters", "easylist"]
    registry = {key[len("cache/"):]: {"readTime": 1, "writeTime": 1, "resourceTime": 0}
                for key in stored if key.startswith("cache/")}
    out = {"version": version, "selectedFilterLists": ["user-filters", "easylist"],
           "registry": registry, "stored": stored}
    out.update(changes)
    return out


def test_a_first_run_reads_the_bundled_selfie_where_storage_has_nothing(tmp_path):
    """A fresh profile is a fresh uBO install: without its selfie it compiles
    every list for 10-25 s while its blocking webRequest listener holds every
    request a page makes. The seed is a last layer under uBO's own storage, on
    a first run only."""
    ubo = staged(tmp_path)
    start = (ubo / "js" / "start.js").read_text(encoding="utf-8")
    cache = (ubo / "js" / "cachestorage.js").read_text(encoding="utf-8")
    assert "    if ( lastVersionInt === 0 ) {\n        µb.camoufoxSeed = true;\n" in start
    assert cache.index("const seed = (( ) => {") < cache.index("    const api = {\n")
    chain = cache[cache.index("        get(argbin) {"):]
    assert chain.index("exGet(cacheAPIs[fastCache]") < chain.index("exGet(extensionStorage") \
        < chain.index("exGet(seed, wanted, outbin)"), "the seed only fills what uBO's storage lacks"
    layer = fetch_ubo.SEED_LAYER
    assert "if ( µb.camoufoxSeed !== true ) { return out; }" in layer
    assert "sameSelection(µb.selectedFilterLists, idx.selectedFilterLists) === false" in layer
    assert "fetch(" in layer and "http" not in layer, "the seed is read from the package only"


@pytest.mark.parametrize("rel, line", [
    ("start.js", "        vAPI.net.unsuspend({ all: true, discard: true });\n"),
    ("cachestorage.js", "    const api = {\n"),
    ("cachestorage.js", "                return exGet(extensionStorage, wanted, outbin);\n"),
])
def test_a_ubo_whose_seed_anchor_moved_is_refused(tmp_path, rel, line):
    js = tmp_path / "js"
    js.mkdir()
    for name, text in SOURCES.items():
        (js / name).write_text(text.replace(line, "") if name == rel else text, encoding="utf-8")
    with pytest.raises(SystemExit, match="uBO changed, update SEED_EDITS"):
        fetch_ubo.seed_layer(str(tmp_path))


def test_a_seed_holds_only_what_a_first_run_reads(tmp_path):
    index, texts = fetch_ubo.seed_from_dump(dump())
    assert index["ubo"] == "1.76.0"
    assert index["selectedFilterLists"] == ["user-filters", "easylist"]
    assert set(index["files"]) == set(fetch_ubo.SEED_KEYS)
    assert sorted(texts) == sorted(index["files"].values())
    assert texts[index["files"]["cache/selfie/staticMain"]] == "UOSC_1 cache/selfie/staticMain"
    # uBO reads a cache entry only if its registry names it; compiled lists stay out.
    assert sorted(index["registry"]) == sorted(k[len("cache/"):] for k in fetch_ubo.SEED_KEYS
                                               if k.startswith("cache/"))

    ubo = staged(tmp_path)
    dest = Path(fetch_ubo.write_seed(str(ubo), index, texts))
    assert json.loads((dest / "index.json").read_text()) == index
    for path in [dest, *dest.iterdir()]:
        assert path.stat().st_mode & 0o777 == (0o755 if path.is_dir() else 0o644)


@pytest.mark.parametrize("change", [
    {"stored": {}},
    {"registry": {}},
    {"selectedFilterLists": []},
])
def test_a_dump_a_first_run_could_not_use_is_refused(change):
    with pytest.raises(SystemExit):
        fetch_ubo.seed_from_dump(dump(**change))


def test_the_generating_copy_posts_its_selfie_and_starts_unseeded(tmp_path):
    ubo = staged(tmp_path)
    (ubo / fetch_ubo.SEED_DIR).mkdir()
    copy = tmp_path / "copy"
    fetch_ubo.hooked_copy(str(ubo), str(copy), "http://127.0.0.1:1/")
    assert not (copy / fetch_ubo.SEED_DIR).exists(), "a stale seed would be posted back as new"
    start = (copy / "js" / "start.js").read_text(encoding="utf-8")
    assert 'await fetch("http://127.0.0.1:1/", {' in start
    assert "await µb.selfieManager.create();" in start
    assert "http" not in (ubo / "js" / "start.js").read_text(encoding="utf-8")


def package(tmp_path, manifest_name, version="1.76.0"):
    path = tmp_path / "camoufox.zip"
    with zipfile.ZipFile(path, "w") as z:
        z.writestr(manifest_name, json.dumps({"version": version}))
        z.writestr("camoufox-bin", "")
    return path


def seed_dir(tmp_path):
    index, texts = fetch_ubo.seed_from_dump(dump())
    ubo = tmp_path / "s" / "UBO"
    ubo.mkdir(parents=True)
    return Path(fetch_ubo.write_seed(str(ubo), index, texts))


@pytest.mark.parametrize("manifest", ["addons/UBO/manifest.json",
                                      "Camoufox.app/Contents/Resources/addons/UBO/manifest.json"])
def test_a_release_carries_the_seed_beside_its_ubo(tmp_path, manifest, monkeypatch):
    monkeypatch.syspath_prepend(str(BROWSER_ROOT / "scripts"))
    spec = importlib.util.spec_from_file_location("camoufox_package", BROWSER_ROOT / "scripts" / "package.py")
    package_py = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(package_py)

    zip_path = package(tmp_path, manifest)
    seed = seed_dir(tmp_path)
    fetch_ubo.inject(str(zip_path), str(seed))
    prefix = manifest[: -len("manifest.json")] + fetch_ubo.SEED_DIR + "/"
    with zipfile.ZipFile(zip_path) as z:
        added = sorted(n[len(prefix):] for n in z.namelist() if n.startswith(prefix) and n != prefix)
        assert added == sorted(p.name for p in seed.iterdir())
        assert z.read(prefix + "index.json") == (seed / "index.json").read_bytes()
    assert [e for e in package_py.unreadable_entries(str(zip_path)) if e.startswith(prefix)] == []


def test_a_release_takes_a_seed_only_for_its_own_ubo(tmp_path):
    seed = seed_dir(tmp_path)
    with pytest.raises(SystemExit, match="seed is for 1.76.0"):
        fetch_ubo.inject(str(package(tmp_path, "addons/UBO/manifest.json", "1.76.1")), str(seed))
    zip_path = package(tmp_path, "addons/UBO/manifest.json")
    fetch_ubo.inject(str(zip_path), str(seed))
    with pytest.raises(SystemExit, match="already has"):
        fetch_ubo.inject(str(zip_path), str(seed))


def test_every_browser_ci_tests_or_ships_carries_the_seed():
    """A uBO staged without its selfie holds every request for 10-25 s at
    launch: tests.yml seeds wherever it stages, and a release seeds its zip
    before the uBO guards check it as shipped."""
    workflows = REPO_ROOT / ".github" / "workflows"
    tests = yaml.safe_load((workflows / "tests.yml").read_text(encoding="utf-8"))
    for job in ("build", "fetch-browser"):
        for step in tests["jobs"][job]["steps"]:
            run = step.get("run", "")
            for line in run.splitlines():
                if "fetch-ubo.py stage" not in line:
                    continue
                target = line.split("fetch-ubo.py stage", 1)[1].split()[0]
                assert f"seed-ubo.sh {target}" in run, f"{job}: {line.strip()} is never seeded"

    build = yaml.safe_load((workflows / "build.yml").read_text(encoding="utf-8"))["jobs"]["build"]["steps"]
    step = next(s for s in build if "fetch-ubo.py seed" in s.get("run", ""))
    run = step["run"]
    assert run.index("fetch-ubo.py seed") < run.index("fetch-ubo.py inject") \
        < run.rindex("unzip -q \"$zip\"") < run.index("ubo-seeded-start.py --binary"), \
        "the guards check the zip after the seed went in"
    assert "ubo-lists-frozen.py --binary" in run
    seed_sh = (BROWSER_ROOT / "scripts" / "seed-ubo.sh").read_text(encoding="utf-8")
    assert 'fetch-ubo.py seed "$bin_dir/camoufox-bin"' in seed_sh
