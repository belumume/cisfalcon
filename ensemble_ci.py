#!/usr/bin/env python
"""Frozen two-head ensemble: does combining the activity and accessibility heads
under a zero-parameter, a-priori rank-average beat the best single head cross-lab?

No training, no tuning: the rule (rank-average the two specificity gaps) is fixed
before any number is read, evaluated on the held-out 93,435 Gosai designs with
frozen models, so it is leakage-immune and un-tunable. Reads the per-design gaps
produced by the Kaggle GPU kernel `ubaidullahshuaib/cisfalcon-ensemble-gaps`
(design_gaps.csv: id, label, act_gap, acc_binary_gap, acc_logsignal_gap).

    python ensemble_ci.py data/gosai_designed/design_gaps.csv

Honesty gate: this is EXPLORATORY. If the paired 95% CI on (ensemble - best single
head) excludes zero and is positive, the ensemble genuinely lifts and it is worth
re-leading. If it straddles zero, the honest read is that the activity head alone
is already the best single predictor and the ensemble adds nothing measurable.
"""

import sys
from pathlib import Path
import numpy as np
import pandas as pd

N_BOOT = 2000
SEED = 0


def auroc(labels: np.ndarray, risk: np.ndarray) -> float:
    """Vectorized average-rank AUROC (ties get the mean rank). Higher risk = more failure."""
    order = np.argsort(risk, kind="mergesort")
    s = risk[order]
    n = len(s)
    # average ranks: for each element, mean of the 1-based positions of its tie group
    ordinal = np.arange(1, n + 1, dtype=float)
    # boundaries of tie groups on the sorted array
    change = np.empty(n, dtype=bool)
    change[0] = True
    change[1:] = s[1:] != s[:-1]
    grp = np.cumsum(change) - 1
    csum = np.zeros(grp[-1] + 2)
    np.add.at(csum, grp, ordinal)
    cnt = np.bincount(grp)
    avg_by_grp = csum[: len(cnt)] / cnt
    ranks_sorted = avg_by_grp[grp]
    rank = np.empty(n)
    rank[order] = ranks_sorted
    n1 = labels.sum()
    n0 = n - n1
    return float((rank[labels == 1].sum() - n1 * (n1 + 1) / 2) / (n1 * n0))


def rank01(x: np.ndarray) -> np.ndarray:
    return pd.Series(x).rank().values / len(x)


def main() -> None:
    path = Path(
        sys.argv[1] if len(sys.argv) > 1 else "data/gosai_designed/design_gaps.csv"
    )
    df = pd.read_csv(path)
    y = df["label"].values.astype(int)
    act = df["act_gap"].values
    acc_bin = df["acc_binary_gap"].values
    acc_log = df["acc_logsignal_gap"].values
    n = len(y)

    heads = {"activity": act, "acc_binary": acc_bin, "acc_logsignal": acc_log}
    aucs = {k: auroc(y, -v) for k, v in heads.items()}

    # a-priori zero-parameter ensembles: rank-average the two specificity gaps.
    ens_bin = (rank01(act) + rank01(acc_bin)) / 2  # higher = safer
    ens_log = (rank01(act) + rank01(acc_log)) / 2
    aucs["ens(act+acc_binary)"] = auroc(y, -ens_bin)
    aucs["ens(act+acc_logsignal)"] = auroc(y, -ens_log)

    best_single = max(aucs["activity"], aucs["acc_binary"], aucs["acc_logsignal"])
    best_single_name = max(
        ("activity", "acc_binary", "acc_logsignal"), key=lambda k: aucs[k]
    )

    # paired bootstrap on (best ensemble - best single head)
    ens = (
        ens_bin
        if aucs["ens(act+acc_binary)"] >= aucs["ens(act+acc_logsignal)"]
        else ens_log
    )
    single = -{"activity": act, "acc_binary": acc_bin, "acc_logsignal": acc_log}[
        best_single_name
    ]
    rng = np.random.default_rng(SEED)
    diffs = np.empty(N_BOOT)
    for b in range(N_BOOT):
        idx = rng.integers(0, n, n)
        diffs[b] = auroc(y[idx], -ens[idx]) - auroc(y[idx], single[idx])
    lo, hi = float(np.percentile(diffs, 2.5)), float(np.percentile(diffs, 97.5))

    L = "=" * 70
    print(L)
    print(f"  Frozen two-head ensemble, cross-lab (n={n:,}, seed {SEED})")
    print(L)
    for k in [
        "activity",
        "acc_binary",
        "acc_logsignal",
        "ens(act+acc_binary)",
        "ens(act+acc_logsignal)",
    ]:
        print(f"  {k:26s} AUROC {aucs[k]:.4f}")
    print(L)
    best_ens = max(aucs["ens(act+acc_binary)"], aucs["ens(act+acc_logsignal)"])
    delta = best_ens - best_single
    print(f"  best single head : {best_single_name} {best_single:.4f}")
    print(f"  best ensemble    : {best_ens:.4f}   (delta {delta:+.4f})")
    print(f"  paired 95% CI on (ensemble - best single head): [{lo:+.4f}, {hi:+.4f}]")
    if lo > 0:
        print(
            "  VERDICT: ensemble genuinely lifts (CI excludes zero, positive). Re-lead it."
        )
    elif hi < 0:
        print(
            "  VERDICT: ensemble is worse (CI excludes zero, negative). Keep the single head."
        )
    else:
        print(
            "  VERDICT: no measurable lift (CI straddles zero). Activity head alone is the best single"
        )
        print(
            "           predictor; the honest read stands, do not overclaim an ensemble gain."
        )
    print(L)


if __name__ == "__main__":
    main()
