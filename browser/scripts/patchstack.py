#!/usr/bin/env python3
"""Replay and regenerate the Camoufox patch stack without a Firefox build.

    python3 scripts/patchstack.py verify [--compare]
        Replay every patch, in the order patch.py applies them, onto clean
        upstream copies of just the files the stack touches. Any reject, fuzz
        or partial application fails. --compare also verifies that the prepared
        source tree contains exactly the replayed result.

    python3 scripts/patchstack.py regen patches/<name>.patch
        Rewrite one patch from the prepared source tree. The base is clean
        upstream with every earlier patch replayed. Regeneration is refused
        when a later patch touches the same file, since the source tree would
        then contain both changes.

Clean upstream files come from the source tree's `unpatched` tag when it has
one, otherwise from the pinned Firefox source tarball.
"""

import argparse
import filecmp
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path
from typing import Dict, Iterable, List, Optional

SCRIPT_DIR = Path(__file__).resolve().parent
REPO = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))

from _mixin import PATCH_FLAGS, list_patches  # noqa: E402


def upstream_version() -> tuple[str, str]:
    values = {}
    for line in (REPO / "upstream.sh").read_text(encoding="utf-8").splitlines():
        if "=" in line:
            key, value = line.strip().split("=", 1)
            values[key] = value
    return values["version"], values["release"]


def source_dir() -> Path:
    version, release = upstream_version()
    return REPO / f"camoufox-{version}-{release}"


def ordered_patches() -> List[Path]:
    """The order patch.py applies: sorted by basename, subdirectories included."""
    cwd = Path.cwd()
    try:
        os.chdir(REPO)
        return [Path(path).resolve() for path in list_patches("patches")]
    finally:
        os.chdir(cwd)


def _header_path(line: str) -> Optional[str]:
    path = line.split("\t", 1)[0].rstrip()
    for prefix in ("a/", "b/"):
        if path.startswith(prefix):
            return path[len(prefix):]
    return path or None


def sections(patch: Path) -> Dict[str, str]:
    """Return one patch section per path, keyed as patch(1) sees it.

    Sections begin at `diff --git` or a bare `---`/`+++` pair. The destination
    header is authoritative because a few patches carry a stale `diff --git`
    path. Sections for the same path are concatenated in source order.
    """
    lines = patch.read_text(encoding="utf-8", errors="surrogateescape").splitlines(
        keepends=True
    )
    chunks: List[List[str]] = []
    current: List[str] = []
    seen_hunk = False

    for index, line in enumerate(lines):
        bare_header = (
            line.startswith("--- ")
            and index + 1 < len(lines)
            and lines[index + 1].startswith("+++ ")
            and seen_hunk
        )
        if line.startswith("diff --git ") or bare_header:
            if current:
                chunks.append(current)
            current = []
            seen_hunk = False
        current.append(line)
        if line.startswith("@@"):
            seen_hunk = True
    if current:
        chunks.append(current)

    result: Dict[str, str] = {}
    for chunk in chunks:
        text = "".join(chunk)
        candidates = (
            re.search(r"(?m)^\+\+\+ (b/\S+)", text),
            re.search(r"(?m)^--- (a/\S+)", text),
            re.search(r"(?m)^diff --git a/(\S+) b/", text),
        )
        path = next(
            (
                _header_path(match.group(1))
                for match in candidates
                if match
            ),
            None,
        )
        if path:
            result[path] = result.get(path, "") + text
    return result


