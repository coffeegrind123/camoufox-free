"""
Computing as another CPU costs no more time than computing as the host.

general.cpu_identity (cpu-vendor-estimates.patch) makes canvas, Web Audio and
Opus give another CPU's bits: the other x86 vendor's RCPPS/RSQRTPS (1 Intel,
2 AMD) or Skia's, libopus's and Web Audio's AArch64 code (3). Bit-exact is not
enough: a page that times a canvas blend sees the emulation when it is slower
than the instruction it replaces. On PR #37's build (GitHub Zen 4 runner) the
Intel emulation drew color-dodge 3.3x and color-burn 4.7x slower than native,
and ARM64 drew source-over 22x and the non-separable blends 58-87x slower; an
Apple M chip draws them in about a millisecond. The vectorised estimates
(SkCpuEstimates.h) and SkNeonEmu.h's fast paths in the HSW build of the
emulated tier are what keep it fast; this guard keeps them from regressing.

The same page runs under the host's own identity (0), the other x86 vendor
and ARM64, in interleaved launches on one machine, so a busy runner slows all
three alike. Each operation's time is the median over launches of the median
over repetitions. The guard fails when an emulated operation takes more than
SLOWER_FACTOR times the host's and at least MIN_GAP_MS more.

    python browser/tests/playwright/patches/cpu-emulation-timing.py
"""

import json
import platform
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from helpers import launch_kwargs  # noqa: E402

LAUNCHES = 3
SLOWER_FACTOR = {"x86 vendor": 1.3, "arm64": 1.5}
MIN_GAP_MS = 0.3
PAGE = "https://cpu-emulation-timing.test/"
PAGE_TIMEOUT_MS = 240_000

# Each entry: ms per operation, median of the repetitions in one launch. It
# runs as the page's own script: Playwright's isolated world may not touch
# typed-array data (AudioBuffer.getChannelData), so the result comes back as
# JSON on <html data-bench>.
BENCH = """async () => {
  const now = () => performance.now();
  const median = (a) => a.slice().sort((x, y) => x - y)[a.length >> 1];
  const out = {};
  const N = 512;
  const src = new OffscreenCanvas(N, N), sg = src.getContext("2d");
  const g = sg.createLinearGradient(0, 0, N, N);
  g.addColorStop(0, "rgba(19,165,240,0.9)"); g.addColorStop(0.5, "rgba(240,165,19,0.6)"); g.addColorStop(1, "rgba(122,19,240,0.8)");
  sg.fillStyle = g; sg.fillRect(0, 0, N, N);
  const dst = new OffscreenCanvas(N, N), dg = dst.getContext("2d");
  // performance.now() is clamped to 1 ms, so each sample repeats the
  // operation until about SAMPLE_MS have passed (the count set once, from a
  // calibration run), and reports the time per operation.
  const SAMPLE_MS = 100;
  const draw = (name, setup, op, reps = 7) => {
    const run = (count) => {
      dg.setTransform(1, 0, 0, 1, 0, 0);
      dg.globalCompositeOperation = "source-over";
      dg.fillStyle = "#808080"; dg.fillRect(0, 0, N, N);
      setup();
      const a = now();
      for (let k = 0; k < count; k++) op(k);
      dg.getImageData(0, 0, 1, 1);
      return now() - a;
    };
    let count = 1;
    while (count < 1 << 14) { const ms = run(count); if (ms >= SAMPLE_MS / 4) { count = Math.ceil(count * SAMPLE_MS / ms); break; } count *= 4; }
    const t = [];
    for (let r = 0; r < reps; r++) t.push(run(count) / count);
    out[name] = median(t);
  };
  for (const mode of ["source-over", "multiply", "screen", "color-dodge", "color-burn", "soft-light",
                      "hue", "saturation", "color", "luminosity"]) {
    draw("canvas:" + mode, () => { dg.globalCompositeOperation = mode; }, (k) => dg.drawImage(src, k, k));
  }
  // Bilinear sampling under a rotation and scale: the highp pipeline's
  // gather, floor and fused multiply-adds.
  draw("canvas:drawImage-rotated", () => { dg.setTransform(0.9, 0.3, -0.3, 0.9, 80, -40); dg.imageSmoothingQuality = "high"; },
       (k) => dg.drawImage(src, k, k, N * 0.8, N * 0.8));
  // Anti-aliased paths and a radial gradient.
  draw("canvas:path-radial", () => {
    const rg = dg.createRadialGradient(N / 2, N / 2, 10, N / 2, N / 2, N / 2);
    rg.addColorStop(0, "rgba(255,0,0,0.7)"); rg.addColorStop(1, "rgba(0,0,255,0.4)");
    dg.fillStyle = rg;
  }, (k) => {
    dg.beginPath();
    for (let i = 0; i < 60; i++) dg.lineTo(N / 2 + Math.cos(i * 2.4 + k) * (N / 2 - i), N / 2 + Math.sin(i * 2.4 + k) * (N / 2 - i));
    dg.fill();
  });

  {
    const t = [];
    for (let r = 0; r < 5; r++) {
      const ctx = new OfflineAudioContext(2, 48000 * 8, 48000);
      const osc = ctx.createOscillator(); osc.type = "sawtooth"; osc.frequency.value = 220;
      const bq = ctx.createBiquadFilter(); bq.frequency.value = 1200;
      const conv = ctx.createConvolver();
      const ir = ctx.createBuffer(2, 4096, 48000);
      for (let c = 0; c < 2; c++) { const d = ir.getChannelData(c); for (let i = 0; i < d.length; i++) d[i] = Math.sin(i * (c + 1) * 0.37) * Math.exp(-i / 900); }
      conv.buffer = ir;
      const comp = ctx.createDynamicsCompressor();
      const pan = ctx.createPanner(); pan.panningModel = "HRTF"; pan.positionX.value = 1;
      const gain = ctx.createGain(); gain.gain.value = 0.7;
      osc.connect(bq).connect(conv).connect(comp).connect(pan).connect(gain).connect(ctx.destination);
      osc.start();
      const a = now();
      await ctx.startRendering();
      t.push(now() - a);
    }
    out.webaudio = median(t);
  }

  if (typeof AudioEncoder !== "undefined") {
    const t = [];
    const frames = 48000 * 8, data = new Float32Array(frames);
    for (let i = 0; i < frames; i++) data[i] = 0.5 * Math.sin(i * 0.031) + 0.3 * Math.sin(i * 0.0071 + Math.sin(i * 0.0003));
    for (let r = 0; r < 5; r++) {
      let err = null;
      const enc = new AudioEncoder({ output: () => {}, error: (e) => { err = e; } });
      enc.configure({ codec: "opus", sampleRate: 48000, numberOfChannels: 1, bitrate: 64000 });
      const a = now();
      for (let off = 0; off < frames; off += 960)
        enc.encode(new AudioData({ format: "f32", sampleRate: 48000, numberOfFrames: 960, numberOfChannels: 1,
                                   timestamp: off * 1e6 / 48000 | 0, data: data.subarray(off, off + 960) }));
      await enc.flush();
      t.push(now() - a);
      enc.close();
      if (err) throw err;
    }
    out.opus = median(t);
  }
  return out;
}"""


