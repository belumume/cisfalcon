"""Audit fix #1/#2/#6: the numbers that actually decide whether a defensive
abort-gate is useful at the real 6.29% cross-lab base rate. AUROC is base-rate
invariant and hides this. Compute AUPRC, confusion matrix at operating points,
per-generator AUPRC with positive counts, and cross-lab baselines (GC, random).
No sklearn dependency (manual metrics)."""

import numpy as np, pandas as pd

df = pd.read_csv("data/gosai_designed/designed_scored.csv")
bench = pd.read_csv("data/gosai_designed/designed_benchmark.csv")[["id", "sequence"]]
df = df.merge(bench, on="id")
score = -df["pred_gap"].values  # higher = more likely to FAIL
fail = df["measured_fail"].values.astype(int)
gen = df["method"].values
base = fail.mean()


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
    rec = tp / y.sum()
    # step integral of precision over recall
    rec = np.concatenate([[0], rec])
    prec = np.concatenate([[1], prec])
    return float(np.sum((rec[1:] - rec[:-1]) * prec[1:]))


print(
    f"cross-lab n={len(df)}  base fail rate={base:.4f}  (random AUPRC = base = {base:.3f})"
)
print(f"AUROC={auroc(score, fail):.4f}   AUPRC={auprc(score, fail):.4f}")
print()
print("OPERATING POINTS (the abort-gate reality):")
order = np.argsort(-score)
ys = fail[order]
tp = np.cumsum(ys)
fp = np.cumsum(1 - ys)
recall = tp / fail.sum()
ppv = tp / (tp + fp)
frac_aborted = (np.arange(1, len(ys) + 1)) / len(ys)
false_abort = fp / (len(fail) - fail.sum())  # fraction of GOOD designs wrongly aborted
for tr in [0.3, 0.5, 0.7, 0.9]:
    i = np.argmin(np.abs(recall - tr))
    print(
        f"  recall={recall[i]:.2f}: PPV={ppv[i]:.3f}  false-abort={false_abort[i]:.3f}  "
        f"aborts {frac_aborted[i] * 100:4.1f}% of all designs  "
        f"({int(fp[i])} good killed per {int(tp[i])} real failures caught)"
    )
print()
# high-precision operating point: flag only the riskiest, what PPV?
for topk in [0.02, 0.05, 0.10]:
    i = int(topk * len(ys)) - 1
    print(
        f"  flag riskiest {topk * 100:.0f}%: PPV={ppv[i]:.3f} captures {recall[i] * 100:.1f}% of all failures"
    )
print()
# baselines
seq = df["sequence"].str.upper()
gc = seq.apply(lambda s: (s.count("G") + s.count("C")) / max(len(s), 1)).values
a_gc = auroc(gc, fail)
a_gc = max(a_gc, auroc(-gc, fail))
seqlen = seq.str.len().values.astype(float)
a_len = auroc(seqlen, fail)
a_len = max(a_len, auroc(-seqlen, fail))
print(f"BASELINES (does the gate beat trivial predictors?):")
print(f"  gate:        AUROC={auroc(score, fail):.3f}  AUPRC={auprc(score, fail):.3f}")
print(f"  GC-content:  AUROC={a_gc:.3f}")
print(f"  seq-length:  AUROC={a_len:.3f}")
print(f"  random:      AUROC=0.500  AUPRC={base:.3f}")
print()
print("PER-GENERATOR (AUPRC + positive count = the honest within-group signal):")
mac = []
for g in sorted(set(gen)):
    idx = gen == g
    npos = int(fail[idx].sum())
    if npos >= 5 and (fail[idx] == 0).sum() >= 5:
        a = auroc(score[idx], fail[idx])
        ap = auprc(score[idx], fail[idx])
        mac.append(a)
        print(
            f"  {g:8s} AUROC={a:.3f} AUPRC={ap:.3f}  n_pos={npos:5d}/{idx.sum():5d}  base={fail[idx].mean():.4f}"
        )
print(
    f"  macro-avg within-generator AUROC = {np.mean(mac):.3f}  (vs pooled {auroc(score, fail):.3f})"
)
