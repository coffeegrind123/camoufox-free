r"""
A Linux identity draws only its own OS's bundled fonts.

On Linux, ActivateBundledFonts() added <GRE>/fonts as an application font
directory, and fontconfig scans one recursively, so every OS's group (M for
macOS, W for Windows, ...) sat on the search path past the per-OS directories
the launcher's fontconfig names. The font list filters by family name, not by
the file a name resolves to, so a Linux identity's "Helvetica" drew Apple's
Helvetica from fonts/M/, a face no Linux machine has, and a canvas text
fingerprint records it. linux-bundled-fonts-toplevel.patch adds only the files
directly in fonts/.

A real Linux machine resolves Helvetica, Times and Courier to their metric
aliases, Nimbus Sans, Nimbus Roman and Nimbus Mono PS, which the Linux group
carries. Each name's per-character advances must match its alias's; Apple's
faces differ on accented Latin and symbols (on v158.0-beta.33-cg.9, Helvetica
differed from Nimbus Sans on 21 of 329 characters, e.g. U+0128 89.0 vs 55.6).

    python browser/tests/playwright/patches/bundled-font-groups.py
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from helpers import launch_kwargs  # noqa: E402

ALIASES = {"Helvetica": "Nimbus Sans", "Times": "Nimbus Roman", "Courier": "Nimbus Mono PS"}
CHARS = [chr(c) for c in [*range(0x21, 0x7F), *range(0xA1, 0x180),
                          0x2014, 0x201C, 0x2026, 0x20AC, 0x2122, 0xFB01, 0xFB02]]
# Canvas advances of one face agree to the hundredth; a different face misses by
# a pixel or more at 200px.
TOLERANCE = 0.3

MEASURE = """([aliases, chars]) => {
  const c = document.createElement('canvas').getContext('2d');
  const advances = family => { c.font = `200px "${family}"`; return chars.map(ch => c.measureText(ch).width); };
  const out = {};
  for (const [name, alias] of Object.entries(aliases))
    out[name] = {name: advances(name), alias: advances(alias), aliasAvailable: document.fonts.check(`12px "${alias}"`)};
  return out;
}"""


def main() -> int:
    from camoufox.sync_api import Camoufox

    with Camoufox(**launch_kwargs(os="linux")) as browser:
        page = browser.new_page()
        page.set_content("<p>fonts</p>")
        result = page.evaluate(MEASURE, [ALIASES, CHARS])

    failures = []
    for name, alias in ALIASES.items():
        r = result[name]
        if not r["aliasAvailable"]:
            failures.append(f"{alias} is not in this Linux identity's fonts, so {name} proves nothing")
            continue
        differ = [(ch, round(a, 1), round(b, 1)) for ch, a, b in zip(CHARS, r["name"], r["alias"])
                  if abs(a - b) > TOLERANCE]
        print(f"{name} vs {alias}: {len(differ)}/{len(CHARS)} characters differ {json.dumps(differ[:6], ensure_ascii=False)}")
        if differ:
            failures.append(f"{name} draws a face other than {alias}, its Linux metric alias")
    for failure in failures:
        print(f"FAIL: {failure}")
    if failures:
        return 1
    print("PASS: a Linux identity's Helvetica, Times and Courier draw their Linux aliases")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
