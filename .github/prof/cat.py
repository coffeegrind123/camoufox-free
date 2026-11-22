import re, sys, collections
tot=collections.Counter(); n=collections.Counter()
for line in open(sys.argv[1]):
    m=re.match(r"^\s+([0-9]+\.[0-9]+)\s+:\s+([0-9a-f]+):\s+(\S+)\s*(.*)$", line)
    if not m: continue
    pct=float(m.group(1)); op=m.group(3); args=m.group(4)
    if pct == 0: continue
    if "(%rsp)" in args: c="stack " + ("store" if args.rstrip().endswith("(%rsp)") else "load")
    elif op.startswith("j"): c="branch"
    elif op in ("vtestps","vptest","vmovmskps","vpmovmskb","test","cmp","testl","cmpl","testq"): c="test"
    elif "cmp" in op: c="fp/int compare"
    elif op.startswith(("vfmadd","vfnmadd","vfmsub","vfnmsub")): c="fma"
    elif op in ("vaddps","vsubps","vmulps","vdivps","vrcpps","vsqrtps"): c="fp arith"
    elif op in ("vminps","vmaxps"): c="minmax"
    elif op.startswith("vblendv") or op in ("vandps","vorps","vxorps","vandnps","vpand","vpor","vpxor","vpandn"): c="logic/blend"
    elif op.startswith("vcvt"): c="convert"
    elif op.startswith("vp"): c="int vector"
    elif op.startswith(("vmov","vbroadcast")): c="move/broadcast"
    else: c="other:"+op
    tot[c]+=pct; n[c]+=1
for c,v in tot.most_common(): print("  %-18s %6.2f%%  (%d instrs)"%(c,v,n[c]))
print("  instructions with samples:", sum(n.values()))
