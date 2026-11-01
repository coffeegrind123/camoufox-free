"""
Verify each context sees, and speaks with, only its own speech voices.

A context's voices used to filter the voices the launch registered, so a
context drawn for another locale or OS showed only what the launch's draw
happened to have: a de-DE context in an en-US Windows launch listed no German
voice, where a German Windows lists its language pack's. The launcher now also
passes every voice of the manifests as `voices:pool`, the browser registers
them beside the launch's, and only a context whose list names one sees it.

Registering more voices must not reach pages that cannot list them. The
registry picks the voice for an utterance without one by its language, and
falls back on any registered voice, so the browser matches only among the
voices the page's context sees. A launch with no voices of its own still has
none for its pages: speak() does nothing, and an utterance forced through by
resume() errors, as on a machine with no voices.

The probe launches an en-US Windows identity with a fixed launch list and the
host's speech daemon unreachable, then checks, with the registry's choice read
from its MOZ_LOG:

    * a de-DE Windows context lists its own drawn voices, in its order, German
      ones first, including voices the launch does not have;
    * the launch's pages and a context made without a list see exactly the
      launch's voices;
    * an utterance without a voice speaks with one of its page's voices: a
      German one in the de-DE context, a launch voice elsewhere, even when its
      language is German;
    * with an empty launch list, a page sees no voices and cannot speak.

    python browser/tests/playwright/patches/context-voice-pool.py
"""

import os
import re
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from helpers import launch_kwargs  # noqa: E402

VOICES = """async () => {
  let voices = speechSynthesis.getVoices();
  if (!voices.length) {
    await new Promise(r => { speechSynthesis.onvoiceschanged = r; setTimeout(r, 2000); });
    voices = speechSynthesis.getVoices();
  }
  return voices.map(v => [v.name, v.lang]);
}"""

# Speaks `text` in `lang` without choosing a voice and reports the events.
# With `forced`, the utterance is queued while paused and released by
# resume(), which advances the queue whether or not the page has voices.
SPEAK = """async ({text, lang, forced}) => {
  const u = new SpeechSynthesisUtterance(text);
  u.lang = lang;
  const events = [];
  const done = new Promise(resolve => {
    for (const type of ['start', 'end', 'error']) {
      u.addEventListener(type, () => { events.push(type); if (type !== 'start') resolve(); });
    }
    setTimeout(resolve, 3000);
  });
  if (forced) speechSynthesis.pause();
  speechSynthesis.speak(u);
  if (forced) speechSynthesis.resume();
  await done;
  speechSynthesis.cancel();
  return events;
}"""

SPOKEN = re.compile(r"SpeakImpl queueing text='([^']*)' uri='([^']*)'")


def spoken_uris(logdir: Path) -> dict:
    """Utterance text -> the voice URI the parent's registry spoke it with."""
    found = {}
    for log in logdir.iterdir():
        for text, uri in SPOKEN.findall(log.read_text(errors="replace")):
            found[text] = uri
    return found


