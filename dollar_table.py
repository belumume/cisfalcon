"""Audit fix #9: the fused operating-point dollar table (the money number) + the
honest triage value, and a Malinois-baseline availability check."""

import os, glob
import numpy as np, pandas as pd

df = pd.read_csv("data/gosai_designed/designed_scored.csv")
score = -df["pred_gap"].values
fail = df["measured_fail"].values.astype(int)
n = len(df)
base = fail.mean()
LO, HI = (
    250,
    1000,
)  # $ per design synth+individual validation (80-PITCH-ANGLES cost model)

print(
    f"n={n}  base fail={base:.4f}  (~{base * 100:.1f} wasted syntheses per 100 designs if uncaught)"
)
print(
    "\nTRIAGE dollar table (scrutinize/redesign the flagged riskiest BEFORE synthesis):"
)
order = np.argsort(-score)
ys = fail[order]
tp = np.cumsum(ys)
fp = np.cumsum(1 - ys)
recall = tp / fail.sum()
ppv = tp / (tp + fp)
for topk in [0.02, 0.05, 0.10, 0.20]:
    i = int(topk * n) - 1
    fails_caught = recall[i] * base * 100
    print(
        f"  flag riskiest {topk * 100:4.0f}% -> PPV {ppv[i]:.2f}, catches {recall[i] * 100:4.1f}% of failures "
        f"({fails_caught:.1f}/100); redesign-first avoids ${recall[i] * base * 100 * LO:.0f}-{recall[i] * base * 100 * HI:.0f} per 100 designs"
    )

print("\nSAFEST-FIRST framing (limited synthesis budget -> make lowest-risk first):")
safe = np.argsort(score)
for frac in [0.5, 0.7, 0.9]:
    m = int(frac * n)
    fr = fail[safe[:m]].mean()
    print(
        f"  synthesize safest {frac * 100:.0f}%: failure rate {fr * 100:.2f}% (vs {base * 100:.2f}% random) "
        f"= {(1 - fr / base) * 100:.0f}% fewer failures in what you make"
    )

print("\n=== Malinois self-prediction availability (killer comparator) ===")
files = [
    os.path.basename(c)
    for c in glob.glob("data/gosai_designed/**/*", recursive=True)
    if os.path.isfile(c)
]
print("gosai_designed files:", files)
b = pd.read_csv("data/gosai_designed/designed_benchmark.csv", nrows=2)
print("benchmark cols (any Malinois pred?):", list(b.columns))
