#!/usr/bin/env python
"""The product's core value, as a picture: safest-first triage vs synthesize-blind.

No GPU, no download. Reads the committed cross-lab per-design scores and draws the
cumulative specificity-failure rate in what you synthesize as you work down a
CisFalcon-ranked (safest-first) batch, against the flat base rate you get with no
triage. The gap between the two curves is the wasted synthesis CisFalcon saves.

    python triage_curve.py   ->   docs/triage_curve.png

The curve is POOLED across the mixed 93,435-design batch, and the repo disowns the pooled
figure as evidence of sequence-level signal, so the figure has to say which basis it is on.
It used to annotate a bare "70% fewer" with no basis label while the README table two lines
above it published the conditioned 41% and the 91% sequence-free null, so a reader
combining the two derived a contradiction with nothing on the figure to resolve it.

Both counterparts are RECOMPUTED here rather than pasted in, using the same min-count filter
and the same safest-half operation as triage_conditioning_check.py, so the caption cannot
drift away from the analysis it quotes.
"""

from pathlib import Path
import numpy as np
import pandas as pd

HERE = Path(__file__).parent
CSV = HERE / "data" / "gosai_designed" / "designed_scored.csv"

MIN_PER_CLASS = 10  # cell_prior_baseline.py: a stratum needs >=10 fail and >=10 pass


def _safest_half_rate(df):
    """Measured failure rate (%) in the safer half of a pred_gap-ranked frame."""
    if len(df) < 2:
        return None
    ranked = df.sort_values("pred_gap", ascending=False)
    return 100.0 * ranked.head(len(ranked) // 2)["measured_fail"].mean()


def conditioned_and_null(df, base_pct):
    """Return (macro within-stratum reduction %, stratum-prior-only null reduction %, n_strata).

    Same logic as triage_conditioning_check.py so the figure and that script agree by
    construction instead of by someone remembering to update both.
    """
    reductions = []
    for _, g in df.groupby(["target_cell", "method"]):
        n_fail = g["measured_fail"].sum()
        if n_fail < MIN_PER_CLASS or (len(g) - n_fail) < MIN_PER_CLASS:
            continue
        b = 100.0 * g["measured_fail"].mean()
        a = _safest_half_rate(g)
        if b:
            reductions.append(100.0 * (1 - a / b))
    macro = sum(reductions) / len(reductions) if reductions else float("nan")

    prior = df.groupby(["target_cell", "method"])["measured_fail"].transform("mean")
    null_df = df.assign(pred_gap=-prior).sample(frac=1.0, random_state=0)
    null_red = 100.0 * (1 - _safest_half_rate(null_df) / base_pct)
    return macro, null_red, len(reductions)


def main() -> None:
    df = pd.read_csv(CSV)
    y = df["measured_fail"].values.astype(int)
    pred_gap = df["pred_gap"].values
    n = len(y)
    base = y.mean()

    order = np.argsort(-pred_gap)  # safest (largest gap) first
    ys = y[order]
    frac = np.arange(1, n + 1) / n
    cum_fail = np.cumsum(ys) / np.arange(1, n + 1)  # failure rate in what you've made

    half = cum_fail[n // 2 - 1]
    print(f"base failure rate                : {base * 100:.2f}%")
    print(
        f"safest 50% synthesized, fail rate: {half * 100:.2f}%  ({(1 - half / base) * 100:.0f}% fewer, POOLED)"
    )
    macro, null_red, n_strata = conditioned_and_null(df, base * 100)
    print(
        f"conditioned within (cell x generator): {macro:.0f}% macro over {n_strata} strata"
    )
    print(f"sequence-free stratum-prior null : {null_red:.0f}% pooled")

    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception as e:
        print(f"(figure skipped: {e})")
        return
    out = HERE / "docs" / "triage_curve.png"
    out.parent.mkdir(exist_ok=True)
    fig, ax = plt.subplots(figsize=(6.6, 3.6), dpi=140)
    ax.plot(
        frac * 100,
        cum_fail * 100,
        color="#2f7d5b",
        lw=2.2,
        label="CisFalcon safest-first",
    )
    ax.axhline(
        base * 100,
        color="#b5341f",
        lw=1.6,
        ls="--",
        label=f"synthesize blind ({base * 100:.1f}%)",
    )
    ax.axvline(50, color="#999", lw=1.0, ls=":")
    ax.annotate(
        f"safest half:\n{half * 100:.1f}% fail\n({(1 - half / base) * 100:.0f}% fewer, POOLED)",
        xy=(50, half * 100),
        xytext=(58, base * 100 * 0.62),
        fontsize=8.5,
        color="#2f7d5b",
        arrowprops=dict(arrowstyle="->", color="#2f7d5b", lw=1),
    )
    ax.set_xlabel(
        "percent of the batch synthesized (ranked safest-first)\n"
        f"Pooled across a mixed batch. Conditioned within (cell x generator) the reduction is "
        f"{macro:.0f}% macro over {n_strata} strata;\na sequence-free stratum-prior rule scores "
        f"{null_red:.0f}% pooled, so the pooled figure is not per-design signal "
        f"(triage_conditioning_check.py).",
        fontsize=7.2,
    )
    ax.set_ylabel("specificity-failure rate\nin what you synthesize (%)")
    ax.set_xlim(0, 100)
    ax.set_ylim(0, base * 100 * 1.15)
    ax.legend(loc="upper left", frameon=False, fontsize=8.5)
    ax.set_title(
        "Rank safest-first and you spend synthesis budget on the designs that work",
        fontsize=9,
    )
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    fig.tight_layout()
    fig.savefig(out)
    print(f"figure written: {out.relative_to(HERE)}")


if __name__ == "__main__":
    main()
