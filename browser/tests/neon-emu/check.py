#!/usr/bin/env python3
"""
Check SkNeonEmu.h's fast paths and shuffles against its lane-wise reference.

    python3 browser/tests/neon-emu/check.py [--quick]

Builds impl.cpp three ways with clang (the compiler Firefox builds Skia with):
the reference (NEON_EMU_REFERENCE) and the shipped HSW build with AVX2, FMA
and F16C, and the shipped baseline x86-64 build. Every operation with a fast
path or a shuffle must give the reference's bytes in both shipped builds:
unary float operations over all 2^32 inputs, the rest over special-heavy
random vectors (main.cpp). Prints ns per vector for each build. Needs an
x86-64 host with AVX2, FMA and F16C; about a minute.
"""

import argparse
import os
import platform
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKIA = HERE.parents[1] / "additions" / "gfx" / "skia" / "skia"
HSW = ["-mavx2", "-mfma", "-mf16c"]
BUILDS = {"ref": HSW + ["-DNEON_EMU_REFERENCE"], "fast": HSW, "base": []}


def host_supports_hsw():
    try:
        flags = next(line for line in Path("/proc/cpuinfo").read_text().splitlines() if line.startswith("flags"))
    except (OSError, StopIteration):
        return False
    have = set(flags.split(":", 1)[1].split())
    return {"avx2", "fma", "f16c"} <= have


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--quick", action="store_true", help="sample the exhaustive sweeps")
    args = ap.parse_args()
    cxx = os.environ.get("CXX") or shutil.which("clang++")
    if platform.machine().lower() not in ("x86_64", "amd64") or not cxx:
        sys.exit("needs an x86-64 host with clang++")
    if not host_supports_hsw():
        sys.exit("needs AVX2, FMA and F16C")
    out = Path(tempfile.mkdtemp(prefix="neon-emu-"))
    common = ["-std=c++17", "-O3", "-Wall", "-Werror", f"-I{SKIA}", f"-I{HERE}"]
    objs = []
    for ns, flags in BUILDS.items():
        obj = out / f"{ns}.o"
        subprocess.run([cxx, *common, *flags, f"-DNS={ns}", "-c", str(HERE / "impl.cpp"), "-o", str(obj)], check=True)
        objs.append(str(obj))
    exe = out / "neon-emu-check"
    subprocess.run([cxx, *common, str(HERE / "main.cpp"), *objs, "-o", str(exe)], check=True)
    sys.exit(subprocess.run([str(exe)] + (["quick"] if args.quick else [])).returncode)


if __name__ == "__main__":
    main()
