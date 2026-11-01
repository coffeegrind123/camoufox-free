"""Regression tests for the patch stack and incremental build helpers."""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

from ci._util import REPO_ROOT

BROWSER = REPO_ROOT / "browser"
SCRIPTS = BROWSER / "scripts"
sys.path.insert(0, str(SCRIPTS))

import _mixin  # noqa: E402
import patchstack  # noqa: E402


def test_the_current_patch_stack_is_parsed_in_application_order():
    expected = sorted(
        (BROWSER / "patches").rglob("*.patch"),
        key=lambda path: path.name,
    )
    assert patchstack.ordered_patches() == [path.resolve() for path in expected]

    for patch in expected:
        parsed = patchstack.sections(patch)
        declared = {
            match.group(1)
            for match in re.finditer(
                r"(?m)^diff --git a/\S+ b/(\S+)$",
                patch.read_text(encoding="utf-8", errors="surrogateescape"),
            )
        }
        assert set(parsed) == declared, patch


def test_plain_unified_headers_and_file_creation_are_parsed(tmp_path):
    patch = tmp_path / "plain.patch"
    patch.write_text(
        "Preamble.\n"
        "--- a/existing.cpp\n"
        "+++ b/existing.cpp\n"
        "@@ -1 +1 @@\n"
        "-old\n"
        "+new\n"
        "--- /dev/null\n"
        "+++ b/new.txt\n"
        "@@ -0,0 +1 @@\n"
        "+created\n"
    )
    assert set(patchstack.sections(patch)) == {"existing.cpp", "new.txt"}


def _patch_probe(tmp_path: Path, patch_text: str) -> subprocess.CompletedProcess:
    root = tmp_path / "tree"
    root.mkdir()
    (root / "file.txt").write_text("one\ntwo\nthree\nfour\nfive\nsix\n")
    return patchstack.apply(patch_text, root)


def test_fuzz_is_a_hard_failure(tmp_path):
    result = _patch_probe(
        tmp_path,
        "--- a/file.txt\n"
        "+++ b/file.txt\n"
        "@@ -2,4 +2,4 @@\n"
        " TWO\n"
        "-three\n"
        "+THREE\n"
        " four\n"
        " FIVE\n",
    )
    assert result.returncode != 0


def test_a_reject_is_a_hard_failure(tmp_path):
    result = _patch_probe(
        tmp_path,
        "--- a/file.txt\n"
        "+++ b/file.txt\n"
        "@@ -1 +1 @@\n"
        "-absent\n"
        "+replacement\n",
    )
    assert result.returncode != 0


def test_verify_treats_fuzz_and_rejects_as_failures(tmp_path, capsys):
    root = tmp_path / "tree"
    root.mkdir()
    (root / "file.txt").write_text("one\ntwo\nthree\nfour\nfive\nsix\n")
    patch_text = (
        "--- a/file.txt\n"
        "+++ b/file.txt\n"
        "@@ -2,4 +2,4 @@\n"
        " TWO\n"
        "-three\n"
        "+THREE\n"
        " four\n"
        " FIVE\n"
    )
    assert not patchstack._apply_or_fail("fuzz.patch", patch_text, root)
    assert "FAIL fuzz.patch" in capsys.readouterr().out


def test_host_target_detection_covers_native_platforms(monkeypatch):
    cases = [
        (("Linux", "x86_64"), ("linux", "x86_64")),
        (("Linux", "aarch64"), ("linux", "arm64")),
        (("Darwin", "arm64"), ("macos", "arm64")),
        (("Windows", "AMD64"), ("windows", "x86_64")),
        (("Windows", "x86"), ("windows", "i686")),
    ]
    for (system, machine), expected in cases:
        monkeypatch.setattr("platform.system", lambda system=system: system)
        monkeypatch.setattr("platform.machine", lambda machine=machine: machine)
        assert _mixin.host_build_target() == expected


def test_unknown_host_targets_fail_loudly(monkeypatch):
    monkeypatch.setattr("platform.system", lambda: "Plan9")
    try:
        _mixin.host_build_target()
    except ValueError as error:
        assert "Plan9" in str(error)
    else:
        raise AssertionError("unsupported hosts must not be guessed")


