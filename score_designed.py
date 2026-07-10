"""Cross-lab DESIGNED test: score Gosai/Malinois BODA designs with CisFalcon's
atlas-trained gate, compute predicted 3-cell (K562/HepG2/SKNSH) specificity gap,
and measure how well it discriminates the MEASURED wet-lab failures.
Independent lab (Tewhey), independent model (Malinois), independent generators.
Usage: python score_designed.py [N]   (N=0 -> full 93k; else stratified subsample)
"""

import sys, time
import numpy as np, pandas as pd
import gate

N = int(sys.argv[1]) if len(sys.argv) > 1 else 0
SHARED = ["K562", "HepG2", "SKNSH"]
SIDX = [gate.CELL_IDX[c] for c in SHARED]
RES = "data/gosai_designed/designed_result.txt"


def log(s):
    print(s, flush=True)
    with open(RES, "a") as f:
        f.write(s + "\n")


df = pd.read_csv("data/gosai_designed/designed_benchmark.csv")
if N:
    per = N // 3
    df = (
        df.groupby("target_cell", group_keys=False)
        .sample(n=per, random_state=0)
        .reset_index(drop=True)
    )
log(
    f"\n===== cross-lab designed run {time.strftime('%H:%M') if False else ''} n={len(df)} (measured FAIL {df.measured_fail.mean() * 100:.1f}%) ====="
)

seqs = df["sequence"].tolist()
t = time.time()
pred = gate.score_sequences(seqs)
dt = time.time() - t
log(f"scored in {dt:.0f}s ({len(seqs) / dt:.1f} seq/s)")

P3 = pred[:, SIDX]
tgt_i = df["target_cell"].map({c: i for i, c in enumerate(SHARED)}).values
r = np.arange(len(df))
offmask = np.eye(3)[tgt_i].astype(bool)
pred_gap = P3[r, tgt_i] - np.where(offmask, -np.inf, P3).max(1)
meas_gap = df["measured_gap"].values
fail = df["measured_fail"].values


def auroc(score, y):
    y = np.asarray(y)
    o = np.argsort(score, kind="mergesort")
    rank = np.empty(len(score))
    rank[o] = np.arange(1, len(score) + 1)
    n1 = y.sum()
    n0 = len(y) - n1
    return (
        float((rank[y == 1].sum() - n1 * (n1 + 1) / 2) / (n1 * n0))
        if n1 and n0
        else float("nan")
    )


def spearman(a, b):
    return float(np.corrcoef(pd.Series(a).rank(), pd.Series(b).rank())[0, 1])


log(
    f"AUROC (predicted gap discriminates measured specificity failure): {auroc(-pred_gap, fail):.3f}"
)
log(f"Spearman(predicted gap, measured gap): {spearman(pred_gap, meas_gap):.3f}")
for col in ["method", "target_cell"]:
    log(f"-- by {col} --")
    for v in sorted(df[col].unique()):
        idx = df[col].values == v
        if fail[idx].sum() >= 5 and (~fail[idx].astype(bool)).sum() >= 5:
            log(
                f"   {v:8s} n={int(idx.sum()):6d} failrate={fail[idx].mean() * 100:4.1f}%  AUROC={auroc(-pred_gap[idx], fail[idx]):.3f}"
            )
log("DONE")
