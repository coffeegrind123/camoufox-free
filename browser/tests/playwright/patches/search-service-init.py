r"""
Verify the search service starts with stock Firefox's engines, and DuckDuckGo
as the default.

no-search-engines.patch replaced the search configuration with one inert
engine whose search URL was the loopback address, and policies.json made it
the default. Stock Firefox reads search-config-v2 from Remote Settings (with
the copy packaged in omni.ja until the first sync), so a fresh profile has
Google, Bing, DuckDuckGo, ... for its region, and fetches the collection and
its icons as stock does. The network sees that fetch, and a stock install
with no search engine is not one any user has.

This launches stock Firefox (--stock, else the release stock-gpu-parity
downloads) and Camoufox on fresh profiles with the region pinned, and checks
that the search service finishes initializing in both and adds the same
engines in the same order.

The default engine is the one deliberate difference: this fork makes
DuckDuckGo, one of stock's own US engines, the default where stock picks
Google (ci/tribal-rules.yml, duckduckgo-default-over-stock-engines). It is
read over Marionette from the SearchService module, in both browsers, so a stock
default that is already DuckDuckGo shows the check proves nothing.

    python browser/tests/playwright/patches/search-service-init.py
    python browser/tests/playwright/patches/search-service-init.py --binary CAMOUFOX --stock FIREFOX
"""

import importlib.util
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from helpers import Marionette, free_port, marionette_args, marionette_env, resolve_binary

HERE = Path(__file__).resolve().parent

# Long enough for the search service to init and write settings; the browser
# does not exit on its own with -headless about:blank, so it is killed after.
LAUNCH_TIMEOUT_S = 60

# The fork's default engine (search-config patch).
DEFAULT_ENGINE = "DuckDuckGo"

ADDED_ENGINE_RE = re.compile(r'"#addEngineToStore: Adding engine:" "([^"]*)"')


def launch_and_capture(binary: Path, profile: Path) -> str:
    """Start the browser on a fresh profile with search logging, return output."""
    # An official build keeps the chrome console off stdout, where the log is read.
    (profile / "user.js").write_text(
        'user_pref("browser.search.log", true);\n'
        'user_pref("devtools.console.stdout.chrome", true);\n'
        # The engines depend on the region, which Firefox otherwise detects
        # from the network partway through startup.
        'user_pref("browser.search.region", "US");\n'
    )
    proc = subprocess.Popen(
        [str(binary), "-profile", str(profile), "-headless", "-no-remote", "about:blank"],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, errors="replace",
    )
    try:
        out, _ = proc.communicate(timeout=LAUNCH_TIMEOUT_S)
        return out
    except subprocess.TimeoutExpired:
        # Expected: about:blank never exits. Take what was logged.
        proc.kill()
        out, _ = proc.communicate()
        return out


def default_engine(binary: Path) -> str:
    """SearchService's default engine on a fresh profile, region US."""
    port = free_port()
    with tempfile.TemporaryDirectory(prefix="search-default-") as tmp:
        Path(tmp, "user.js").write_text(
            f'user_pref("marionette.port", {port});\n'
            'user_pref("browser.search.region", "US");\n'
        )
        proc = subprocess.Popen(
            [str(binary), "-profile", tmp, "-headless", "-no-remote", *marionette_args(), "about:blank"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=marionette_env(),
        )
        try:
            m = Marionette(port)
            # Firefox 159 has no Services.search; the service is a moz-src module.
            name = m.js(
                'const { SearchService } = ChromeUtils.importESModule('
                '"moz-src:///toolkit/components/search/SearchService.sys.mjs");'
                "return SearchService.getDefault().then(e => e ? e.name : null);"
            )
            m.close()
        finally:
            proc.kill()
            proc.wait()
    return name


def stock_firefox() -> Path:
    spec = importlib.util.spec_from_file_location("getter_cost_parity", HERE / "getter-cost-parity.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    binary = module.stock_firefox()
    module.prepare_stock(binary)
    return binary


def search_state(binary: Path) -> dict:
    with tempfile.TemporaryDirectory(prefix="search-") as tmp:
        profile = Path(tmp)
        log = launch_and_capture(binary, profile)
        written = (profile / "search.json.mozlz4").exists()
    failed = [line.strip()[:160] for line in log.splitlines()
              if "#init: failure initializing search" in line or "missing field `recordType`" in line]
    return {
        "completed": "Completed #init" in log,
        "failed": failed,
        "written": written,
        "engines": list(dict.fromkeys(ADDED_ENGINE_RE.findall(log))),
    }


def main() -> int:
    binary = resolve_binary()
    stock = stock_firefox()
    cf, ref = search_state(binary), search_state(stock)
    cf["default"], ref["default"] = default_engine(binary), default_engine(stock)
    for name, state in (("stock", ref), ("camoufox", cf)):
        print(f"  {name:9} init {'completed' if state['completed'] else 'NOT completed'}, "
              f"settings {'written' if state['written'] else 'MISSING'}, engines: {state['engines']}, "
              f"default: {state['default']}")

    failures = []
    if not ref["completed"] or not ref["engines"]:
        failures.append("stock Firefox logged no search init with engines: the check proves nothing")
    if not cf["completed"]:
        failures.append("Camoufox's search service never logged 'Completed #init'")
    failures += [f"Camoufox: {line}" for line in cf["failed"]]
    if not cf["written"]:
        failures.append("Camoufox never wrote search.json.mozlz4")
    if cf["engines"] != ref["engines"]:
        failures.append(f"Camoufox added {cf['engines']}, stock {ref['engines']}")
    if ref["default"] == DEFAULT_ENGINE:
        failures.append(f"stock's default is already {DEFAULT_ENGINE}: the default check proves nothing")
    if DEFAULT_ENGINE not in ref["engines"]:
        failures.append(f"{DEFAULT_ENGINE} is not one of stock's engines here; the default would be one stock lacks")
    if cf["default"] != DEFAULT_ENGINE:
        failures.append(f"Camoufox's default engine is {cf['default']!r}, not {DEFAULT_ENGINE}")

    print()
    for f in failures:
        print(f"FAIL: {f}")
    if failures:
        return 1
    print(f"PASS: the search service starts with stock's engines, {DEFAULT_ENGINE} the default.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
