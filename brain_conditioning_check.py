"""Does the BRAIN triage headline survive the same conditioning as the flagship one?

triage_conditioning_check.py showed that the pooled 70% safest-half reduction is mostly
the ranker sorting easy strata above hard ones: conditioned within (cell x generator) it
is 41% macro, and a sequence-free rule that ranks only by each stratum's base rate scores
91% pooled. The brain figure (SKNSH, 10.06% -> 4.19%, "58% fewer") is the number the
disease-impact case rests on, and it was published pooled across generators, so it needs
the same test.

Positive control first: reproduce brain_triage.py's published pooled SKNSH numbers. If the
control does not reproduce, the conditioned numbers below mean nothing (a metric script
with no known-answer assert is an instrument nobody has shown to work).

Run:
  python brain_conditioning_check.py <path-to-cisfalcon-clone>
"""

import os
import sys
import pandas as pd

REPO = sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(os.path.abspath(__file__))
CSV = f"{REPO}/data/gosai_designed/designed_scored.csv"

CELL = "SKNSH"  # the brain-derived line the disease-impact lane reports on

# Published, from the repo's own brain_triage.py output
PUB_BASE, PUB_AFTER = 10.06, 4.19

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


def enrichment(df, frac=0.02):
    """Failure rate in the riskiest `frac` of a batch, over the batch's own base rate."""
    n = max(1, int(round(len(df) * frac)))
    riskiest = df.sort_values("pred_gap", ascending=True).head(n)
    b = df["measured_fail"].mean()
    return (riskiest["measured_fail"].mean() / b) if b else float("nan")


def main():
    full = pd.read_csv(CSV)
    d = full[full["target_cell"] == CELL]
    print(
        f"{CELL} designs {len(d):,} of {len(full):,}   generators {d.method.nunique()}\n"
    )

    # ---- positive control -------------------------------------------------
    base = 100.0 * d["measured_fail"].mean()
    after = safest_half_failure_rate(d)
    red = 100.0 * (1 - after / base)
    print("POSITIVE CONTROL (pooled within SKNSH, must match brain_triage.py)")
    print(f"  base rate      {base:.2f}%   published {PUB_BASE}%")
    print(f"  safest half    {after:.2f}%   published {PUB_AFTER}%")
    print(f"  reduction      {red:.0f}%")
    ok = abs(base - PUB_BASE) < 0.05 and abs(after - PUB_AFTER) < 0.05
    print(f"  control: {'PASS' if ok else 'FAIL'}\n")
    if not ok:
        raise SystemExit(
            "control failed; conditioned numbers below would be meaningless"
        )

    # ---- conditioned within each generator stratum ------------------------
    # The cell is already held fixed, so conditioning on the generator here is exactly the
    # (cell x generator) conditioning triage_conditioning_check.py applies globally,
    # restricted to this one cell.
    print(f"CONDITIONED within each ({CELL} x generator) stratum")
    rows = []
    for method, g in d.groupby("method"):
        n_fail = g["measured_fail"].sum()
        n_pass = len(g) - n_fail
        if n_fail < MIN_PER_CLASS or n_pass < MIN_PER_CLASS:
            continue
        b = 100.0 * g["measured_fail"].mean()
        a = safest_half_failure_rate(g)
        rows.append(
            (
                method,
                len(g),
                b,
                a,
                100.0 * (1 - a / b) if b else float("nan"),
                enrichment(g),
            )
        )

    if not rows:
        raise SystemExit("no strata survived the min-count filter")

    rows.sort(key=lambda r: -r[1])
    print(
        f"  {'generator':<22}{'n':>8}{'base':>9}{'half':>9}{'reduction':>11}{'risk-2%':>10}"
    )
    for method, n, b, a, r, e in rows:
        print(
            f"  {str(method)[:21]:<22}{n:>8,}{b:>8.2f}%{a:>8.2f}%{r:>10.0f}%{e:>9.2f}x"
        )

    macro = sum(r[4] for r in rows) / len(rows)
    macro_e = sum(r[5] for r in rows) / len(rows)
    kept = sum(r[1] for r in rows)
    print(f"\n  strata used: {len(rows)}   macro-average reduction: {macro:.0f}%")
    print(f"  macro-average riskiest-2% enrichment: {macro_e:.2f}x")
    print(
        f"  coverage: {kept:,} of {len(d):,} {CELL} designs "
        f"({100 * kept / len(d):.0f}%) after the min-count filter"
    )

    # ---- generator-prior-only NULL ---------------------------------------
    # Score each design by its generator's BASE RATE alone, with zero per-item signal, then
    # run the identical safest-first operation. Within this one cell it measures how much of
    # the 58% is the ranker sorting easy generators above hard ones rather than
    # discriminating designs. Ties inside a stratum are broken by a seeded shuffle, not by
    # input order, or the "null" would silently inherit the CSV's own ordering.
    print(f"\nGENERATOR-PRIOR-ONLY NULL within {CELL} (no per-item signal)")
    prior = d.groupby("method")["measured_fail"].transform("mean")
    null_df = d.assign(pred_gap=-prior).sample(frac=1.0, random_state=0)
    null_after = safest_half_failure_rate(null_df)
    null_red = 100.0 * (1 - null_after / base)
    print(f"  reduction using ONLY the generator prior: {null_red:.0f}%")

    # ---- the decomposition the brain headline needs -----------------------
    print(f"\nDECOMPOSITION OF THE {red:.0f}% BRAIN HEADLINE")
    print(f"  pooled within {CELL} (published headline)   {red:.0f}%")
    print(f"  generator-prior-only null (pooling alone)  {null_red:.0f}%")
    print(f"  within-stratum macro (per-item signal)     {macro:.0f}%")
    print(f"  headline minus within-stratum              {red - macro:.0f} points")
    print(
        f"  verdict: the sequence-free null ({null_red:.0f}%) "
        f"{'BEATS' if null_red > red else 'does not beat'} the published headline "
        f"({red:.0f}%); the honest per-design figure is the macro {macro:.0f}%"
    )


if __name__ == "__main__":
    main()
