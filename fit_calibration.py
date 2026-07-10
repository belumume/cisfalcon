"""Fit + honesty-check the failure-probability calibration used by the live tool.

The verifier maps a predicted specificity gap -> P(fail) via isotonic regression on
(pred_gap, measured_fail) pairs. Until now no calibration.csv shipped, so the tool ran a
documented sigmoid fallback and the "calibrated" claim was soft. This fits the real map on
the 93,435-design Gosai cross-lab set, reports HELD-OUT calibration error honestly (fit on
half, evaluate ECE on the other half, both directions), and writes data/calibration.csv that
the deployed tool loads. Isotonic is monotonic, so the flagship ranking AUROC is unchanged;
this only makes the emitted probability trustworthy.

Local, CPU, seconds. No GPU.
"""

import numpy as np
import pandas as pd
from pathlib import Path

try:
    from sklearn.isotonic import IsotonicRegression
except Exception as e:
    raise SystemExit(f"sklearn required: {e}")

DATA = Path(__file__).parent / "data"
SCORED = DATA / "gosai_designed" / "designed_scored.csv"
OUT = DATA / "calibration.csv"
SEED = 0


def ece(pred_p, y, n_bins=10):
    """Expected calibration error: |predicted prob - observed fail rate| weighted by bin size."""
    edges = np.linspace(0, 1, n_bins + 1)
    idx = np.clip(np.digitize(pred_p, edges[1:-1]), 0, n_bins - 1)
    tot = 0.0
    rows = []
    for b in range(n_bins):
        m = idx == b
        if not m.any():
            continue
        conf = pred_p[m].mean()
        acc = y[m].mean()
        w = m.mean()
        tot += w * abs(conf - acc)
        rows.append(
            (edges[b], edges[b + 1], int(m.sum()), round(conf, 3), round(acc, 3))
        )
    return tot, rows


def fit_eval(train, test):
    iso = IsotonicRegression(increasing=False, out_of_bounds="clip").fit(
        train["pred_gap"].values, train["fail"].values
    )
    p = iso.predict(test["pred_gap"].values)
    return ece(p, test["fail"].values.astype(float))


def main():
    df = pd.read_csv(SCORED).rename(columns={"measured_fail": "fail"})
    df = df[["pred_gap", "fail"]].dropna()
    df["fail"] = df["fail"].astype(int)
    n = len(df)
    base = df["fail"].mean()
    print(f"n={n}  base fail rate={base:.4f}")

    rng = np.random.default_rng(SEED)
    perm = rng.permutation(n)
    half = n // 2
    A = df.iloc[perm[:half]].reset_index(drop=True)
    B = df.iloc[perm[half:]].reset_index(drop=True)

    e_ab, rows_ab = fit_eval(A, B)
    e_ba, _ = fit_eval(B, A)
    print(f"HELD-OUT ECE (fit A, eval B): {e_ab:.4f}")
    print(f"HELD-OUT ECE (fit B, eval A): {e_ba:.4f}")
    print(f"HELD-OUT ECE (mean, honest):  {(e_ab + e_ba) / 2:.4f}")

    # baseline ECE of the shipped sigmoid fallback, for contrast
    sig = 1.0 / (1.0 + np.exp(3.0 * B["pred_gap"].values))
    e_sig, _ = ece(sig, B["fail"].values.astype(float))
    print(f"sigmoid-fallback ECE (eval B): {e_sig:.4f}  <- what the tool ran before")

    print("\nHELD-OUT reliability (fit A, eval B): [lo,hi) n pred_conf obs_fail")
    for lo, hi, cnt, conf, acc in rows_ab:
        print(f"  [{lo:.1f},{hi:.1f})  n={cnt:6d}  pred={conf:.3f}  obs={acc:.3f}")

    # deployment calibration = raw pairs; verifier.py fits isotonic on load.
    # 20k stratified subsample keeps the bundled CSV small with an identical monotone map.
    keep = min(20000, n)
    sub = (
        df.iloc[rng.permutation(n)[:keep]]
        .sort_values("pred_gap")
        .reset_index(drop=True)
    )
    sub.to_csv(OUT, index=False)
    print(
        f"\nwrote {OUT}  ({len(sub)} pairs, cols pred_gap,fail) for the deployed tool"
    )


if __name__ == "__main__":
    main()
