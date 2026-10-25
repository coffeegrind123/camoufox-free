#!/usr/bin/env python3
"""Measure the Windows font units' rates from the pinned fpgen model.

font-manifests.json says how often a Windows machine carries each addition
(Office, LibreOffice, web fonts...). Those rates must come from recorded
devices, not from memory, and the one recorded source this repo pins is the
fpgen model (python/src/camoufox/fpgen-model.json). This draws fingerprints
from it and counts, for each unit, how many show the unit's fonts.

Only the fonts the model probes can be counted, and units share members
(`Roboto` is in both `libreoffice` and `web`), so a unit is detected by the
fonts that no other unit and no base carries. A bundle installs whole, so a
sample that shows any of its probed fonts shows it all. An a-la-carte unit
installs only a few of its fonts, so a sample misses it whenever the few were
not probed ones; `reveal_probability` undoes that. Units with no probed
exclusive font (`meslo`, `cascadia`), and `cjk-tc`, whose rate is conditional
on a locale the samples do not carry, keep the rate they have. A bundle counts
as present when at least half of its probed fonts show.

The draw is seeded, so a rerun gives the same table. fpgen is loaded through
camoufox.fpgen_model.load_fpgen(), which installs the pinned model first (a bare
`import fpgen` would fetch another one), so the package must be importable:
`pip install -e python`.

Usage:
    python3 browser/scripts/measure-font-units.py            # print old -> new
    python3 browser/scripts/measure-font-units.py --write    # update the manifest
then:
    python3 browser/scripts/gen-font-groups.py
"""

import argparse
import json
import math
import os
import random
import re

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.dirname(REPO)
MANIFEST = os.path.join(REPO, 'scripts', 'data', 'font-manifests.json')
MODEL = os.path.join(ROOT, 'python', 'src', 'camoufox', 'fpgen-model.json')
STYLE = re.compile(r' (Bold|Italic|Regular|Oblique)( Italic)?$')


def reveal_probability(kind, probed, total, sizes):
    """The chance a sample shows at least one probed font of an installed unit."""
    if kind == 'bundle':
        return 1.0
    if not sizes:
        raise ValueError('an a-la-carte unit needs its sizes to correct its rate')
    return sum(
        size['w'] * (
            1 - math.comb(total - probed, size['n']) / math.comb(total, size['n'])
        )
        for size in sizes
    )


def exclusive_fonts(units, base):
    """Per unit, the fonts that no other unit and no base also carries."""
    out = {}
    for unit in units:
        others = set(base).union(*(set(other['fonts']) for other in units if other is not unit))
        out[unit['id']] = set(unit['fonts']) - others
    return out


def skip_reason(unit, probed):
    """Why a unit keeps the rate it has, or None when the samples can speak for it."""
    if unit.get('requiresLocale'):
        return f"its rate is conditional on locale {unit['requiresLocale']}, which the samples ignore"
    if not probed:
        return 'the model probes none of its exclusive fonts'
    return None


def unit_rate(samples, kind, probed, total, sizes):
    """The share of machines that carry the unit, from samples of the fonts each shows."""
    need = 1 if kind == 'alacarte' else max(1, math.ceil(len(probed) / 2))
    seen = sum(len(probed & sample) >= need for sample in samples) / len(samples)
    return min(1.0, seen / reveal_probability(kind, len(probed), total, sizes))


def draw(n, seed):
    from camoufox.fpgen_model import load_fpgen

    fpgen = load_fpgen()
    random.seed(seed)
    out = []
    for _ in range(n):
        fonts = set(fpgen.generate(os='Windows').get('allFonts') or [])
        out.append(fonts | {STYLE.sub('', font) for font in fonts})
    return out


def main():
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument('--n', type=int, default=8000)
    parser.add_argument('--seed', type=int, default=0)
    parser.add_argument('--write', action='store_true')
    args = parser.parse_args()

    with open(MANIFEST, encoding='utf-8') as fh:
        manifest = json.load(fh)
    with open(MODEL, encoding='utf-8') as fh:
        tag = json.load(fh)['tag']
    windows = manifest['win']
    base = set(windows['bases']['win11']['fonts'])
    exclusive = exclusive_fonts(windows['additions'], base)

    samples = draw(args.n, args.seed)
    universe = set().union(*samples)
    print(f'model {tag}, {args.n} Windows draws, seed {args.seed}')
    for unit in windows['additions']:
        probed = exclusive[unit['id']] & universe
        reason = skip_reason(unit, probed)
        if reason:
            print(f"  {unit['id']:12s} kept {unit['prob']}: {reason}")
            continue
        rate = round(
            unit_rate(
                samples,
                unit['kind'],
                probed,
                len(unit['fonts']),
                unit.get('sizes', []),
            ),
            3,
        )
        print(
            f"  {unit['id']:12s} {unit['prob']} -> {rate}  "
            f"({len(probed)} of {len(unit['fonts'])} fonts probed)"
        )
        if args.write:
            unit['prob'] = rate
            unit['model'] = tag
    if args.write:
        with open(MANIFEST, 'w', encoding='utf-8') as fh:
            json.dump(manifest, fh, indent=1, ensure_ascii=False)
            fh.write('\n')
        print('wrote', MANIFEST)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
