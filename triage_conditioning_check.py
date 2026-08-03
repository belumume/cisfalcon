"""Does CisFalcon's triage headline survive the same conditioning as its AUROC?

The finding (surfaced by Kimi K3 when handed the real repo, 2026-07-28): the headline
AUROC is reported BOTH pooled (0.80) and conditioned on cell x generator (0.66), but the
triage headline (6.29% -> 1.91%, "70% fewer failures") is only ever reported POOLED. If
that reduction is partly the ranker sorting easy strata above hard ones, the conditioned
number is smaller and the honest report should say so.

Positive control first: reproduce the published pooled numbers. If the control does not
reproduce, the conditioned numbers below mean nothing (a metric script with no known-answer
assert is an instrument nobody has shown to work).

Run:
  python triage_conditioning_check.py <path-to-cisfalcon-clone>
"""

import os
import sys
import pandas as pd

REPO = sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(os.path.abspath(__file__))
CSV = f"{REPO}/data/gosai_designed/designed_scored.csv"

# Published, from the repo's own reproduce_flagship.py output
PUB_BASE, PUB_AFTER = 6.29, 1.91

# cell_prior_baseline.py: "a stratum needs >=10 fail and >=10 pass"
MIN_PER_CLASS = 10


def safest_half_failure_rate(df):
    """Rank safest-first by predicted specificity gap, keep the safer half, return its
    measured failure rate as a percentage. Higher pred_gap = predicted more specific."""
    if len(df) < 2:
        return None
    ranked = df.sort_values("pred_gap", ascending=False)
    half = ranked.head(len(ranked) // 2)
    return 100.0 * half["measured_fail"].mean()


def main():
    d = pd.read_csv(CSV)
    print(
        f"rows {len(d):,}   cells {d.target_cell.nunique()}   generators {d.method.nunique()}\n"
    )

    # ---- positive control -------------------------------------------------
    base = 100.0 * d["measured_fail"].mean()
    after = safest_half_failure_rate(d)
    red = 100.0 * (1 - after / base)
    print("POSITIVE CONTROL (pooled, must match the published numbers)")
    print(f"  base rate      {base:.2f}%   published {PUB_BASE}%")
    print(f"  safest half    {after:.2f}%   published {PUB_AFTER}%")
    print(f"  reduction      {red:.0f}%")
    ok = abs(base - PUB_BASE) < 0.05 and abs(after - PUB_AFTER) < 0.05
    print(f"  control: {'PASS' if ok else 'FAIL'}\n")
    if not ok:
        raise SystemExit(
            "control failed; conditioned numbers below would be meaningless"
        )

    # ---- conditioned on cell x generator, the same axes as the 0.66 -------
    print("CONDITIONED within each (cell x generator) stratum")
    rows = []
    for (cell, method), g in d.groupby(["target_cell", "method"]):
        # The repo's own criterion, verbatim from cell_prior_baseline.py:
        #   MIN_PER_CLASS = 10  # >=10 fail and >=10 pass
        # Using it (rather than a proxy) means these strata are exactly the 14 the
        # published 0.66 joint AUROC is macro-averaged over, so the triage figures below
        # are directly comparable to it rather than merely similar-looking.
        n_fail = g["measured_fail"].sum()
        n_pass = len(g) - n_fail
        if n_fail < MIN_PER_CLASS or n_pass < MIN_PER_CLASS:
            continue
        b = 100.0 * g["measured_fail"].mean()
        a = safest_half_failure_rate(g)
        rows.append(
            (cell, method, len(g), b, a, 100.0 * (1 - a / b) if b else float("nan"))
        )

    rows.sort(key=lambda r: -r[2])
    print(
        f"  {'cell':<10}{'generator':<22}{'n':>8}{'base':>9}{'half':>9}{'reduction':>11}"
    )
    for cell, method, n, b, a, r in rows:
        print(
            f"  {cell:<10}{str(method)[:21]:<22}{n:>8,}{b:>8.2f}%{a:>8.2f}%{r:>10.0f}%"
        )

    if not rows:
        raise SystemExit("no strata survived the min-count filter")

    macro = sum(r[5] for r in rows) / len(rows)
    print(f"\n  strata used: {len(rows)}   macro-average reduction: {macro:.0f}%")
    kept = sum(r[2] for r in rows)
    print(
        f"  coverage: {kept:,} of {len(d):,} designs ({100 * kept / len(d):.0f}%) after the min-count filter"
    )

    # ---- stratum-prior-only NULL -----------------------------------------
    # Score each design by its stratum's BASE RATE alone, with zero per-item signal, then
    # run the identical safest-first operation. Pooled, this ranks whole strata against
    # each other, so it measures exactly how much of the 70% is the ranker sorting easy
    # strata above hard ones rather than discriminating designs. Ties inside a stratum are
    # broken by a seeded shuffle, not by input order, or the "null" would silently inherit
    # whatever ordering the CSV happens to have.
    print("\nSTRATUM-PRIOR-ONLY NULL (no per-item signal)")
    prior = d.groupby(["target_cell", "method"])["measured_fail"].transform("mean")
    null_df = d.assign(pred_gap=-prior).sample(frac=1.0, random_state=0)
    null_after = safest_half_failure_rate(null_df)
    null_red = 100.0 * (1 - null_after / base)
    print(f"  pooled reduction using ONLY the stratum prior: {null_red:.0f}%")

    # ---- riskiest-2% enrichment ------------------------------------------
    def enrichment(df, frac=0.02):
        """Failure rate in the riskiest `frac` of a batch, over the batch's own base rate."""
        n = max(1, int(round(len(df) * frac)))
        riskiest = df.sort_values("pred_gap", ascending=True).head(n)
        b = df["measured_fail"].mean()
        return (riskiest["measured_fail"].mean() / b) if b else float("nan")

    print("\nRISKIEST-2% ENRICHMENT (x over the stratum's own base rate)")
    enrichments = []
    for cell, method, n, *_ in rows:
        g = d[(d.target_cell == cell) & (d.method == method)]
        e = enrichment(g)
        enrichments.append(e)
        print(f"  {cell:<10}{str(method)[:21]:<22}{n:>8,}{e:>9.2f}x")
    macro_e = sum(enrichments) / len(enrichments)
    print(f"\n  pooled riskiest-2% enrichment: {enrichment(d):.2f}x")
    print(f"  macro-average within stratum:  {macro_e:.2f}x")

    # ---- the decomposition the headline needs ----------------------------
    print("\nDECOMPOSITION OF THE 70% HEADLINE")
    print(f"  pooled reduction (published headline)      {red:.0f}%")
    print(f"  stratum-prior-only null (pooling alone)    {null_red:.0f}%")
    print(f"  within-stratum macro (per-item signal)     {macro:.0f}%")
    print(f"  headline minus within-stratum              {red - macro:.0f} points")
    verdict = (
        "SURVIVES conditioning (>=40%)" if macro >= 40 else "COLLAPSES toward the null"
    )
    print(f"  verdict: per-item signal {verdict}")


if __name__ == "__main__":
    main()
