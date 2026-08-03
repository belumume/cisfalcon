"""Matched, paired comparison of CisFalcon and AlphaGenome on the SAME 240 designs.

docs/independent-model-crosscheck.md used to say "AlphaGenome's 0.69 is lower than CisFalcon's
cross-lab 0.80". Those two numbers are measured on DIFFERENT evaluation sets: the 0.688 is on this
240-design stratified BALANCED subsample (base_fail = 0.5), the 0.80 on the full 93,435 designs at a
6.29% base rate. A metric is only comparable to another metric computed on the same rows.

alphagenome_crosscheck.json already ships CisFalcon's own gap for these same 240 rows (`cf_gap`), so
the matched comparison needs no new data and no API key. It reverses the naive ordering.

Positive control first: reproduce the published AlphaGenome AUROC from the JSON. That also pins the
score ORIENTATION (a flipped sign returns exactly 1 - AUROC), so the paired delta below cannot be a
silent sign error.

Run:
  python alphagenome_matched.py
"""

from pathlib import Path
import json
import numpy as np

JSON = Path(__file__).parent / "data" / "gosai_designed" / "alphagenome_crosscheck.json"

N_BOOT = 2000
SEED = 0


def auroc(score, y):
    """AUROC of `score` predicting y == 1, with mid-ranks for ties."""
    score = np.asarray(score, dtype=float)
    y = np.asarray(y, dtype=int)
    n1 = int(y.sum())
    n0 = len(y) - n1
    if not n1 or not n0:
        return float("nan")
    order = np.argsort(score, kind="mergesort")
    ranks = np.empty(len(score), dtype=float)
    ranks[order] = np.arange(1, len(score) + 1, dtype=float)
    # average ranks within tied score groups, or ties silently bias the estimate
    s_sorted = score[order]
    i = 0
    while i < len(s_sorted):
        j = i
        while j + 1 < len(s_sorted) and s_sorted[j + 1] == s_sorted[i]:
            j += 1
        if j > i:
            ranks[order[i : j + 1]] = ranks[order[i : j + 1]].mean()
        i = j + 1
    return float((ranks[y == 1].sum() - n1 * (n1 + 1) / 2) / (n1 * n0))


def main():
    d = json.loads(JSON.read_text())
    y = np.asarray(d["y"], dtype=int)
    ag = np.asarray(d["ag_gap"], dtype=float)
    cf = np.asarray(d["cf_gap"], dtype=float)
    n = len(y)

    # A higher predicted specificity gap means LESS likely to fail, so the failure score is -gap.
    ag_auroc = auroc(-ag, y)
    cf_auroc = auroc(-cf, y)

    print(f"n = {n}   base failure rate = {y.mean():.3f} (balanced by construction)\n")

    print("POSITIVE CONTROL (must match the published AlphaGenome AUROC in the JSON)")
    print(f"  recomputed AlphaGenome AUROC {ag_auroc:.4f}   published {d['auroc']:.4f}")
    ok = abs(ag_auroc - d["auroc"]) < 1e-6
    print(f"  control: {'PASS' if ok else 'FAIL'}\n")
    if not ok:
        raise SystemExit(
            "control failed; the orientation or the data does not match the published "
            "run, so the matched comparison below would be meaningless"
        )

    print("MATCHED on the same 240 rows")
    print(f"  CisFalcon   AUROC {cf_auroc:.4f}")
    print(f"  AlphaGenome AUROC {ag_auroc:.4f}")

    delta = ag_auroc - cf_auroc
    rng = np.random.default_rng(SEED)
    deltas = np.empty(N_BOOT)
    for b in range(N_BOOT):
        # PAIRED: resample designs, then score both models on the identical resample, so the
        # models' shared difficulty on a given design cancels instead of inflating the interval.
        #
        # These resamples are drawn WITH REPLACEMENT FROM THE FIXED 240 OBSERVED ROWS, not freshly
        # generated data. The percentiles below are therefore a nonparametric bootstrap CONFIDENCE
        # INTERVAL for the delta on this sample, not the spread of a hypothetical future run.
        idx = rng.integers(0, n, n)
        yb = y[idx]
        if yb.sum() == 0 or yb.sum() == len(yb):
            deltas[b] = np.nan
            continue
        deltas[b] = auroc(-ag[idx], yb) - auroc(-cf[idx], yb)
    deltas = deltas[~np.isnan(deltas)]
    lo, hi = np.percentile(deltas, [2.5, 97.5])

    print(
        f"\n  paired delta (AlphaGenome - CisFalcon) {delta:+.4f}"
        f"   95% CI [{lo:+.4f}, {hi:+.4f}]   ({len(deltas)} resamples, seed {SEED})"
    )
    spans_zero = lo <= 0 <= hi
    print(
        f"  the CI {'INCLUDES' if spans_zero else 'EXCLUDES'} zero: "
        + (
            "the two are statistically indistinguishable on this subsample"
            if spans_zero
            else "a real difference is detected"
        )
    )
    print(
        "\n  NOTE: the flagship 0.80 is NOT comparable here. It is measured on the full\n"
        "  93,435-design set at a 6.29% base rate, not on this balanced 240-row subsample."
    )


if __name__ == "__main__":
    main()
