"""Audit fix #4: make 0.92-vs-0.80 apples-to-apples. In-distribution AUROC on the
atlas's OWN AI designs, but restricted to the SAME 3 cells (K562/HepG2/SKNSH) and
the SAME 3-cell fail definition and OOF scoring used for the cross-lab 0.80. Tells
us how much of the 0.92->0.80 'drop' is the task change (max-of-10 -> max-of-3, 48%
-> 6% base rate) vs real generalization loss."""

import json
import numpy as np, pandas as pd
import gate

SHARED = ["K562", "HepG2", "SKNSH"]
SIDX = [gate.CELL_IDX[c] for c in SHARED]
lfc = [f"log2FC_{c}" for c in SHARED]

splits = json.load(open("data/mpra_data_splits.json"))
oof = {}
for k in [0, 1, 3]:
    for i in splits[k]["test"]:
        oof.setdefault(i, k)

df = pd.read_csv("data/enhancer_mpra_processed.tsv", sep="\t", low_memory=False)


def norm(s):
    return str(s).upper().replace("_", "").replace("-", "")


panel = {norm(c): c for c in SHARED}
d = df[df["target"].notna()].copy()
d = d[~d["target"].astype(str).str.startswith("(")]
d = d[~d["target"].astype(str).str.contains(",")]
d["tcell"] = d["target"].map(lambda t: panel.get(norm(t)))
d = d[d["tcell"].notna()]
d = d[d["source"].isin(["fsp", "den", "motif_embedding"])]
d = d.dropna(subset=lfc)
d["oof"] = d["id"].map(oof)
d = d[d["oof"].notna()].copy()
d["oof"] = d["oof"].astype(int)
print(
    f"matched in-dist designs (atlas AI, target in 3 shared cells, OOF-covered): {len(d)}",
    flush=True,
)

L = d[lfc].values.astype(float)
ti = np.array([SHARED.index(c) for c in d["tcell"]])
r = np.arange(len(d))
offmask = np.eye(3)[ti].astype(bool)
meas_gap = L[r, ti] - np.where(offmask, -np.inf, L).max(1)
fail = (meas_gap <= 0).astype(int)
print(
    f"measured 3-cell FAIL rate (in-dist): {fail.mean():.4f}  (cross-lab was 0.063)",
    flush=True,
)

import tensorflow as tf

models = {
    k: tf.keras.models.load_model(f"models/dhs64_mpra_split{k}.h5", compile=False)
    for k in [0, 1, 3]
}
seqs = d["sequence"].tolist()
pred = np.empty((len(d), 12), np.float32)
for k in [0, 1, 3]:
    idx = np.where(d["oof"].values == k)[0]
    X = gate.one_hot_encode([seqs[j] for j in idx])
    pred[idx] = models[k].predict(X, batch_size=256, verbose=0)
    print(f"  scored OOF fold {k}: {len(idx)}", flush=True)
P3 = pred[:, SIDX]
pred_gap = P3[r, ti] - np.where(offmask, -np.inf, P3).max(1)


def auroc(s, y):
    o = np.argsort(s, kind="mergesort")
    rank = np.empty(len(s))
    rank[o] = np.arange(1, len(s) + 1)
    n1 = y.sum()
    n0 = len(y) - n1
    return (
        float((rank[y == 1].sum() - n1 * (n1 + 1) / 2) / (n1 * n0))
        if n1 and n0
        else float("nan")
    )


def auprc(s, y):
    o = np.argsort(-s, kind="mergesort")
    y = y[o]
    tp = np.cumsum(y)
    fp = np.cumsum(1 - y)
    prec = tp / (tp + fp)
    rec = np.concatenate([[0], tp / y.sum()])
    prec = np.concatenate([[1], prec])
    return float(np.sum((rec[1:] - rec[:-1]) * prec[1:]))


print("\n===== MATCHED COMPARISON =====", flush=True)
print(
    f"in-dist  3-cell OOF: AUROC={auroc(-pred_gap, fail):.4f}  AUPRC={auprc(-pred_gap, fail):.4f}  n={len(d)}  fail={fail.mean():.3f}",
    flush=True,
)
print(
    f"cross-lab 3-cell:    AUROC=0.8013  AUPRC=0.2929  n=93435  fail=0.063", flush=True
)
print(
    f"(in-dist 10-cell was 0.921 at 48% fail - NOT comparable to either above)",
    flush=True,
)