def host_vendor() -> str:
    try:
        for line in Path("/proc/cpuinfo").read_text().splitlines():
            if line.startswith("vendor_id"):
                return {"GenuineIntel": "intel", "AuthenticAMD": "amd"}.get(line.split(":", 1)[1].strip(), "")
    except OSError:
        pass
    return ""


HTML = """<!doctype html><p>x</p><script>
(%s)().then(r => { document.documentElement.dataset.bench = JSON.stringify(r); },
            e => { document.documentElement.dataset.bench = JSON.stringify({error: String(e)}); });
</script>""" % BENCH


def measure(pref: int) -> dict:
    from camoufox.sync_api import Camoufox

    with Camoufox(**launch_kwargs(os="linux", firefox_user_prefs={"general.cpu_identity": pref})) as browser:
        page = browser.new_page()
        # WebCodecs needs a secure context; about:blank is not one.
        page.route(PAGE, lambda route: route.fulfill(body=HTML, content_type="text/html"))
        page.goto(PAGE)
        page.wait_for_function("document.documentElement.dataset.bench", timeout=PAGE_TIMEOUT_MS)
        result = json.loads(page.evaluate("document.documentElement.dataset.bench"))
    if "error" in result:
        raise RuntimeError(f"general.cpu_identity {pref}: the bench threw {result['error']}")
    return result


def main() -> int:
    host = host_vendor()
    if platform.machine().lower() not in ("x86_64", "amd64") or not host:
        print(f"FAIL: needs an Intel or AMD x86-64 host, not {platform.machine()} {platform.processor()!r}")
        return 1
    other = {"intel": ("amd", 2), "amd": ("intel", 1)}[host]
    identities = {"host": 0, f"{other[0]} (x86 vendor)": other[1], "arm64": 3}

    runs = {name: [] for name in identities}
    for launch in range(LAUNCHES):
        for name, pref in identities.items():
            runs[name].append(measure(pref))
    ms = {name: {k: statistics.median(r[k] for r in rs) for k in rs[0]} for name, rs in runs.items()}

    failures = []
    keys = list(ms["host"])
    print(f"  {'ms per operation':26} " + " ".join(f"{n.split()[0]:>14}" for n in identities))
    for key in keys:
        cells = [f"{ms['host'][key]:14.2f}"]
        for name in list(identities)[1:]:
            got, base = ms[name][key], ms["host"][key]
            ratio = got / base if base else float("inf")
            cells.append(f"{got:7.2f} {ratio:5.2f}x")
            factor = SLOWER_FACTOR["arm64" if name == "arm64" else "x86 vendor"]
            if ratio > factor and got - base >= MIN_GAP_MS:
                failures.append(f"{name}: {key} {got:.2f} ms, {ratio:.2f}x the host's {base:.2f} ms (limit {factor}x)")
        print(f"  {key:26} " + " ".join(cells))

    for failure in failures:
        print(f"FAIL: {failure}")
    if failures:
        return 1
    print(f"PASS: on this {host} host, computing as the other x86 vendor or as ARM64 costs no more than "
          f"{max(SLOWER_FACTOR.values())}x the host's own time.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
