"""
Verify a context's locale and request identity reach every scope of its pages.

With a launch locale of en-US and a context created with locale "de-DE", every
scope must report de-DE and Asia/Tokyo, every request must send the context's
Accept-Language and User-Agent, and built-in strings must use the context's
language. A second context with another locale checks that no context changed
the launch locale or another context's isolated world.

    python browser/tests/playwright/patches/context-locale-follows.py
"""

import functools
import http.server
import os
import sys
import tempfile
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from helpers import launch_kwargs  # noqa: E402

LOCALE = "de-DE"
TIMEZONE = "Asia/Tokyo"
OTHER_LOCALE = "fr-FR"
OTHER_TIMEZONE = "Europe/Paris"

READ = """() => ({
  languages: typeof navigator === 'undefined' ? null : [...navigator.languages],
  userAgent: typeof navigator === 'undefined' ? null : navigator.userAgent,
  locale: new Intl.DateTimeFormat().resolvedOptions().locale,
  timeZone: new Intl.DateTimeFormat().resolvedOptions().timeZone,
})"""

WORKER = f"""const read = {READ};
const report = async (kind) => {{ await fetch('/from-' + kind); return read(); }};
onmessage = async (e) => {{
  if (e.source) e.source.postMessage(await report('service'));
  else postMessage(await report('dedicated'));
}};
onconnect = (e) => {{
  const port = e.ports[0];
  port.onmessage = async () => port.postMessage(await report('shared'));
}};
"""

WORKLET = f"""const read = {READ};
registerProcessor('probe', class extends AudioWorkletProcessor {{
  constructor() {{ super(); this.port.postMessage(read()); }}
  process() {{ return false; }}
}});
"""

PROBE = f"""mw:(async () => {{
  const read = {READ};
  const out = {{window: read()}};
  out.dedicated = await new Promise(r => {{
    const w = new Worker('/w.js'); w.onmessage = e => r(e.data); w.postMessage(0);
  }});
  out.shared = await new Promise(r => {{
    const s = new SharedWorker('/w.js'); s.port.onmessage = e => r(e.data); s.port.postMessage(0);
  }});
  const reg = await navigator.serviceWorker.register('/w.js');
  const sw = reg.installing || reg.waiting || reg.active;
  if (sw.state !== 'activated')
    await new Promise(r => sw.addEventListener('statechange', () => sw.state === 'activated' && r()));
  out.service = await new Promise(r => {{
    navigator.serviceWorker.onmessage = e => r(e.data); sw.postMessage(0);
  }});
  const audio = new OfflineAudioContext(1, 128, 44100);
  await audio.audioWorklet.addModule('/worklet.js');
  out.worklet = await new Promise(r => {{ new AudioWorkletNode(audio, 'probe').port.onmessage = e => r(e.data); }});
  return out;
}})()"""

UI = """() => {
  const input = document.createElement('input');
  input.required = true;
  const email = document.createElement('input');
  email.type = 'email';
  email.value = 'x';
  const xml = new DOMParser().parseFromString('<a>', 'text/xml');
  return {required: input.validationMessage, email: email.validationMessage,
          xml: xml.querySelector('parsererror').firstChild.textContent.split('\\n')[0]};
}"""

SEEN = {}


