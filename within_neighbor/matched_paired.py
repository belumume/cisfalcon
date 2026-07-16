"""Matched, paired comparison of the sequence specificity gap against the measured
baselines on the Allen/BICCN in-vivo cortical set.

Why this exists: the headline within-tissue AUROC (gap, 0.7056) is computable only on
the enhancers whose target subclass DeepBICCN2 has an output head for (204 of the 211
hard On/Off-labelled rows). The measured baselines need no subclass mapping, so they
score all 211. Comparing 0.7056 (n=204) against a baseline at n=211 is not a like-for-
like comparison, and a difference of point estimates is not a result in either case.

This script does both things properly:
  1. restricts every feature to the SAME rows (those where the gap is computable), and
  2. runs a PAIRED bootstrap on the difference, the same instrument `ensemble_ci.py`
     uses for the two-head lift.

Result (2000 resamples, seed 0): on the matched 204, gini reads 0.7308 vs the gap's
0.7056, and the paired 95% CI on the difference is [-0.066, +0.115], which INCLUDES
zero. So the sequence gap and the measured feature are statistically indistinguishable
on this set. They are not ranked. Reproducible; pandas + numpy only, no GPU.
"""

import numpy as np
import pandas as pd

DATA = "within_neighbor/kaggle_brain/out/brain_gaps_with_baselines.csv"
GAP = "gap"
BASELINES = ["gini_index", "max_scaled_acc_mouse", "GC.content"]
N_BOOT = 2000
SEED = 0


def auroc(labels, scores):
    """Rank-sum AUROC, ties averaged. Higher score = more likely positive (On-Target)."""
    labels = np.asarray(labels)
    scores = np.asarray(scores)
    n1 = int(labels.sum())
    n0 = int((1 - labels).sum())
    if n1 == 0 or n0 == 0:
        return float("nan")
    rank = pd.Series(scores).rank().values
    return float((rank[labels == 1].sum() - n1 * (n1 + 1) / 2) / (n1 * n0))


def paired_bootstrap(labels, a, b, n_boot=N_BOOT, seed=SEED):
    """95% CI on auroc(b) - auroc(a), resampling the SAME rows through both features."""
    rng = np.random.default_rng(seed)
    n = len(labels)
    deltas = []
    for _ in range(n_boot):
        idx = rng.integers(0, n, n)
        y = labels[idx]
        if y.sum() == 0 or (1 - y).sum() == 0:
            continue
        deltas.append(auroc(y, b[idx]) - auroc(y, a[idx]))
    deltas = np.array(deltas)
    lo, hi = np.percentile(deltas, [2.5, 97.5])
    return float(deltas.mean()), float(lo), float(hi), float((deltas > 0).mean())


def main(path=DATA):
    df = pd.read_csv(path)
    hard = df[df["LABEL_Specificity"].isin(["On_Target", "Off_Target"])].copy()
    hard["y"] = (hard["LABEL_Specificity"] == "On_Target").astype(int)
    print(
        f"hard On/Off rows: {len(hard)}  (On {int(hard.y.sum())}, Off {int((1 - hard.y).sum())})"
    )

    scorable = hard[~hard[GAP].isna()].copy().reset_index(drop=True)
    dropped = len(hard) - len(scorable)
    print(
        f"gap-scorable rows: {len(scorable)}  (On {int(scorable.y.sum())}, "
        f"Off {int((1 - scorable.y).sum())}); {dropped} dropped, target subclass "
        f"has no DeepBICCN2 output head"
    )

    y = scorable["y"].values
    gap = scorable[GAP].values
    gap_auroc = auroc(y, gap)

    print(
        "\nUNMATCHED (each feature on its own non-null rows, as originally reported):"
    )
    for col in BASELINES:
        sub = hard[~hard[col].isna()]
        print(
            f"    {col:22s} {auroc(sub['y'].values, sub[col].values):.4f}  (n={len(sub)})"
        )
    print(f"    {GAP:22s} {gap_auroc:.4f}  (n={len(scorable)})")

    print(
        f"\nMATCHED on the {len(scorable)} gap-scorable rows, PAIRED bootstrap "
        f"({N_BOOT} resamples, seed {SEED}):"
    )
    print(f"    {GAP:22s} {gap_auroc:.4f}   (reference)")
    for col in BASELINES:
        b = scorable[col].values
        b_auroc = auroc(y, b)
        mean, lo, hi, p_gt = paired_bootstrap(y, gap, b)
        verdict = (
            "EXCLUDES zero"
            if (lo > 0 or hi < 0)
            else "INCLUDES zero (indistinguishable)"
        )
        print(
            f"    {col:22s} {b_auroc:.4f}   delta {mean:+.4f}  "
            f"95% CI [{lo:+.4f}, {hi:+.4f}]  {verdict}  P(baseline>gap)={p_gt:.3f}"
        )

    print(
        "\nRead: a difference of point estimates is not a result. On the matched set the "
        "sequence gap and the measured accessibility features are statistically\n"
        "indistinguishable, so the honest claim is that the gap recovers from sequence what "
        "an assay would tell you, not that either one ranks above the other."
    )


if __name__ == "__main__":
    main()
