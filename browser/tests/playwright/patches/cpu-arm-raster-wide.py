"""
The wide ARM64 raster tier draws what the 4-wide emulated one draws.

With general.cpu_identity = ARM64 on a CPU with AVX2, FMA and F16C, Skia's
raster pipeline runs at AVX2's width with the AArch64 tier's helpers
(SkOpts_armhsw.cpp, SKRP_ARM_SEMANTICS in cpu-vendor-estimates.patch): a pixel
does not depend on how many are computed at once, and every helper whose
AArch64 definition differs from AVX2's is that definition, run through
SkNeonEmu.h. MOZ_CAMOUFOX_ARM_RASTER_NARROW keeps the 4-wide emulated tier
(SkOpts_neonemu_hsw.cpp), which the cpu-vendor-estimates guard checks against
stock Firefox on an Apple M4.

This guard draws a battery that reaches the pipeline's helpers -- every
composite operation over translucent gradients, scaled and rotated drawImage
at each smoothing quality, linear, radial and conic gradients, shadows, the
CSS filters, paths, text and createImageBitmap resizing -- under both tiers and
requires every hash to match.

    python browser/tests/playwright/patches/cpu-arm-raster-wide.py
"""

import os
import platform
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from helpers import launch_kwargs  # noqa: E402

NARROW = "MOZ_CAMOUFOX_ARM_RASTER_NARROW"

BATTERY = """async () => {
  const fnv = (d) => { let h = 0x811c9dc5; for (let i = 0; i < d.length; i++) { h ^= d[i]; h = Math.imul(h, 0x01000193) >>> 0; } return h.toString(16).padStart(8, "0"); };
  const W = 173, H = 131;  // odd sizes: partial vectors at every row end
  const canvas = () => { const c = new OffscreenCanvas(W, H); return [c, c.getContext("2d")]; };
  const hash = (ctx) => fnv(ctx.getImageData(0, 0, W, H).data);
  const base = (ctx) => {
    const g = ctx.createLinearGradient(0, 0, W, H);
    g.addColorStop(0, "rgba(250,30,90,0.85)"); g.addColorStop(0.4, "rgba(40,200,120,0.6)"); g.addColorStop(1, "rgba(20,60,240,0.95)");
    ctx.fillStyle = g; ctx.fillRect(0, 0, W, H);
  };
  const over = (ctx) => {
    const g = ctx.createRadialGradient(W / 3, H / 2, 3, W / 2, H / 2, W / 1.5);
    g.addColorStop(0, "rgba(255,220,0,0.8)"); g.addColorStop(0.5, "rgba(0,0,0,0.3)"); g.addColorStop(1, "rgba(0,120,255,0.55)");
    ctx.fillStyle = g; ctx.fillRect(0, 0, W, H);
  };
  const out = {};
  for (const op of ["source-over", "source-in", "source-out", "source-atop", "destination-over", "destination-in",
                    "destination-out", "destination-atop", "lighter", "copy", "xor", "multiply", "screen", "overlay",
                    "darken", "lighten", "color-dodge", "color-burn", "hard-light", "soft-light", "difference",
                    "exclusion", "hue", "saturation", "color", "luminosity"]) {
    const [, ctx] = canvas(); base(ctx); ctx.globalCompositeOperation = op; over(ctx); out["op:" + op] = hash(ctx);
  }
  const [src, sctx] = canvas(); base(sctx); over(sctx);
  for (const q of ["low", "medium", "high"]) {
    for (const [name, m] of [["scale", [1.37, 0, 0, 0.71, 3.5, -2.25]], ["rotate", [0.86, 0.5, -0.5, 0.86, 40, -20]],
                             ["perspective-ish", [0.3, 0.05, -0.02, 1.9, 10, 5]]]) {
      const [, ctx] = canvas(); ctx.imageSmoothingQuality = q; ctx.setTransform(...m); ctx.drawImage(src, 0, 0);
      out[`draw:${name}:${q}`] = hash(ctx);
    }
  }
  { const [, ctx] = canvas(); ctx.imageSmoothingEnabled = false; ctx.setTransform(2.3, 0.2, 0.1, 1.7, -5, 3); ctx.drawImage(src, 0, 0); out["draw:nearest"] = hash(ctx); }
  { const [, ctx] = canvas(); const g = ctx.createConicGradient(1.1, W / 2, H / 2);
    for (let i = 0; i <= 12; i++) g.addColorStop(i / 12, `hsla(${i * 30},80%,50%,${0.3 + i / 20})`);
    ctx.fillStyle = g; ctx.fillRect(0, 0, W, H); out["gradient:conic"] = hash(ctx); }
  { const [, ctx] = canvas(); const g = ctx.createLinearGradient(0, 0, W, 0);
    for (let i = 0; i < 9; i++) g.addColorStop(i / 8, i % 2 ? "#0f08" : "#f0fc");
    ctx.fillStyle = g; ctx.fillRect(0, 0, W, H); out["gradient:9stops"] = hash(ctx); }
  { const [, ctx] = canvas(); base(ctx); ctx.shadowColor = "rgba(0,0,0,0.7)"; ctx.shadowBlur = 9; ctx.shadowOffsetX = 4;
    ctx.fillStyle = "rgba(255,255,255,0.6)"; ctx.fillRect(30, 30, 80, 50); out["shadow"] = hash(ctx); }
  for (const f of ["blur(3px)", "contrast(170%) brightness(80%)", "hue-rotate(77deg) saturate(150%)", "sepia(60%) invert(30%)",
                   "grayscale(80%) opacity(70%)", "drop-shadow(3px 4px 5px rgba(0,0,0,.6))"]) {
    const [, ctx] = canvas(); ctx.filter = f; ctx.drawImage(src, 0, 0); out["filter:" + f] = hash(ctx);
  }
  { const [, ctx] = canvas(); base(ctx); ctx.beginPath();
    for (let i = 0; i < 40; i++) ctx.lineTo(W / 2 + Math.cos(i * 2.4) * (W / 2 - i), H / 2 + Math.sin(i * 2.4) * (H / 2 - i));
    ctx.fillStyle = "rgba(10,10,200,0.5)"; ctx.fill("evenodd"); ctx.lineWidth = 2.7; ctx.strokeStyle = "rgba(255,0,0,0.7)"; ctx.stroke();
    out["path"] = hash(ctx); }
  { const [, ctx] = canvas(); base(ctx); ctx.font = "19px sans-serif"; ctx.fillStyle = "rgba(255,255,255,0.8)";
    ctx.rotate(0.13); ctx.fillText("Pack my box with five dozen", 4, 40); out["text"] = hash(ctx); }
  for (const q of ["pixelated", "low", "high"]) {
    const bmp = await createImageBitmap(src, { resizeWidth: 97, resizeHeight: 211, resizeQuality: q });
    const [, ctx] = canvas(); ctx.drawImage(bmp, 0, 0); out["bitmap:" + q] = hash(ctx);
  }
  return out;
}"""