class Recording(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        path = self.path.split("?", 1)[0]
        SEEN.setdefault(path, []).append(
            (self.headers.get("Accept-Language"), self.headers.get("User-Agent"))
        )
        if path.startswith("/from-"):
            self.send_response(204)
            self.end_headers()
            return
        super().do_GET()

    def log_message(self, *a):
        pass


def main() -> int:
    from camoufox.sync_api import Camoufox, NewContext

    with tempfile.TemporaryDirectory() as site:
        Path(site, "p.html").write_text(
            "<!doctype html><meta charset=utf-8><body>x</body>", encoding="utf-8"
        )
        Path(site, "w.js").write_text(WORKER, encoding="utf-8")
        Path(site, "worklet.js").write_text(WORKLET, encoding="utf-8")
        srv = http.server.ThreadingHTTPServer(
            ("127.0.0.1", 0), functools.partial(Recording, directory=site)
        )
        threading.Thread(target=srv.serve_forever, daemon=True).start()

        try:
            with Camoufox(
                **launch_kwargs(locale=LOCALE, i_know_what_im_doing=True)
            ) as browser:
                expected_ui = browser.new_page().evaluate(UI)
            with Camoufox(
                **launch_kwargs(
                    os="windows",
                    canvas_noise=True,
                    locale="en-US",
                    config={"timezone": "America/New_York"},
                    main_world_eval=True,
                    i_know_what_im_doing=True,
                )
            ) as browser:
                launch_ui = browser.new_page().evaluate(UI)
                launch_page = browser.new_page()
                page = NewContext(
                    browser,
                    os="macos",
                    locale=LOCALE,
                    timezone_id=TIMEZONE,
                ).new_page()
                ui = {"about:blank": page.evaluate(UI)}
                page.goto(f"http://127.0.0.1:{srv.server_address[1]}/p.html")
                ui["page"] = page.evaluate(UI)
                out = page.evaluate(PROBE)
                out["isolated"] = page.evaluate(f"({READ})()")
                launch_default = launch_page.evaluate(f"({READ})()")
                other = NewContext(
                    browser,
                    os="linux",
                    locale=OTHER_LOCALE,
                    timezone_id=OTHER_TIMEZONE,
                ).new_page().evaluate(f"({READ})()")
        finally:
            srv.shutdown()
            srv.server_close()

    failures = []
    for scope, got in out.items():
        print(f"  {scope:10}: {got}")
        if got["locale"] != LOCALE or got["timeZone"] != TIMEZONE:
            failures.append(f"{scope}: Intl reports {got['locale']} / {got['timeZone']}")
        if got["languages"] not in (None, [LOCALE, "de"]):
            failures.append(f"{scope}: navigator.languages {got['languages']}")
    expected_ua = out["window"]["userAgent"]
    for path, requests in sorted(SEEN.items()):
        print(f"  {path:15}: Accept-Language / User-Agent {requests}")
        for accept, user_agent in requests:
            if not (accept or "").startswith("de-DE,de;q="):
                failures.append(f"wire: {path} sent Accept-Language {accept!r}")
            if user_agent != expected_ua:
                failures.append(
                    f"wire: {path} sent User-Agent {user_agent!r}, "
                    f"the context's was {expected_ua!r}"
                )
    required = {"/p.html", "/w.js", "/worklet.js", "/from-dedicated",
                "/from-shared", "/from-service"}
    if not required <= SEEN.keys():
        failures.append(
            f"a request never arrived -- check is vacuous: {sorted(SEEN)}"
        )
    if (
        launch_default["locale"] != "en-US"
        or launch_default["timeZone"] != "America/New_York"
    ):
        failures.append(f"launch: a context changed the launch locale: {launch_default}")
    if other["locale"] != OTHER_LOCALE or other["timeZone"] != OTHER_TIMEZONE:
        failures.append(
            f"isolated: another context reports {other['locale']} / {other['timeZone']}"
        )
    if other["languages"] != [OTHER_LOCALE, "fr"]:
        failures.append(f"isolated: another context reports languages {other['languages']}")

    print(f"  {LOCALE} launch: {expected_ui}")
    if expected_ui == launch_ui:
        allowed = os.environ.get("CAMOUFOX_TEST_ALLOW_MISSING", "").split(",")
        if "packaged-locales" in allowed:
            ui = {}
            print(
                "  ui: not checked, this build has no packaged locales "
                "(allowed: packaged-locales)"
            )
        else:
            failures.append(
                "ui: a de-DE launch words its strings as an en-US one, so this "
                "build has no packaged locales and the check would prove nothing"
            )
    for where, got in ui.items():
        print(f"  {where:15}: {got}")
        if got != expected_ui:
            failures.append(
                f"ui: {where} words its strings as {got}, "
                f"a {LOCALE} launch as {expected_ui}"
            )

    print()
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}")
        return 1
    print(
        "PASS: every scope, request and built-in string follows the "
        "context's locale and timezone."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