def fetch_clean(files: Iterable[str], dest: Path) -> None:
    """Populate `dest` with unpatched versions of the stack's touched files."""
    wanted = sorted(set(files))
    tree = source_dir()
    has_tag = (
        (tree / ".git").is_dir()
        and subprocess.run(
            ["git", "-C", str(tree), "rev-parse", "-q", "--verify", "unpatched"],
            capture_output=True,
        ).returncode
        == 0
    )

    if has_tag:
        for path in wanted:
            blob = subprocess.run(
                ["git", "-C", str(tree), "show", f"unpatched:{path}"],
                capture_output=True,
            )
            if blob.returncode == 0:
                target = dest / path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(blob.stdout)
    else:
        version, _ = upstream_version()
        tarball = REPO / f"firefox-{version}.source.tar.xz"
        if not tarball.is_file():
            sys.exit(
                f"No clean source: neither {tree} with an `unpatched` tag nor "
                f"{tarball}. Run `make fetch` first."
            )
        remaining = set(wanted)
        with tarfile.open(tarball) as archive:
            for member in archive:
                name = member.name.split("/", 1)[1] if "/" in member.name else ""
                if name not in remaining or not member.isfile():
                    continue
                source = archive.extractfile(member)
                if source is None:
                    continue
                target = dest / name
                target.parent.mkdir(parents=True, exist_ok=True)
                with source, target.open("wb") as output:
                    shutil.copyfileobj(source, output)
                remaining.remove(name)

    prepare_baseline(dest)


def prepare_baseline(tree: Path) -> None:
    """Overlay the additions and settings that `make setup` places before patches."""
    result = subprocess.run(
        [sys.executable, str(SCRIPT_DIR / "sync_additions.py"), str(tree), "--baseline"],
        capture_output=True,
        text=True,
    )
    if result.returncode:
        sys.exit(result.stdout + result.stderr)


def apply(patch_text: str, root: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [
            "patch",
            *PATCH_FLAGS,
            "--no-backup-if-mismatch",
            "-r",
            "-",
            "-d",
            str(root),
        ],
        input=patch_text,
        text=True,
        capture_output=True,
    )


def _output_lines(result: subprocess.CompletedProcess) -> List[str]:
    return result.stdout.splitlines() + result.stderr.splitlines()


def _apply_or_fail(name: str, patch_text: str, root: Path) -> bool:
    result = apply(patch_text, root)
    lines = _output_lines(result)
    fuzzed = [line for line in lines if "with fuzz" in line]
    rejected = [
        line
        for line in lines
        if "FAILED" in line or ".rej" in line or "malformed patch" in line
    ]
    if result.returncode == 0 and not fuzzed and not rejected:
        return True

    print(f"FAIL {name}")
    for line in fuzzed + rejected or lines:
        print(f"     {line}")
    return False


def _same_file(left: Path, right: Path) -> bool:
    if left.exists() != right.exists():
        return False
    return not left.exists() or filecmp.cmp(left, right, shallow=False)


def verify(compare: bool) -> int:
    patches = ordered_patches()
    files = sorted({path for patch in patches for path in sections(patch)})
    patch_failures = 0
    diff_failures = 0

    with tempfile.TemporaryDirectory(prefix="patchstack-") as temporary:
        root = Path(temporary)
        fetch_clean(files, root)

        for patch in patches:
            name = patch.relative_to(REPO)
            if not _apply_or_fail(
                str(name), patch.read_text(encoding="utf-8", errors="surrogateescape"), root
            ):
                patch_failures += 1
                break

        if compare:
            tree = source_dir()
            for rel in files:
                replayed = root / rel
                actual = tree / rel
                if _same_file(replayed, actual):
                    continue
                why = (
                    "exists on one side only"
                    if replayed.exists() != actual.exists()
                    else "the source tree holds edits no patch records"
                )
                print(f"DIFF {rel}: {why}")
                diff_failures += 1

    print(
        f"{len(patches) - patch_failures}/{len(patches)} patches apply cleanly "
        f"({len(files)} files, {diff_failures} tree differences)"
    )
    return 1 if patch_failures or diff_failures else 0


