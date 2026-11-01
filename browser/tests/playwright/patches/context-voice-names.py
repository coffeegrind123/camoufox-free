r"""
A context's speech voices keep names that hold a comma.

NewContext() hands a context its voices through setSpeechVoices(), as one
string. The browser split it on commas, but Windows voice names hold commas
("Microsoft Hanhan - Chinese (Traditional, Taiwan)"), so each such name was cut
in two, matched no registered voice, and the context lost it: a zh-TW or zh-CN
Windows context showed no Chinese voice. The list is now one name per line.

The launch registers two Windows voices, one with a comma in its name; a context
is given both, as the launchers pass them. Its page must list both.

    python browser/tests/playwright/patches/context-voice-names.py
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from helpers import launch_kwargs  # noqa: E402

VOICES = [
    {"name": "Microsoft Hanhan - Chinese (Traditional, Taiwan)", "lang": "zh-TW",
     "voiceUri": "urn:moz-tts:sapi:Microsoft Hanhan - Chinese (Traditional, Taiwan)?zh-TW",
     "isDefault": False, "isLocalService": True},
    {"name": "Microsoft David - English (United States)", "lang": "en-US",
     "voiceUri": "urn:moz-tts:sapi:Microsoft David - English (United States)?en-US",
     "isDefault": False, "isLocalService": True},
]

VOICE_NAMES = """async () => {
  let voices = speechSynthesis.getVoices();
  if (!voices.length) {
    await new Promise(r => { speechSynthesis.onvoiceschanged = r; setTimeout(r, 3000); });
    voices = speechSynthesis.getVoices();
  }
  return voices.map(v => v.name).sort();
}"""


def main() -> int:
    from camoufox.sync_api import Camoufox

    names = sorted(v["name"] for v in VOICES)
    with Camoufox(**launch_kwargs(os="windows", config={"voices": VOICES},
                                  i_know_what_im_doing=True)) as browser:
        launch_page = browser.new_page()
        launch_page.set_content("<p>voices</p>")
        launch = launch_page.evaluate(VOICE_NAMES)

        context = browser.new_context()
        context.add_init_script(
            f"if (typeof setSpeechVoices === 'function') setSpeechVoices({json.dumps(chr(10).join(names))});")
        page = context.new_page()
        page.set_content("<p>voices</p>")
        seen = page.evaluate(VOICE_NAMES)

    print(f"launch: {json.dumps(launch)}")
    print(f"context: {json.dumps(seen)}")
    if launch != names:
        print("FAIL: the launch does not list the two configured voices, so this proves nothing")
        return 1
    if seen != names:
        print("FAIL: the context lost a voice it was given")
        return 1
    print("PASS: a context keeps every voice it is given, commas and all")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
