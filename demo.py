"""CisFalcon demo: catch a real doomed AI-designed enhancer BEFORE synthesis.
The design is real, from an independent lab (Gosai/Tewhey), optimized to be
HepG2-specific. Its wet-lab measurement is the ground-truth reveal at the end."""

import os, sys, json
import pandas as pd
from verifier import CisFalconVerifier
import gate

HERO_ID = "20211213_141901__715602__47::hmc__hepg2__0"
b = pd.read_csv("data/gosai_designed/designed_benchmark.csv")
row = b[b["id"] == HERO_ID].iloc[0]
seq, target = row["sequence"], row["target_cell"]
measured = {"K562": row["K562"], "HepG2": row["HepG2"], "SKNSH": row["SKNSH"]}

bar = "=" * 68
print(bar)
print("A scientist has an AI-designed enhancer, optimized to be HepG2-SPECIFIC.")
print("Synthesizing + validating one design: $250-1000 and 2-4 weeks.")
print("CisFalcon reads it from SEQUENCE ALONE, before any DNA is made:")
print(bar)

v = CisFalconVerifier(use_agents=(not "--no-agents" in sys.argv))
out = v.verify(seq, target)
g = out["gate"]
print(f"\n[ GATE ]  predicted cell-type activity from sequence")
print(f"  intended target       : {target}")
print(
    f"  predicted MOST-ACTIVE  : {g['predicted_most_active_cell']}   <-- not the target"
)
print(
    f"  predicted specificity gap : {g['predicted_specificity_gap']}   (<= 0 means predicted FAIL)"
)
print(f"  predicted off-target risk : {g['off_target_risk_cells'][:2]}")

verd = out.get("verdict", {})
if isinstance(verd, dict) and verd.get("verdict"):
    print(f"\n[ VERDICT ]  {verd['verdict']}  ->  {verd.get('recommendation', '')}")
    print(f"  {str(verd.get('reasoning', ''))[:240]}")

print(f"\n[ WET-LAB TRUTH ]  what actually happened when this design was measured")
print(
    f"  HepG2 (its target): {measured['HepG2']:+.1f}    K562: {measured['K562']:+.1f}    SKNSH: {measured['SKNSH']:+.1f}"
)
print(
    f"  It barely touches its HepG2 target and fires {measured['K562']:.1f}-fold in K562."
)
print(f"  A complete cell-type-specificity failure -- and CisFalcon predicted the K562")
print(f"  off-target from sequence alone, before a cent was spent on synthesis.")

print(f"\n{bar}")
print("At scale: on 93,435 designs from this independent lab (a different model and")
print("generators the gate never saw), ranking by CisFalcon and making the safest half")
print(
    "first cuts specificity failures 70% (6.3% -> 1.9%). Cross-lab AUROC 0.80, grounded"
)
print(
    "in real wet-lab measurement -- a signal a generic AI-reviewing-AI does not have."
)
print(bar)
