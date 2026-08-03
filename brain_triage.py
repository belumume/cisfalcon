#!/usr/bin/env python
"""Brain-cell (SKNSH) triage operating point, for the disease-impact lane.

No GPU, no download. Restricts the committed cross-lab per-design scores to the
brain-derived SKNSH neuroblastoma line and reports the triage numbers that matter
for a lab designing brain-cell-specific enhancers: base failure rate, the
safest-first failure reduction, and the riskiest-flag enrichment. These are softer
than the pooled numbers (SKNSH cross-lab AUROC 0.73 vs pooled 0.80) and are
reported honestly as-is; they show the brain relevance with a concrete brain number
rather than only arguing it. SKNSH is a brain-derived cancer line, an in-vitro
stand-in, not primary cortical neurons.

    python brain_triage.py
"""

from pathlib import Path
import numpy as np
import pandas as pd

CSV = Path(__file__).parent / "data" / "gosai_designed" / "designed_scored.csv"


def auroc(score: np.ndarray, y: np.ndarray) -> float:
    order = np.argsort(score, kind="mergesort")
    rank = np.empty(len(score))
    rank[order] = np.arange(1, len(score) + 1)
    n1 = y.sum()
    n0 = len(y) - n1
    return (
        float((rank[y == 1].sum() - n1 * (n1 + 1) / 2) / (n1 * n0))
        if n1 and n0
        else float("nan")
    )


def main() -> None:
    df = pd.read_csv(CSV)
    d = df[df["target_cell"] == "SKNSH"]
    y = d["measured_fail"].values.astype(int)
    gap = d["pred_gap"].values
    n = len(y)
    base = y.mean()

    order = np.argsort(gap)  # riskiest (smallest gap) first
    ys = y[order]
    safe_half = ys[n // 2 :].mean()

    def enrich(frac):
        k = int(round(frac * n))
        ppv = ys[:k].mean()
        captured = np.cumsum(ys)[k - 1] / y.sum()
        return ppv, ppv / base, captured

    ppv2, enr2, cap2 = enrich(0.02)
    ppv10, enr10, cap10 = enrich(0.10)

    L = "=" * 68
    print(L)
    print("  CisFalcon on the brain-derived SKNSH line (cross-lab, committed data)")
    print(L)
    print(f"  designs targeting SKNSH                    : {n:,}")
    print(f"  specificity-failure base rate              : {base * 100:.2f}%")
    print(f"  cross-lab AUROC                            : {auroc(-gap, y):.4f}")
    print()
    print(f"  synthesize the safest-ranked half:")
    print(f"    failure rate in what you make            : {safe_half * 100:.2f}%")
    print(
        f"    reduction vs unranked, POOLED             : {(1 - safe_half / base) * 100:.0f}%"
    )
    print(f"    reduction CONDITIONED (x generator)      : 32% macro (7% to 67%)")
    print(f"    sequence-free generator-prior null       : 82%")
    print(f"    -> the honest per-design figure is the conditioned 32%, not the")
    print(f"       pooled number; run brain_conditioning_check.py to re-derive")
    print()
    # These two used to print unlabelled, four lines below an explicitly POOLED/CONDITIONED
    # pair - so a reader just taught to distinguish the two bases reasonably read the more
    # flattering 4.8x as carrying the same conditioning. Both are pooled; the conditioned
    # macro enrichment is 1.90x (brain_conditioning_check.py), 2.5x lower.
    print(
        f"  flag the riskiest 2%, POOLED  : PPV {ppv2 * 100:.0f}%  ({enr2:.1f}x base)"
    )
    print(
        f"  flag the riskiest 10%, POOLED : captures {cap10 * 100:.0f}% of failures ({enr10:.1f}x base)"
    )
    print("    riskiest-2% enrichment CONDITIONED (x generator) : 1.90x macro")
    print("    -> as above, the conditioned figure is the per-design one")
    print(L)
    print("  Softer than the pooled 0.80 / 70% / 7.74x numbers, and reported as-is:")
    print("  SKNSH is a brain-derived cancer line, an in-vitro stand-in. A primary")
    print("  cortical-neuron MPRA is the honest next step. But the brain relevance is")
    print("  shown here on a real brain-cell design set, not only argued.")
    print(L)


if __name__ == "__main__":
    main()
