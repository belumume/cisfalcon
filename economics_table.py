"""Regenerate the triage economics table and figure from the committed data.

Why this script exists: docs/cisfalcon_triage_economics.csv and docs/cisfalcon_economics.png were
hand-authored from the POOLED riskiest-2% operating point (7.74x enrichment, PPV 0.49). The
2026-08-03 conditioning correction disowned the pooled triage figures as evidence of per-design
signal, because a sequence-free rule that ranks only by each (cell x generator) stratum's base rate
beats them. The dollar figure is the most-remembered quantity in the submission, so it must carry
its basis and both numbers, not the flattering one alone.

Both bases are derived here from data/gosai_designed/designed_scored.csv rather than transcribed, so
the table cannot drift from the scripts again.

  POOLED       riskiest-2% across the whole mixed batch. An upper bound. Rides the stratum prior.
  CONDITIONED  macro-average riskiest-2% enrichment within (cell x generator), the same axes the
               published 0.66 joint AUROC uses. This is the honest per-design operating point.

Positive control first: reproduce the published pooled enrichment / PPV and the currently shipped
pooled dollar figures. If the control fails, nothing is written.

Run:
  python economics_table.py
"""

from pathlib import Path
import pandas as pd

HERE = Path(__file__).parent
CSV_IN = HERE / "data" / "gosai_designed" / "designed_scored.csv"
CSV_OUT = HERE / "docs" / "cisfalcon_triage_economics.csv"
PNG_OUT = HERE / "docs" / "cisfalcon_economics.png"

BATCH = 200  # designs per batch
FLAG_FRAC = 0.02  # flag the riskiest 2%
SPEND_LO, SPEND_HI = (
    950,
    3500,
)  # $ per pursued design, FULL committed spend (incl. follow-up)
RECHECK_LO, RECHECK_HI = 40, 120  # $ per flagged design, cheap orthogonal recheck

MIN_PER_CLASS = 10  # cell_prior_baseline.py: ">=10 fail and >=10 pass"

# Published pooled values this script must reproduce before writing anything.
# These are the anchors reproduce_flagship.py prints ("of those, truly fail: 48.7%",
# "enrichment over base rate: 7.74x"), so they pin both the data and the operating point.
PUB_ENRICH, PUB_PPV = 7.74, 0.487

# The PREVIOUSLY SHIPPED dollar figures, kept only to report the delta. They are NOT a control:
# they were computed from the ROUNDED PPV 0.49 rather than the true 0.4869, which overstates the
# averted spend by about 0.6%. The recompute below uses the unrounded value.
OLD_AVERTED_LO, OLD_AVERTED_HI = 1862, 6860


def enrichment_and_ppv(df, frac=FLAG_FRAC):
    n = max(1, int(round(len(df) * frac)))
    riskiest = df.sort_values("pred_gap", ascending=True).head(n)
    base = df["measured_fail"].mean()
    ppv = riskiest["measured_fail"].mean()
    return (ppv / base if base else float("nan")), ppv