def test_dir_reset_preserves_object_directories(tmp_path):
    tree = tmp_path / "tree"
    tree.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=tree, check=True)
    (tree / "tracked").write_text("patched\n")
    subprocess.run(["git", "add", "tracked"], cwd=tree, check=True)
    subprocess.run(
        ["git", "-c", "user.name=Test", "-c", "user.email=test@example.com",
         "commit", "-q", "-m", "base"],
        cwd=tree,
        check=True,
    )
    subprocess.run(["git", "tag", "unpatched"], cwd=tree, check=True)
    (tree / "tracked").write_text("working\n")
    (tree / "obj-linux").mkdir()
    (tree / "obj-linux/keep").write_text("object\n")
    (tree / "scratch").write_text("remove\n")

    script = (
        "import sys; "
        f"sys.path.insert(0, {str(SCRIPTS)!r}); "
        "sys.argv = ['patch.py', '1.0', 'test']; "
        "import patch; patch.reset_to_unpatched()"
    )
    subprocess.run([sys.executable, "-c", script], cwd=tree, check=True)
    assert (tree / "tracked").read_text() == "patched\n"
    assert (tree / "obj-linux/keep").is_file()
    assert not (tree / "scratch").exists()


def test_set_target_keeps_the_patch_tree_and_objdir(tmp_path):
    browser = tmp_path / "browser"
    tree = browser / "camoufox-1.0-test"
    (browser / "assets").mkdir(parents=True)
    tree.mkdir()
    (tree / "configure.py").write_text("")
    (tree / "patch-sentinel").write_text("applied\n")
    (tree / "obj-linux").mkdir()
    (tree / "obj-linux/keep").write_text("object\n")
    (tree / "mozconfig.backup").write_text("old base\n")
    (browser / "assets/base.mozconfig").write_text("new base\n")
    (browser / "assets/linux.mozconfig").write_text("linux target\n")
    script = (
        "import sys; "
        f"sys.path.insert(0, {str(SCRIPTS)!r}); "
        "sys.argv = ['patch.py', '1.0', 'test', '--mozconfig-only']; "
        "import patch; "
        "patch.Patcher('x86_64-pc-linux-gnu', 'linux', '1.95.0', '/pgo').camoufox_patches()"
    )
    subprocess.run([sys.executable, "-c", script], cwd=browser, check=True)
    assert (tree / "patch-sentinel").read_text() == "applied\n"
    assert (tree / "obj-linux/keep").read_text() == "object\n"
    mozconfig = (tree / "mozconfig").read_text()
    assert "\nnew base\n" in mozconfig and "old base" not in mozconfig
    assert mozconfig.startswith("CAMOUFOX_TARGET=x86_64-pc-linux-gnu\nCAMOUFOX_PGO_PROFILE=/pgo\n")


def test_regen_refuses_a_file_touched_by_a_later_patch(tmp_path, monkeypatch):
    first = tmp_path / "first.patch"
    second = tmp_path / "second.patch"
    body = "--- a/file.txt\n+++ b/file.txt\n@@ -1 +1 @@\n-a\n+b\n"
    first.write_text(body)
    second.write_text(body.replace("-a\n+b", "-b\n+c"))
    monkeypatch.setattr(patchstack, "ordered_patches", lambda: [first, second])
    monkeypatch.setattr(patchstack, "REPO", tmp_path)

    try:
        patchstack.regen(str(first))
    except SystemExit as error:
        assert "also touches" in str(error)
    else:
        raise AssertionError("regen must not mix a later patch into the target")


def test_regen_diff_preserves_creation_and_deletion_headers(tmp_path):
    base = tmp_path / "base.txt"
    actual = tmp_path / "actual.txt"
    base.write_text("old\n")
    actual.write_text("new\n")
    changed = patchstack._diff_file(base, actual, "src/file.txt")
    assert "--- a/src/file.txt" in changed
    assert "+++ b/src/file.txt" in changed
    assert str(tmp_path) not in changed

    deleted = patchstack._diff_file(base, tmp_path / "missing.txt", "src/file.txt")
    assert "--- a/src/file.txt" in deleted
    assert "+++ /dev/null" in deleted

    created = patchstack._diff_file(tmp_path / "missing.txt", actual, "src/file.txt")
    assert "--- /dev/null" in created
    assert "+++ b/src/file.txt" in created


