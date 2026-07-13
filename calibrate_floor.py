"""Calibrate an activity-plausibility floor for the CisFalcon gate.

A user testing the tool found that a RANDOM nucleotide sequence still gets a
specificity verdict, because the gate is purely relative (gap = target - max off-target)
with no absolute-activity check. This scores real designs vs random sequences on peak
predicted activity (max log2FC over the 10 target cells) to find a floor below which a
sequence is not a plausible enhancer and the specificity question is moot.
"""

import os, sys, csv, random

os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "3")
os.environ.setdefault("CUDA_VISIBLE_DEVICES", "-1")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np
import gate

random.seed(0)
np.random.seed(0)

BM = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "data",
    "gosai_designed",
    "designed_benchmark.csv",
)
N = 1000

# --- real designs ---
real = []
with open(BM, newline="") as f:
    for row in csv.DictReader(f):
        s = row["sequence"].strip().upper()
        if set(s) <= set("ACGT") and 100 <= len(s) <= 500:
            real.append(s)
random.shuffle(real)
real = real[:N]
lens = [len(s) for s in real]
Lmed = int(np.median(lens))
print(f"real designs: n={len(real)} len(min/med/max)={min(lens)}/{Lmed}/{max(lens)}")


# --- random sequences (length-matched to real, plus a fixed-median batch) ---
def rnd(n):
    return "".join(random.choice("ACGT") for _ in range(n))


randm = [rnd(len(real[i])) for i in range(len(real))]  # length-matched
randf = [rnd(Lmed) for _ in range(N)]  # fixed median length


def peak_over_targets(seqs):
    pred = gate.score_sequences(seqs)  # (n, 12) log2FC
    idx = [gate.CELL_IDX[c] for c in gate.TARGET_CELLS]  # 10 target cells
    return pred[:, idx].max(axis=1)  # peak over target cells


print("scoring real ...")
pr = peak_over_targets(real)
print("scoring rand(len-matched) ...")
pn = peak_over_targets(randm)
print("scoring rand(fixed-median) ...")
pf = peak_over_targets(randf)


def show(name, x):
    q = np.percentile(x, [0, 1, 5, 10, 25, 50, 75, 90, 95, 99, 100])
    print(
        f"{name:22s} n={len(x)}  min/1/5/10/25/50/75/90/95/99/max = "
        + " ".join(f"{v:.2f}" for v in q)
    )


print("\n=== PEAK predicted activity (max log2FC over 10 target cells) ===")
show("REAL designs", pr)
show("RANDOM (len-matched)", pn)
show("RANDOM (fixed-median)", pf)

print("\n=== candidate floors: fraction flagged 'not enhancer-like' (peak < floor) ===")
allrand = np.concatenate([pn, pf])
for fl in [0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0]:
    print(
        f"floor={fl:4.2f}: REAL flagged={(pr < fl).mean():6.1%}   RANDOM flagged={(allrand < fl).mean():6.1%}"
    )

# a clean separator: highest floor keeping REAL false-flag <= 1%
cand = [round(x, 2) for x in np.arange(0.5, 3.01, 0.05)]
best = None
for fl in cand:
    if (pr < fl).mean() <= 0.01:
        best = fl
print(f"\nSuggested floor (REAL false-flag <= 1%, maximized): {best}")
if best is not None:
    print(
        f"  at floor={best}: REAL flagged={(pr < best).mean():.2%}, RANDOM flagged={(allrand < best).mean():.2%}"
    )
