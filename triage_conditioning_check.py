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
    # Every design inside a stratum ties on the prior, because the prior IS the score, so the
    # safer half is decided entirely by the tie-break and this figure MOVES WITH THE SEED.
    # Reporting one shuffle as a point estimate is a number without its basis: it ran 90.1% to
    # 90.8% across 12 seeds, and the 91% this used to print was seed 0 rounding up. The spread
    # is the honest form; the conclusion (a sequence-free rule beats the pooled figure) is
    # unchanged at either end of it.
    null_reds = []
    for _seed in range(12):
        _nd = d.assign(pred_gap=-prior).sample(frac=1.0, random_state=_seed)
        null_reds.append(100.0 * (1 - safest_half_failure_rate(_nd) / base))
    null_red = sum(null_reds) / len(null_reds)
    print(
        f"  pooled reduction using ONLY the stratum prior: {null_red:.1f}% "
        f"(range {min(null_reds):.1f}-{max(null_reds):.1f} over 12 tie-break seeds)"
    )

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
    # The difference used to be computed on the UNROUNDED values while the operands were
    # displayed rounded, so the block printed 70, 41 and "28 points" and a reader doing the
    # subtraction on screen got 29. Round the operands once and derive the difference from
    # the rounded values, so the arithmetic reconciles AND the operands still match the 70 /
    # 91 / 41 published everywhere else (printing 69.7 / 90.5 / 41.2 would fix the internal
    # arithmetic by introducing a fresh mismatch against every other surface).
    red_r, null_r, macro_r = round(red), round(null_red), round(macro)
    print(f"  pooled reduction (published headline)      {red_r:.0f}%")
    print(f"  stratum-prior-only null (pooling alone)    {null_r:.0f}%")
    print(f"  within-stratum macro (per-item signal)     {macro_r:.0f}%")
    print(f"  headline minus within-stratum              {red_r - macro_r:.0f} points")
    # No binary verdict here. The previous version printed "SURVIVES conditioning (>=40%)"
    # against a 40% cut that appears in no shipped document, was not pre-registered, and sat
    # 1.2 points below the measured 41.2% - so the most quotable line of the output was a
    # post-hoc pass/fail that a small data or filter change would flip. The three numbers
    # above are the finding; they carry it without a threshold nobody committed to.
    print(
        f"  the per-item signal is the {macro_r:.0f}% macro, not the {red_r:.0f}% pooled headline;\n"
        f"  a sequence-free stratum-prior rule reaches {null_r:.0f}% pooled with no sequence access"
    )


if __name__ == "__main__":
    main()
