#!/usr/bin/env python
"""Bootstrap 95% confidence intervals for every CisFalcon flagship number.

No GPU, no model download, no API key. Needs numpy + pandas (+ matplotlib for the
figure). Takes about two minutes (2000 bootstrap reps over 93,435 designs); every other
advertised script is seconds, so budget for this one.

    python bootstrap_ci.py

Answers the two questions a computational-genomics reviewer asks first about the
headline cross-lab AUROC 0.80 and the pooled 7.74x triage enrichment (conditioned: 2.59x macro,
see triage_conditioning_check.py): what is the
uncertainty on those numbers, and is the separation from a trivial baseline
statistically real. It reads the committed cross-lab scores and reports:

  * a design-level bootstrap CI (resample the 93,435 designs) - the tight CI,
  * a cluster bootstrap CI (resample the 24 cell x generator strata) - the
    honest wide CI that respects effective sample size, not raw N,
  * bootstrap CIs on the triage enrichment and the safest-half failure reduction,
  * paired-bootstrap CIs on the DIFFERENCE between CisFalcon and three trivial
    sequence baselines (random, GC-content, length), which must exclude zero for
    the headline separation to be defensible.

Seeded (default_rng(0)) so every number is reproducible to the digit. This is the
pre-registered rigor from build-readiness/10-EVAL-SPEC.md, made concrete.
"""

from pathlib import Path
import numpy as np
import pandas as pd

HERE = Path(__file__).parent
SCORED = HERE / "data" / "gosai_designed" / "designed_scored.csv"
BENCH = HERE / "data" / "gosai_designed" / "designed_benchmark.csv"
N_BOOT = 2000
SEED = 0


def rank_sum_auroc(labels: np.ndarray, scores: np.ndarray) -> float:
    """AUROC via average-rank sum. labels: 1=fail/0=pass; higher score = more risk."""
    n_pos = labels.sum()
    n_neg = len(labels) - n_pos
    if n_pos == 0 or n_neg == 0:
        return float("nan")
    ranks = pd.Series(scores).rank().values  # average ranks handle ties
    return (ranks[labels == 1].sum() - n_pos * (n_pos + 1) / 2) / (n_pos * n_neg)


def best_oriented_auroc(labels: np.ndarray, feature: np.ndarray) -> float:
    """AUROC of a trivial feature, oriented in whichever direction helps it most.

    A baseline gets the benefit of the doubt: we give the trivial feature its
    best possible orientation, so beating it is a strictly harder, more honest bar.
    """
    a = rank_sum_auroc(labels, feature)
    return max(a, 1.0 - a)


def triage_enrichment(y: np.ndarray, pred_gap: np.ndarray, frac: float = 0.02) -> float:
    """Enrichment of true failures in the riskiest `frac` (ranked by gap ascending)."""
    base = y.mean()
    if base == 0:
        return float("nan")
    order = np.argsort(pred_gap)
    k = int(round(frac * len(y)))
    return (y[order][:k].mean() / base) if k > 0 else float("nan")


