#!/usr/bin/env python3
"""
Check SkCpuEstimates.h with the shipped tables against real CPUs.

    python3 browser/tests/cpu-estimates/check.py
    python3 browser/tests/cpu-estimates/check.py --bench

--bench only times the native instructions against both vendors' emulation
(ns per vector, data in L1), and needs an AVX2 host.

On an Intel or AMD host, the emulation of the host's vendor must give the
native RCPPS/RSQRTPS bits for every one of the 2^32 inputs. For both vendors,
the emulation's hashes over all inputs must equal the native hashes recorded on
that vendor's CPU (provenance.json), so one host checks the other vendor too.
On an AVX2 host, the SSE2 and AVX2 versions the raster pipeline runs must give
the scalar functions' bits for every input and both vendors.
A few minutes on one core.
"""

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from record import PROVENANCE, VENDORS, build  # noqa: E402


def host_has_avx2():
    try:
        return any(line.startswith("flags") and " avx2" in line
                   for line in Path("/proc/cpuinfo").read_text().splitlines())
    except OSError:
        return False


def bench():
    if not host_has_avx2():
        sys.exit("--bench needs an AVX2 host")
    vexe = build(tables=True, avx2=True)
    for index, vendor in VENDORS.items():
        print(f"{vendor} emulation:", flush=True)
        subprocess.run([vexe, "bench", index], check=True)


def main():
    if "--bench" in sys.argv[1:]:
        bench()
        return
    exe = build(tables=True)
    prov = json.loads(PROVENANCE.read_text())
    failed = False
    for index, vendor in VENDORS.items():
        out = subprocess.run([exe, "hash", index], capture_output=True, text=True, check=True).stdout.split()
        got = dict(zip(out[::2], out[1::2]))
        ok = got == prov[vendor]["hashes"]
        failed |= not ok
        print(f"{vendor}: emulated {got}, recorded {prov[vendor]['hashes']}: {'ok' if ok else 'MISMATCH'}")
    host = subprocess.run([exe, "vendor"], capture_output=True, text=True, check=True).stdout.strip()
    if host in VENDORS:
        run = subprocess.run([exe, "check", host], capture_output=True, text=True)
        print(f"host ({VENDORS[host]}) native vs emulated:\n{run.stdout.strip()}")
        failed |= run.returncode != 0
    else:
        print("host is neither Intel nor AMD: native comparison skipped")
    if host_has_avx2():
        vexe = build(tables=True, avx2=True)
        for index, vendor in VENDORS.items():
            run = subprocess.run([vexe, "vcheck", index], capture_output=True, text=True)
            print(f"{vendor} vector vs scalar:\n{run.stdout.strip()}")
            failed |= run.returncode != 0
    else:
        print("host has no AVX2: vector comparison skipped")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
