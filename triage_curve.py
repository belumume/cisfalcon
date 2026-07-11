#!/usr/bin/env python
"""The product's core value, as a picture: safest-first triage vs synthesize-blind.

No GPU, no download. Reads the committed cross-lab per-design scores and draws the
cumulative specificity-failure rate in what you synthesize as you work down a
CisFalcon-ranked (safest-first) batch, against the flat base rate you get with no
triage. The gap between the two curves is the wasted synthesis CisFalcon saves.

    python triage_curve.py   ->   docs/triage_curve.png
"""

from pathlib import Path
import numpy as np
import pandas as pd

HERE = Path(__file__).parent
CSV = HERE / "data" / "gosai_designed" / "designed_scored.csv"


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
        f"safest 50% synthesized, fail rate: {half * 100:.2f}%  ({(1 - half / base) * 100:.0f}% fewer)"
    )

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
        f"safest half:\n{half * 100:.1f}% fail\n({(1 - half / base) * 100:.0f}% fewer)",
        xy=(50, half * 100),
        xytext=(58, base * 100 * 0.62),
        fontsize=8.5,
        color="#2f7d5b",
        arrowprops=dict(arrowstyle="->", color="#2f7d5b", lw=1),
    )
    ax.set_xlabel("percent of the batch synthesized (ranked safest-first)")
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
