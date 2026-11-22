"""Launch with general.cpu_identity=<pref>, run <mode> in a loop for ~20 s (a canvas blend mode, or 'webaudio')."""
import sys
from camoufox.sync_api import Camoufox
pref, mode = int(sys.argv[1]), sys.argv[2]
CANVAS = """(mode) => { const N = 512; const src = new OffscreenCanvas(N, N), sg = src.getContext('2d');
const g = sg.createLinearGradient(0, 0, N, N); g.addColorStop(0, 'rgba(19,165,240,0.9)'); g.addColorStop(0.5, 'rgba(240,165,19,0.6)'); g.addColorStop(1, 'rgba(122,19,240,0.8)');
sg.fillStyle = g; sg.fillRect(0, 0, N, N); const dst = new OffscreenCanvas(N, N), dg = dst.getContext('2d');
dg.fillStyle = '#808080'; dg.fillRect(0, 0, N, N); dg.globalCompositeOperation = mode;
const t0 = performance.now(); let n = 0; while (performance.now() - t0 < 20000) { dg.drawImage(src, n & 7, n & 7); n++; }
dg.getImageData(0,0,1,1); return n; }"""
AUDIO = """async () => { const t0 = performance.now(); let n = 0;
while (performance.now() - t0 < 20000) {
  const ctx = new OfflineAudioContext(2, 48000 * 8, 48000);
  const osc = ctx.createOscillator(); osc.type = "sawtooth"; osc.frequency.value = 220;
  const bq = ctx.createBiquadFilter(); bq.frequency.value = 1200;
  const conv = ctx.createConvolver(); const ir = ctx.createBuffer(2, 4096, 48000);
  for (let c = 0; c < 2; c++) { const d = ir.getChannelData(c); for (let i = 0; i < d.length; i++) d[i] = Math.sin(i * (c + 1) * 0.37) * Math.exp(-i / 900); }
  conv.buffer = ir; const comp = ctx.createDynamicsCompressor();
  const pan = ctx.createPanner(); pan.panningModel = "HRTF"; pan.positionX.value = 1;
  const gain = ctx.createGain(); gain.gain.value = 0.7;
  osc.connect(bq).connect(conv).connect(comp).connect(pan).connect(gain).connect(ctx.destination);
  osc.start(); await ctx.startRendering(); n++; }
return n; }"""
with Camoufox(executable_path=sys.argv[3], os="linux", headless=True, i_know_what_im_doing=True,
              firefox_user_prefs={"general.cpu_identity": pref}) as b:
    p = b.new_page(); p.goto("about:blank")
    print("READY", flush=True)
    print(f"pref {pref} {mode}: runs in 20 s:", p.evaluate(AUDIO if mode == "webaudio" else CANVAS, mode), flush=True)
