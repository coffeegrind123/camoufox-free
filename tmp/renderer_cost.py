"""Throwaway: the WebGL renderer-string getter's cost, stock vs Camoufox.

Per launch (session) it times getParameter(RENDERER) and (UNMASKED_RENDERER)
five times, 300 ms apart, plus two controls, and records the strings returned
and the helper process types alive. Launches alternate stock / Camoufox so a
runner's drift hits both. Prints every sample, then per-browser distributions.

    renderer_cost.py <camoufox-bin> [launches]
"""
import importlib.util, json, statistics, subprocess, sys, threading, time, urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
GUARD_DIR = HERE.parent / "browser" / "tests" / "playwright" / "patches"
sys.path.insert(0, str(GUARD_DIR))
spec = importlib.util.spec_from_file_location("gcp", GUARD_DIR / "getter-cost-parity.py")
gcp = importlib.util.module_from_spec(spec); spec.loader.exec_module(gcp)
from helpers import hidden_display  # noqa: E402

EXPRS = ["G.getParameter(G.RENDERER)", "G.getParameter(37446)",
         "G.getParameter(G.VENDOR)", "G.getParameter(G.MAX_TEXTURE_SIZE)", "screen.orientation.type"]

PAGE = """<!doctype html><meta charset=utf-8><body><script>
const EXPRS = %s;
const G = document.createElement('canvas').getContext('webgl');
const ext = G && G.getExtension('WEBGL_debug_renderer_info');
const mk = (e) => new Function('G', 'N', 'let t = performance.now(); let x; for (let i = 0; i < N; i++) { x = (' + e + '); } return performance.now() - t;');
const empty = mk('i');
const best = (f, N) => { let b = Infinity; for (let r = 0; r < 7; r++) b = Math.min(b, f(G, N)); return b; };
function round() {
  const out = {};
  for (const e of EXPRS) {
    const f = mk(e); f(G, 10);
    let N = 100; while (N < 5e6 && f(G, N) < 25) N *= 4;
    out[e] = Math.max(0, best(f, N) - best(empty, N)) * 1e6 / N;
  }
  return out;
}
(async () => {
  if (!G) throw new Error('no webgl');
  const rounds = [];
  for (let k = 0; k < 5; k++) { rounds.push(round()); await new Promise(r => setTimeout(r, 300)); }
  const res = {rounds, renderer: G.getParameter(G.RENDERER), unmasked: G.getParameter(37446),
               vendor: G.getParameter(G.VENDOR), unmaskedVendor: G.getParameter(37445)};
  document.body.dataset.result = JSON.stringify(res);
  fetch('/result', {method: 'POST', body: JSON.stringify(res)});
})().catch(e => { const res = {error: String(e)}; document.body.dataset.result = JSON.stringify(res);
                  fetch('/result', {method: 'POST', body: JSON.stringify(res)}); });
</script></body>""" % json.dumps(EXPRS)


class Handler(gcp.Handler):
    def do_GET(self):
        body = PAGE.encode()
        self.send_response(200); self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)


def proc_types(marker):
    """Child process types of the browser whose command lines contain marker."""
    out = subprocess.run(["ps", "-eo", "args"], capture_output=True, text=True).stdout.splitlines()
    kinds = [l.split()[-1] for l in out if "-contentproc" in l and (marker is None or marker in l)]
    return sorted(set(kinds)), len(kinds)


def main():
    camou_bin = Path(sys.argv[1]); launches = int(sys.argv[2]) if len(sys.argv) > 2 else 10
    stock_bin = gcp.stock_firefox()
    server = gcp.Server(("127.0.0.1", 0), Handler); server.results = []
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{server.server_address[1]}/"
    samples = {"stock": [], "camoufox": []}
    for i in range(launches):
        # stock
        server.results = []
        profile, proc = gcp.run_stock(stock_bin, url)
        deadline = time.time() + 120
        while not server.results and time.time() < deadline:
            time.sleep(0.3)
        kinds = proc_types(profile)
        gcp.stop_stock(profile, proc)
        r = server.results[0] if server.results else {"error": "no report"}
        r["procs"] = kinds; samples["stock"].append(r)
        print("stock", i, json.dumps(r)[:900], flush=True)
        # camoufox (the guard's launch-identity path), process types read mid-run
        holder = {}
        def snap():
            time.sleep(4); holder["procs"] = proc_types("camoufox")
        t = threading.Thread(target=snap); t.start()
        try:
            r = gcp.run_camoufox(camou_bin, url, "launch")
        except SystemExit as e:
            r = {"error": str(e)}
        t.join(); r["procs"] = holder.get("procs"); samples["camoufox"].append(r)
        print("camoufox", i, json.dumps(r)[:900], flush=True)
    server.shutdown()

    print("\n=== per session: median of 5 in-session rounds (us); in-session min-max")
    for e in EXPRS:
        print(f"\n{e}")
        for name, rs in samples.items():
            meds = []
            for r in rs:
                if "rounds" not in r:
                    continue
                v = [x[e] / 1000 for x in r["rounds"]]
                meds.append(statistics.median(v))
                print(f"  {name:9s} med {statistics.median(v):8.3f}  range {min(v):8.3f}-{max(v):8.3f}")
            if meds:
                print(f"  {name:9s} ACROSS SESSIONS: min {min(meds):.3f} median {statistics.median(meds):.3f} max {max(meds):.3f}  n={len(meds)}")
    for name, rs in samples.items():
        strs = {(r.get('renderer'), r.get('unmasked'), r.get('vendor'), r.get('unmaskedVendor')) for r in rs if 'rounds' in r}
        procs = {json.dumps(r.get('procs')) for r in rs}
        print(f"\n{name}: strings {strs}\n{name}: process types {procs}")


if __name__ == "__main__":
    with hidden_display():
        main()