def main() -> int:
    from camoufox import sync_api
    from camoufox.fingerprints import _generate_random_voice_subset, voice_pool
    from camoufox.sync_api import Camoufox, NewContext

    launch_voices = _generate_random_voice_subset("windows", "en-US", seed=1)
    launch_names = [[v["name"], v["lang"]] for v in launch_voices]
    launch_uris = {v["voiceUri"] for v in launch_voices}
    pool_uris = {v["voiceUri"]: v for v in voice_pool()}

    # The draw NewContext makes for the de-DE context: its list and order.
    drawn = []
    generate = sync_api.generate_context_fingerprint

    def recording(*args, **kwargs):
        fp = generate(*args, **kwargs)
        drawn.append(fp["config"]["voices"])
        return fp

    sync_api.generate_context_fingerprint = recording

    logdir = Path(tempfile.mkdtemp(prefix="voice-pool-log-"))
    env = {
        **os.environ,
        # The host backend fails to start, as on a machine without the daemon.
        "SPEECHD_ADDRESS": "unix_socket:/nonexistent/speechd.sock",
        # Both launches write here; append keeps the first launch's log.
        "MOZ_LOG": "SpeechSynthesis:5,sync,append",
        "MOZ_LOG_FILE": str(logdir / "speech"),
    }
    failures = []
    try:
        common = dict(os="windows", canvas_noise=True, locale="en-US", env=env,
                      i_know_what_im_doing=True)
        with Camoufox(**launch_kwargs(**common, config={"voices": launch_voices})) as browser:
            launch_page = browser.new_page()
            german_page = NewContext(browser, os="windows", locale="de-DE").new_page()
            plain_page = browser.new_context().new_page()

            seen = {
                "launch": launch_page.evaluate(VOICES),
                "de-DE context": german_page.evaluate(VOICES),
                "context without a list": plain_page.evaluate(VOICES),
            }
            spoke = {
                "launch-de": launch_page.evaluate(SPEAK, dict(text="launch-de", lang="de-DE", forced=False)),
                "plain-de": plain_page.evaluate(SPEAK, dict(text="plain-de", lang="de-DE", forced=False)),
                "german-de": german_page.evaluate(SPEAK, dict(text="german-de", lang="de-DE", forced=False)),
            }

        with Camoufox(**launch_kwargs(**common, config={"voices": []})) as browser:
            empty_page = browser.new_page()
            seen["launch with no voices"] = empty_page.evaluate(VOICES)
            spoke["empty"] = empty_page.evaluate(SPEAK, dict(text="empty", lang="de-DE", forced=False))
            spoke["empty-forced"] = empty_page.evaluate(SPEAK, dict(text="empty-forced", lang="de-DE", forced=True))

        uris = spoken_uris(logdir)
    finally:
        sync_api.generate_context_fingerprint = generate
        shutil.rmtree(logdir, ignore_errors=True)

    for name, voices in seen.items():
        print(f"  {name}: {len(voices)} voices, first {voices[:2]}")
    for text, events in spoke.items():
        print(f"  speak {text}: {events} with {uris.get(text)}")

    german_list = [[v["name"], v["lang"]] for v in drawn[0]] if drawn else []
    german_uris = {v["voiceUri"] for v in drawn[0]} if drawn else set()
    if not german_list or german_list[0][1] != "de-DE":
        failures.append(f"the de-DE context was not drawn for its locale: {german_list[:2]}")
    if not german_uris - launch_uris:
        failures.append("the de-DE context's draw has no voice the launch lacks, so nothing was tested")
    if not german_uris <= pool_uris.keys():
        failures.append(f"the de-DE context's draw is not in voices:pool: {sorted(german_uris - pool_uris.keys())}")
    if seen["de-DE context"] != german_list:
        failures.append(f"the de-DE context lists {seen['de-DE context'][:4]}..., not its own {german_list[:4]}...")
    for name in ("launch", "context without a list"):
        if seen[name] != launch_names:
            failures.append(f"the {name} page lists {seen[name][:4]}..., not the launch's {launch_names[:4]}...")
    if seen["launch with no voices"]:
        failures.append(f"a launch with no voices lists {seen['launch with no voices'][:4]}")

    for text, allowed in (("launch-de", launch_uris), ("plain-de", launch_uris),
                          ("german-de", german_uris)):
        if spoke[text] != ["start", "end"]:
            failures.append(f"{text}: expected start then end, got {spoke[text]}")
        if uris.get(text) not in allowed:
            failures.append(f"{text}: spoke with {uris.get(text)}, a voice the page cannot list")
    if pool_uris.get(uris.get("german-de"), {}).get("lang") != "de-DE":
        failures.append(f"german-de: a German utterance in the de-DE context took {uris.get('german-de')}")
    if spoke["empty"]:
        failures.append(f"empty: a page with no voices spoke: {spoke['empty']}")
    if spoke["empty-forced"] != ["error"] or "empty-forced" in uris:
        failures.append(f"empty-forced: expected only an error, got {spoke['empty-forced']} "
                        f"with {uris.get('empty-forced')}")

    for failure in failures:
        print(f"  FAIL: {failure}")
    if failures:
        return 1
    print("  PASS: every page lists and speaks with only its own context's voices")
    return 0


if __name__ == "__main__":
    sys.exit(main())