def safest_half_reduction(y: np.ndarray, pred_gap: np.ndarray) -> float:
    """Fractional failure reduction if you synthesize only the safer-ranked half."""
    base = y.mean()
    if base == 0:
        return float("nan")
    order = np.argsort(pred_gap)  # riskiest first; safer half is the tail
    safe_half_fail = y[order][len(y) // 2 :].mean()
    return 1.0 - safe_half_fail / base


def ci(values: np.ndarray) -> tuple:
    """Percentile 95% CI, dropping NaN resamples."""
    v = values[~np.isnan(values)]
    return float(np.percentile(v, 2.5)), float(np.percentile(v, 97.5))


def gc_fraction(seq: str) -> float:
    s = seq.upper()
    return (s.count("G") + s.count("C")) / len(s) if s else 0.5


def main() -> None:
    scored = pd.read_csv(SCORED)
    y = scored["measured_fail"].values.astype(int)
    pred_gap = scored["pred_gap"].values
    risk = -pred_gap
    n = len(y)
    base = y.mean()

    # Trivial sequence baselines, merged on id (benefit-of-the-doubt orientation).
    bench = pd.read_csv(BENCH, usecols=["id", "sequence"])
    merged = scored[["id"]].merge(bench, on="id", how="left")
    assert len(merged) == n and merged["sequence"].isna().sum() == 0, "id merge gap"
    seqs = merged["sequence"].values
    gc = np.array([gc_fraction(s) for s in seqs])
    length = np.array([len(s) for s in seqs], dtype=float)
    rng0 = np.random.default_rng(SEED)
    randscore = rng0.random(n)

    # Point estimates.
    auroc = rank_sum_auroc(y, risk)
    enrich = triage_enrichment(y, pred_gap)
    reduction = safest_half_reduction(y, pred_gap)
    auroc_rand = best_oriented_auroc(y, randscore)
    auroc_gc = best_oriented_auroc(y, gc)
    auroc_len = best_oriented_auroc(y, length)

    # Strata for the cluster bootstrap.
    strat_key = (
        scored["target_cell"].astype(str) + "|" + scored["method"].astype(str)
    ).values
    strata = {}
    for i, k in enumerate(strat_key):
        strata.setdefault(k, []).append(i)
    strata = {k: np.array(v) for k, v in strata.items()}
    strata_keys = list(strata.keys())

    rng = np.random.default_rng(SEED)
    boot_auroc_design = np.empty(N_BOOT)
    boot_enrich = np.empty(N_BOOT)
    boot_reduction = np.empty(N_BOOT)
    boot_auroc_cluster = np.empty(N_BOOT)
    diff_rand = np.empty(N_BOOT)
    diff_gc = np.empty(N_BOOT)
    diff_len = np.empty(N_BOOT)
    # The paired baseline differences used to be reported design-level ONLY, under a heading
    # saying they "must exclude zero for the headline separation to be defensible" - while this
    # script's own docstring calls the cluster bootstrap the honest one. Compute both. The
    # conclusion is unchanged (all three still exclude zero); the cluster interval is the wide
    # one, and the summary line below now cites it.
    cdiff_rand = np.empty(N_BOOT)
    cdiff_gc = np.empty(N_BOOT)
    cdiff_len = np.empty(N_BOOT)

    for b in range(N_BOOT):
        idx = rng.integers(0, n, n)  # design-level resample (with replacement)
        yb, gapb, riskb = y[idx], pred_gap[idx], risk[idx]
        boot_auroc_design[b] = rank_sum_auroc(yb, riskb)
        boot_enrich[b] = triage_enrichment(yb, gapb)
        boot_reduction[b] = safest_half_reduction(yb, gapb)
        # paired: same resample scores CisFalcon and each trivial baseline
        cf = boot_auroc_design[b]
        diff_rand[b] = cf - best_oriented_auroc(yb, randscore[idx])
        diff_gc[b] = cf - best_oriented_auroc(yb, gc[idx])
        diff_len[b] = cf - best_oriented_auroc(yb, length[idx])
        # cluster resample: draw strata with replacement, pool their rows
        chosen = rng.integers(0, len(strata_keys), len(strata_keys))
        pooled = np.concatenate([strata[strata_keys[c]] for c in chosen])
        cf_c = rank_sum_auroc(y[pooled], risk[pooled])
        boot_auroc_cluster[b] = cf_c
        # same cluster resample scores CisFalcon and each trivial baseline (paired)
        yc = y[pooled]
        cdiff_rand[b] = cf_c - best_oriented_auroc(yc, randscore[pooled])
        cdiff_gc[b] = cf_c - best_oriented_auroc(yc, gc[pooled])
        cdiff_len[b] = cf_c - best_oriented_auroc(yc, length[pooled])

    def fmt(lo, hi, pct=False):
        return (
            (f"[{lo * 100:.1f}%, {hi * 100:.1f}%]")
            if pct
            else (f"[{lo:.4f}, {hi:.4f}]")
        )

    a_lo, a_hi = ci(boot_auroc_design)
    c_lo, c_hi = ci(boot_auroc_cluster)
    e_lo, e_hi = ci(boot_enrich)
    r_lo, r_hi = ci(boot_reduction)
    dr_lo, dr_hi = ci(diff_rand)
    dg_lo, dg_hi = ci(diff_gc)
    dl_lo, dl_hi = ci(diff_len)
    cr_lo, cr_hi = ci(cdiff_rand)
    cg_lo, cg_hi = ci(cdiff_gc)
    cl_lo, cl_hi = ci(cdiff_len)

    L = "=" * 74
    print(L)
    print("  CisFalcon flagship, bootstrap 95% CIs (seed=0, 2000 resamples)")
    print(f"  source: {SCORED.relative_to(HERE)}  (n={n:,} independent designs)")
    print(L)
    print(f"  base failure rate                         : {base * 100:.2f}%")
    print()
    print(f"  cross-lab AUROC                           : {auroc:.4f}")
    print(f"    design-level 95% CI (n={n:,})        : {fmt(a_lo, a_hi)}")
    print(f"    cluster 95% CI (24 cell x generator)    : {fmt(c_lo, c_hi)}")
    print()
    print(f"  triage enrichment, riskiest 2%            : {enrich:.2f}x")
    print(f"    95% CI                                  : [{e_lo:.2f}x, {e_hi:.2f}x]")
    print(f"  safest-half failure reduction             : {reduction * 100:.0f}%")
    print(f"    95% CI                                  : {fmt(r_lo, r_hi, pct=True)}")
    print()
    print("  Paired difference vs best-oriented trivial baselines (must exclude 0):")
    print("    (design-level CI first, then the wider cluster CI over the 24 strata)")
    print(
        f"    vs random  (baseline AUROC {auroc_rand:.3f})     : +{auroc - auroc_rand:.3f}\n"
        f"        design  {fmt(dr_lo, dr_hi)}   cluster {fmt(cr_lo, cr_hi)}"
    )
    print(
        f"    vs GC%     (baseline AUROC {auroc_gc:.3f})     : +{auroc - auroc_gc:.3f}\n"
        f"        design  {fmt(dg_lo, dg_hi)}   cluster {fmt(cg_lo, cg_hi)}"
    )
    print(
        f"    vs length  (baseline AUROC {auroc_len:.3f})     : +{auroc - auroc_len:.3f}\n"
        f"        design  {fmt(dl_lo, dl_hi)}   cluster {fmt(cl_lo, cl_hi)}"
    )
    print(L)
    # Cite the CLUSTER basis in the summary: it is the one the docstring calls honest, and it
    # is the wider of the two, so "excludes zero" on it is the defensible claim.
    excl = all(lo > 0 for lo in (cr_lo, cg_lo, cl_lo))
    print(f"  Every baseline-difference CLUSTER CI excludes zero: {excl}")
    print(L)

    _write_figure(
        auroc,
        (a_lo, a_hi),
        (c_lo, c_hi),
        auroc_rand,
        auroc_gc,
        auroc_len,
        boot_auroc_design,
    )


def _write_figure(auroc, design_ci, cluster_ci, a_rand, a_gc, a_len, boot_design):
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception as e:  # figure is a bonus, never block the numbers
        print(f"  (figure skipped: {e})")
        return
    out = HERE / "docs" / "bootstrap_ci.png"
    out.parent.mkdir(exist_ok=True)
    fig, ax = plt.subplots(figsize=(7.2, 3.2), dpi=140)
    ax.hist(boot_design, bins=60, color="#3b6ea5", alpha=0.55, edgecolor="none")
    top = ax.get_ylim()[1]
    # one collapsed marker for the trivial baselines (all ~0.50-0.51, they overlap)
    base_x = min(a_gc, a_rand, a_len)
    ax.axvspan(
        min(a_gc, a_rand, a_len), max(a_gc, a_rand, a_len), color="#999", alpha=0.4
    )
    ax.axvline(base_x, color="#888", lw=1.4, ls="--")
    ax.text(
        base_x - 0.006,
        top * 0.9,
        "trivial baselines\n(GC / length / random) ~0.51",
        color="#666",
        fontsize=8,
        ha="right",
        va="top",
    )
    ax.axvline(auroc, color="#b5341f", lw=2.0)
    ax.text(
        auroc + 0.004,
        top * 0.9,
        "CisFalcon\nAUROC 0.80",
        color="#b5341f",
        fontsize=8,
        va="top",
    )
    ax.axvspan(design_ci[0], design_ci[1], color="#b5341f", alpha=0.14)
    ax.set_xlim(0.45, 0.85)
    ax.set_xlabel("cross-lab AUROC (2000 design-level bootstrap resamples)")
    ax.set_yticks([])
    ax.set_title(
        f"CisFalcon cross-lab AUROC 95% CI: [{design_ci[0]:.3f}, {design_ci[1]:.3f}] "
        f"design / [{cluster_ci[0]:.3f}, {cluster_ci[1]:.3f}] cluster",
        fontsize=9,
    )
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    fig.tight_layout()
    fig.savefig(out)
    print(f"  figure written: {out.relative_to(HERE)}")


if __name__ == "__main__":
    main()