def test_sync_leaves_unchanged_files_and_patched_moz_build_alone(tmp_path):
    fake = tmp_path / "browser"
    (fake / "scripts").mkdir(parents=True)
    shutil.copy2(SCRIPTS / "sync_additions.py", fake / "scripts")
    (fake / "upstream.sh").write_text("version=1.0\nrelease=test\n")
    for path, content in {
        "additions/example.txt": "example\n",
        "settings/camoufox.cfg": "pref\n",
        "settings/distribution/policies.json": "{}\n",
        "settings/defaults/pref/local-settings.js": "// pref\n",
        "settings/properties.json": "[]\n",
        "additions/browser/branding/camoufox/Assets.car": "asset\n",
    }.items():
        target = fake / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)

    tree = tmp_path / "camoufox-1-test"
    (tree / "browser/config").mkdir(parents=True)
    (tree / "configure.py").write_text("")
    (tree / "lw").mkdir()
    (tree / "lw/moz.build").write_text("patched\n")

    command = [sys.executable, str(fake / "scripts/sync_additions.py"), str(tree)]
    first = subprocess.run(command, capture_output=True, text=True, check=True)
    assert "6 file(s) changed" in first.stdout
    source_mtime = (tree / "example.txt").stat().st_mtime_ns
    mozbuild = (tree / "lw/moz.build").read_text()

    second = subprocess.run(command, capture_output=True, text=True, check=True)
    assert "0 file(s) changed" in second.stdout
    assert (tree / "example.txt").stat().st_mtime_ns == source_mtime
    assert (tree / "lw/moz.build").read_text() == mozbuild == "patched\n"


def test_compiler_cache_selection_keeps_release_configuration(tmp_path):
    scripts = tmp_path / "bin"
    scripts.mkdir()
    sccache = scripts / "sccache"
    sccache.write_text("#!/bin/sh\nexit 0\n")
    sccache.chmod(0o755)
    shell = (
        "ac_add_options(){ echo \"$*\"; }; mk_add_options(){ :; }; "
        f". {BROWSER / 'assets/base.mozconfig'}; "
        "printf 'CCACHE_MAXSIZE=%s\\nSCCACHE_CACHE_SIZE=%s\\nRUSTC_WRAPPER=%s\\n' "
        "\"$CCACHE_MAXSIZE\" \"$SCCACHE_CACHE_SIZE\" \"$RUSTC_WRAPPER\""
    )
    result = subprocess.run(
        ["bash", "-c", shell],
        env={
            "HOME": str(tmp_path),
            "PATH": f"{scripts}:/usr/bin:/bin",
            "CAMOUFOX_SCCACHE": "1",
        },
        capture_output=True,
        text=True,
        check=True,
    )
    assert "enable-release" in result.stdout
    assert "with-ccache=sccache" in result.stdout
    assert "CCACHE_MAXSIZE=20G" in result.stdout
    assert "SCCACHE_CACHE_SIZE=20G" in result.stdout
    assert f"RUSTC_WRAPPER={sccache}" in result.stdout


def test_ccache_remains_the_default_when_both_compilers_are_available(tmp_path):
    scripts = tmp_path / "bin"
    scripts.mkdir()
    for name in ("sccache", "ccache"):
        compiler_cache = scripts / name
        compiler_cache.write_text("#!/bin/sh\nexit 0\n")
        compiler_cache.chmod(0o755)
    shell = (
        "ac_add_options(){ echo \"$*\"; }; mk_add_options(){ :; }; "
        f". {BROWSER / 'assets/base.mozconfig'}"
    )
    result = subprocess.run(
        ["bash", "-c", shell],
        env={"HOME": str(tmp_path), "PATH": f"{scripts}:/usr/bin:/bin"},
        capture_output=True,
        text=True,
        check=True,
    )
    assert "with-ccache=ccache" in result.stdout
    assert "with-ccache=sccache" not in result.stdout


def test_docker_persists_both_compiler_caches():
    dockerfile = (BROWSER / "Dockerfile").read_text(encoding="utf-8")
    assert "CCACHE_DIR=/root/.mozbuild/ccache" in dockerfile
    assert "SCCACHE_DIR=/root/.mozbuild/sccache-cache" in dockerfile