def main():
    d = pd.read_csv(CSV_IN)
    base = d["measured_fail"].mean()

    pooled_enrich, pooled_ppv = enrichment_and_ppv(d)

    # conditioned: macro-average enrichment across the same 14 strata as the 0.66 joint AUROC
    enrichments = []
    for (_cell, _method), g in d.groupby(["target_cell", "method"]):
        n_fail = g["measured_fail"].sum()
        if n_fail < MIN_PER_CLASS or (len(g) - n_fail) < MIN_PER_CLASS:
            continue
        enrichments.append(enrichment_and_ppv(g)[0])
    if not enrichments:
        raise SystemExit("no strata survived the min-count filter")
    cond_enrich = sum(enrichments) / len(enrichments)
    # Applied to the batch's own base rate, the conditioned enrichment implies this precision.
    cond_ppv = cond_enrich * base

    flagged = int(round(BATCH * FLAG_FRAC))

    def economics(ppv):
        caught = flagged * ppv
        return {
            "caught": caught,
            "averted_lo": caught * SPEND_LO,
            "averted_hi": caught * SPEND_HI,
            "recheck_lo": flagged * RECHECK_LO,
            "recheck_hi": flagged * RECHECK_HI,
            "net_lo": caught * SPEND_LO - flagged * RECHECK_LO,
            "net_hi": caught * SPEND_HI - flagged * RECHECK_HI,
        }

    pooled = economics(pooled_ppv)
    cond = economics(cond_ppv)

    # ---- positive control -------------------------------------------------
    print("POSITIVE CONTROL (pooled, must match reproduce_flagship.py)")
    print(f"  enrichment    {pooled_enrich:.2f}x   published {PUB_ENRICH}x")
    print(f"  PPV           {pooled_ppv:.3f}    published {PUB_PPV}")
    ok = abs(pooled_enrich - PUB_ENRICH) < 0.01 and abs(pooled_ppv - PUB_PPV) < 0.001
    print(f"  control: {'PASS' if ok else 'FAIL'}\n")
    if not ok:
        raise SystemExit("control failed; refusing to write the table or the figure")

    print("ROUNDING CORRECTION to the previously shipped pooled figures")
    print(
        f"  averted lo   ${pooled['averted_lo']:,.0f}  (was ${OLD_AVERTED_LO:,}, "
        f"computed from the rounded PPV 0.49)"
    )
    print(
        f"  averted hi   ${pooled['averted_hi']:,.0f}  (was ${OLD_AVERTED_HI:,}, "
        f"computed from the rounded PPV 0.49)\n"
    )

    print(f"CONDITIONED (macro within cell x generator, {len(enrichments)} strata)")
    print(f"  enrichment    {cond_enrich:.2f}x")
    print(f"  implied PPV   {cond_ppv:.3f}")
    print(f"  net savings  ${cond['net_lo']:,.0f} to ${cond['net_hi']:,.0f}")
    print(f"  vs pooled    ${pooled['net_lo']:,.0f} to ${pooled['net_hi']:,.0f}\n")

    def money(x):
        return f"${x:,.0f}"

    rows = [
        (
            "Basis",
            f"CONDITIONED macro within (cell x generator), {len(enrichments)} strata (the honest per-design case)",
            "POOLED riskiest-2% across a mixed batch (upper bound; rides the stratum prior)",
        ),
        ("Batch size (designs)", BATCH, BATCH),
        ("Measured failure base rate", f"{base * 100:.2f}%", f"{base * 100:.2f}%"),
        ("Designs flagged (riskiest 2%)", flagged, flagged),
        ("Enrichment over base rate", f"{cond_enrich:.2f}x", f"{pooled_enrich:.2f}x"),
        ("Flag precision (PPV)", f"{cond_ppv:.3f}", f"{pooled_ppv:.3f}"),
        (
            "Real failures caught early / batch",
            f"{cond['caught']:.2f}",
            f"{pooled['caught']:.2f}",
        ),
        (
            "Full committed spend / design",
            f"{money(SPEND_LO)} to {money(SPEND_HI)}",
            f"{money(SPEND_LO)} to {money(SPEND_HI)}",
        ),
        (
            "Cheap orthogonal recheck / flag",
            f"{money(RECHECK_LO)} to {money(RECHECK_HI)}",
            f"{money(RECHECK_LO)} to {money(RECHECK_HI)}",
        ),
        (
            "Wasted spend averted / batch",
            f"{money(cond['averted_lo'])} to {money(cond['averted_hi'])}",
            f"{money(pooled['averted_lo'])} to {money(pooled['averted_hi'])}",
        ),
        (
            "Recheck cost / batch",
            f"{money(cond['recheck_lo'])} to {money(cond['recheck_hi'])}",
            f"{money(pooled['recheck_lo'])} to {money(pooled['recheck_hi'])}",
        ),
        (
            "Net savings / batch",
            f"{money(cond['net_lo'])} to {money(cond['net_hi'])}",
            f"{money(pooled['net_lo'])} to {money(pooled['net_hi'])}",
        ),
    ]
    out = pd.DataFrame(
        rows, columns=["Quantity", "Conditioned (headline)", "Pooled (upper bound)"]
    )
    out.to_csv(CSV_OUT, index=False, lineterminator="\n")
    print(f"wrote {CSV_OUT}")

    # ---- figure -----------------------------------------------------------
    # Every printed number and the CSV have already landed above. matplotlib is optional
    # here for the same reason it is in bootstrap_ci.py and triage_curve.py: an unguarded
    # import turned a complete reproduction into exit 1 plus a traceback, which any && chain
    # or CI step reads as "the reproduction failed".
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception as e:  # figure is a bonus, never block the numbers
        print(f"  (figure skipped: {e})")
        return

    fig, ax = plt.subplots(figsize=(9, 4.6))
    labels = [
        "Conditioned\n(within cell x generator)",
        "Pooled\n(mixed batch, upper bound)",
    ]
    los = [cond["net_lo"], pooled["net_lo"]]
    his = [cond["net_hi"], pooled["net_hi"]]
    x = range(2)
    ax.bar(x, his, color="#cfe0f5", label=f"high spend basis (${SPEND_HI:,}/design)")
    ax.bar(x, los, color="#3b6fb0", label=f"low spend basis (${SPEND_LO:,}/design)")
    for i, (lo, hi) in enumerate(zip(los, his)):
        # Escape the dollar signs. Two unescaped '$' in ONE string switch matplotlib into
        # mathtext, which silently swallows them: "$1,690 to $6,336" renders "1,690to6,336".
        ax.text(
            i,
            hi,
            rf" \${lo:,.0f} to \${hi:,.0f}",
            ha="center",
            va="bottom",
            fontsize=10,
        )
    ax.set_xticks(list(x))
    ax.set_xticklabels(labels, fontsize=10)
    ax.set_ylabel("Net savings per 200-design batch ($)")
    ax.set_title(
        f"Triage economics: flag the riskiest 2%\n"
        f"conditioned {cond_enrich:.2f}x / PPV {cond_ppv:.3f}   vs   "
        f"pooled {pooled_enrich:.2f}x / PPV {pooled_ppv:.3f}",
        fontsize=11,
    )
    ax.set_ylim(0, max(his) * 1.22)
    ax.legend(frameon=False, fontsize=9)
    fig.text(
        0.5,
        0.005,
        "The conditioned column is the honest per-design case. The pooled column is an upper bound: "
        "a sequence-free\nstratum-prior rule reproduces most of the pooled triage effect "
        "(see triage_conditioning_check.py).",
        ha="center",
        fontsize=8,
        color="#444",
    )
    fig.tight_layout(rect=(0, 0.07, 1, 1))
    fig.savefig(PNG_OUT, dpi=150)
    print(f"wrote {PNG_OUT}")


if __name__ == "__main__":
    main()
