#!/usr/bin/env python3
"""Copy Camoufox additions and settings into a prepared Firefox tree.

Incremental mode leaves identical files untouched so their mtimes, and the
downstream build graph, stay stable. Baseline mode also creates the files that
`make setup` needs before patches run.

Run from browser/:

    python3 scripts/sync_additions.py camoufox-<version>-<release>
    python3 scripts/sync_additions.py camoufox-<version>-<release> --baseline
"""

import argparse
import filecmp
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SETTINGS = {
    "settings/camoufox.cfg": "lw/camoufox.cfg",
    "settings/distribution/policies.json": "lw/policies.json",
    "settings/defaults/pref/local-settings.js": "lw/local-settings.js",
    "settings/properties.json": "lw/properties.json",
}


def copy_if_changed(src: Path, dst: Path) -> bool:
    if dst.is_file() and filecmp.cmp(src, dst, shallow=False):
        return False
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    return True


def write_if_changed(path: Path, content: str) -> bool:
    if path.is_file() and path.read_text(encoding="utf-8") == content:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return True


def read_upstream() -> dict:
    values = {}
    for line in (REPO / "upstream.sh").read_text(encoding="utf-8").splitlines():
        if "=" in line:
            key, value = line.strip().split("=", 1)
            values[key] = value
    return values


def sync(tree: Path, baseline: bool) -> list[str]:
    changed = []
    assets = REPO / "additions/browser/branding/camoufox/Assets.car"
    if not assets.is_file():
        subprocess.run(
            ["bash", str(REPO / "scripts/generate-assets-car.sh")],
            check=True,
        )

    for src, rel in SETTINGS.items():
        if copy_if_changed(REPO / src, tree / rel):
            changed.append(rel)

    # The empty file is part of unpatched Firefox. Existing content may be the
    # config patch, which a fast sync must leave alone.
    mozbuild = tree / "lw/moz.build"
    if not mozbuild.exists():
        mozbuild.parent.mkdir(parents=True, exist_ok=True)
        mozbuild.touch()

    additions = REPO / "additions"
    for src in sorted(path for path in additions.rglob("*") if path.is_file()):
        rel = str(src.relative_to(additions))
        if copy_if_changed(src, tree / rel):
            changed.append(rel)

    if baseline:
        upstream = read_upstream()
        version = f"{upstream['version']}-{upstream['release']}\n"
        for rel in (
            "browser/config/version.txt",
            "browser/config/version_display.txt",
        ):
            if write_if_changed(tree / rel, version):
                changed.append(rel)

    return changed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_dir", type=Path)
    parser.add_argument("--baseline", action="store_true")
    args = parser.parse_args()

    tree = args.source_dir.resolve()
    changed = sync(tree, baseline=args.baseline)
    for rel in changed:
        print(f"updated {rel}")
    print(f"{len(changed)} file(s) changed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