def draw(narrow: bool) -> dict:
    from camoufox.sync_api import Camoufox

    env = dict(os.environ)
    env.pop(NARROW, None)
    if narrow:
        env[NARROW] = "1"
    with Camoufox(**launch_kwargs(os="linux", env=env,
                                  firefox_user_prefs={"general.cpu_identity": 3})) as browser:
        page = browser.new_page()
        page.goto("about:blank")
        return page.evaluate(BATTERY)


def main() -> int:
    flags = ""
    try:
        flags = next(line for line in Path("/proc/cpuinfo").read_text().splitlines() if line.startswith("flags"))
    except (OSError, StopIteration):
        pass
    if platform.machine().lower() not in ("x86_64", "amd64") or not {"avx2", "fma", "f16c"} <= set(flags.split()):
        print(f"FAIL: needs an x86-64 host with AVX2, FMA and F16C, not {platform.machine()}")
        return 1

    wide, narrow = draw(False), draw(True)
    differ = sorted(k for k in narrow if wide.get(k) != narrow[k])
    if len(set(narrow.values())) < len(narrow) // 2:
        print(f"FAIL: the battery draws too few distinct images ({len(set(narrow.values()))} of {len(narrow)})")
        return 1
    for key in differ:
        print(f"FAIL: {key}: wide {wide.get(key)}, 4-wide {narrow[key]}")
    if differ:
        return 1
    print(f"PASS: the wide ARM64 tier draws all {len(narrow)} images as the 4-wide emulated tier does.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