def _replay_earlier(patches: List[Path], index: int, files: set[str], root: Path) -> None:
    for earlier in patches[:index]:
        selected = {
            path: text for path, text in sections(earlier).items() if path in files
        }
        if not selected:
            continue
        name = str(earlier.relative_to(REPO))
        if not _apply_or_fail(name, "".join(selected.values()), root):
            raise SystemExit(f"{name} does not apply when preparing the regen base")


def _diff_file(base: Path, actual: Path, rel: str) -> str:
    old = str(base) if base.exists() else "/dev/null"
    new = str(actual) if actual.exists() else "/dev/null"
    result = subprocess.run(
        [
            "git",
            "-c",
            "core.quotepath=off",
            "diff",
            "--no-index",
            "--no-color",
            "--no-ext-diff",
            "--diff-algorithm=patience",
            "-U6",
            old,
            new,
        ],
        capture_output=True,
        text=True,
        errors="surrogateescape",
    )
    if result.returncode not in (0, 1):
        raise SystemExit(f"git diff failed for {rel}: {result.stderr}")

    diff = result.stdout
    diff = re.sub(r"(?m)^diff --git .*$", f"diff --git a/{rel} b/{rel}", diff, count=1)
    diff = re.sub(r"(?m)^--- (?!/dev/null).*$", f"--- a/{rel}", diff, count=1)
    diff = re.sub(r"(?m)^\+\+\+ (?!/dev/null).*$", f"+++ b/{rel}", diff, count=1)
    return re.sub(r"(?m)^index .*\n", "", diff)


def _validate_regen(
    base: Path, tree: Path, files: List[str], patch_text: str
) -> None:
    with tempfile.TemporaryDirectory(prefix="patchstack-check-") as temporary:
        check = Path(temporary)
        shutil.copytree(base, check, dirs_exist_ok=True)
        if not _apply_or_fail("regenerated patch", patch_text, check):
            raise SystemExit("regenerated patch does not apply cleanly")
        for rel in files:
            if not _same_file(check / rel, tree / rel):
                raise SystemExit(
                    f"regenerated patch does not reproduce source tree file: {rel}"
                )


def regen(patch_path: str, output: Optional[str] = None) -> int:
    patches = ordered_patches()
    target = Path(patch_path).resolve()
    if target not in patches:
        sys.exit(f"{patch_path} is not in the patch stack")

    touched = sections(target)
    files = list(touched)
    index = patches.index(target)
    for later in patches[index + 1 :]:
        clash = set(files) & set(sections(later))
        if clash:
            sys.exit(
                f"{later.relative_to(REPO)} also touches {sorted(clash)}; "
                "the source tree holds both patches"
            )

    tree = source_dir()
    with tempfile.TemporaryDirectory(prefix="patchstack-base-") as temporary:
        base = Path(temporary)
        fetch_clean(files, base)
        _replay_earlier(patches, index, set(files), base)

        regenerated = "".join(
            _diff_file(base / rel, tree / rel, rel) for rel in files
        )
        if not regenerated:
            sys.exit(f"{target.relative_to(REPO)} would be empty")
        _validate_regen(base, tree, files, regenerated)

        destination = Path(output).resolve() if output else target
        temporary_copy = destination.with_suffix(destination.suffix + ".tmp")
        temporary_copy.parent.mkdir(parents=True, exist_ok=True)
        temporary_copy.write_text(regenerated, encoding="utf-8", errors="surrogateescape")
        temporary_copy.replace(destination)

    shown = target.relative_to(REPO) if destination == target else destination
    print(f"regenerated {shown} ({len(files)} files)")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    commands = parser.add_subparsers(dest="command", required=True)
    verify_parser = commands.add_parser("verify")
    verify_parser.add_argument("--compare", action="store_true")
    regen_parser = commands.add_parser("regen")
    regen_parser.add_argument("patch")
    regen_parser.add_argument("--output")
    args = parser.parse_args()
    return (
        verify(args.compare)
        if args.command == "verify"
        else regen(args.patch, output=args.output)
    )


if __name__ == "__main__":
    sys.exit(main())
