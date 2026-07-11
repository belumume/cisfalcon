#!/usr/bin/env python
"""Re-derive every CisFalcon flagship number from the committed cross-lab scores.

No GPU, no model download, no API key. Needs only numpy + pandas. Runs in ~1 second.

    python reproduce_flagship.py

It reads data/gosai_designed/designed_scored.csv (the per-design CisFalcon
predictions and the wet-lab specificity labels for 93,435 designs from an
independent lab, Gosai/Tewhey 2024) and prints the cross-lab AUROC, the triage
enrichment, and the failure-reduction from safest-first ranking. The AUROC is a
plain rank-sum (Mann-Whitney) computation, so the headline number is not a
pipeline artifact: it falls straight out of the two committed columns.
"""

from pathlib import Path
import numpy as np
import pandas as pd

CSV = Path(__file__).parent / "data" / "gosai_designed" / "designed_scored.csv"


def rank_sum_auroc(labels: np.ndarray, scores: np.ndarray) -> float:
    """AUROC via average-rank sum. labels: 1=fail/0=pass; higher score = more risk."""
    ranks = pd.Series(scores).rank().values  # average ranks handle ties
    n_pos = labels.sum()
    n_neg = len(labels) - n_pos
    return (ranks[labels == 1].sum() - n_pos * (n_pos + 1) / 2) / (n_pos * n_neg)


def main() -> None:
    df = pd.read_csv(CSV)
    y = df["measured_fail"].values.astype(int)  # wet-lab: 1 = failed specificity
    pred_gap = df["pred_gap"].values  # CisFalcon predicted specificity gap
    risk = -pred_gap  # lower gap = higher failure risk

    n = len(y)
    base = y.mean()
    auroc = rank_sum_auroc(y, risk)

    # Triage: rank by predicted gap ascending (riskiest first).
    ys = y[np.argsort(pred_gap)]
    k2 = int(round(0.02 * n))
    ppv2 = ys[:k2].mean()
    safe_half_fail = ys[n // 2 :].mean()

    # A no-sequence-signal baseline on the same task and labels.
    rng = np.random.default_rng(0)
    auroc_random = rank_sum_auroc(y, rng.random(n))

    line = "=" * 66
    print(line)
    print("  CisFalcon flagship, re-derived from committed cross-lab scores")
    print(f"  source: {CSV.relative_to(Path(__file__).parent)}")
    print(line)
    print(f"  designs (independent lab, zero training overlap) : {n:,}")
    print(
        f"  wet-lab specificity-failure base rate            : {base * 100:.2f}%  (~1 in {1 / base:.0f})"
    )
    print()
    print(f"  cross-lab AUROC (risk vs measured failure)       : {auroc:.4f}")
    print(f"    random-score baseline                          : {auroc_random:.4f}")
    print()
    print(f"  TRIAGE, riskiest 2% flagged (n={k2:,})")
    print(f"    of those, truly fail                           : {ppv2 * 100:.1f}%")
    print(f"    enrichment over base rate                      : {ppv2 / base:.2f}x")
    print()
    print(f"  RANK safest-first, synthesize the safer half")
    print(
        f"    failure rate in what you make                  : {safe_half_fail * 100:.2f}%"
    )
    print(
        f"    reduction vs unranked                          : {(1 - safe_half_fail / base) * 100:.0f}%"
    )
    print(line)
    print("  These are the deployment numbers for a mixed batch. Conditioning")
    print("  the AUROC on the cell and generator base-rates (cell_prior_baseline.py)")
    print("  leaves a per-sequence signal of 0.66, still well above 0.50. Full")
    print("  methodology, caveats, and pre-registered threshold are in PREREG.md.")
    print(line)


if __name__ == "__main__":
    main()
