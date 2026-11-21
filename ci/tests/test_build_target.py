"""browser/scripts/patch.py: BUILD_TARGET unset builds for this machine.

Defaulting to macos,arm64 configured a macOS cross-build that failed minutes
later on the missing SDK (upstream #1097). This fork defaults to the host's own
target instead (_mixin.host_build_target), which is linux,x86_64 on the
documented Linux build and never a cross-build.
"""

import pytest


@pytest.fixture
def patch_py(load_patch_py):
    return load_patch_py()


def test_unset_builds_for_this_machine(patch_py, monkeypatch):
    monkeypatch.delenv("BUILD_TARGET", raising=False)
    monkeypatch.setattr(patch_py, "host_build_target", lambda: ("linux", "x86_64"))
    assert patch_py.extract_build_target() == ("linux", "x86_64")


@pytest.mark.parametrize(
    "value, expected",
    [
        ("linux,x86_64", ("linux", "x86_64")),
        ("macos,arm64", ("macos", "arm64")),
        ("windows,i686", ("windows", "i686")),
    ],
)
def test_an_explicit_build_target_wins(patch_py, monkeypatch, value, expected):
    monkeypatch.setenv("BUILD_TARGET", value)
    assert patch_py.extract_build_target() == expected


@pytest.mark.parametrize("value", ["plan9,x86_64", "linux,riscv64"])
def test_an_unknown_target_or_arch_is_rejected(patch_py, monkeypatch, value):
    monkeypatch.setenv("BUILD_TARGET", value)
    with pytest.raises(ValueError, match="Unsupported"):
        patch_py.extract_build_target()
