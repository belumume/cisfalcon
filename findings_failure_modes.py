"""Finding: a systematic reliability map of AI enhancer-design methods.

Honest framing: the specificity-failure LABELS are Gosai/Tewhey 2024 wet-lab MPRA
measurements, not our discovery. The contribution here is (1) turning that scattered
data into a systematic per-method / per-target-cell reliability map, and (2) showing a
FROZEN cross-lab verifier predicts where those failures cluster. No model training, no
new wet-lab. Pure analysis of the committed designed_scored.csv.

    python findings_failure_modes.py   ->   docs/failure_modes.png + prints the finding
"""

from pathlib import Path

import pandas as pd
from sklearn.metrics import roc_auc_score

HERE = Path(__file__).resolve().parent

d = pd.read_csv(HERE / "data" / "gosai_designed" / "designed_scored.csv")

# fix AUROC orientation: a failing design (fires off-target) has a LOW specificity gap,
# so rank failure risk by -pred_gap. Verify the pooled value matches the committed 0.8013.
pooled = roc_auc_score(d.measured_fail, -d.pred_gap)
assert abs(pooled - 0.8013) < 0.01, f"orientation check failed: pooled={pooled:.4f}"


def auroc(sub):
    if sub.measured_fail.nunique() < 2:
        return float("nan")
    return roc_auc_score(sub.measured_fail, -sub.pred_gap)


NAMES = {
    "hmc": "Hamiltonian MC",
    "sa": "Simulated Annealing",
    "sa_rep": "SA (replicate)",
    "al": "AdaLead",
    "fsp": "FastSeqProp",
}
CELLS = {"SKNSH": "SK-N-SH (brain)", "HepG2": "HepG2 (liver)", "K562": "K562 (blood)"}

print(f"pooled cross-lab AUROC (orientation-verified): {pooled:.4f}")
print(f"overall specificity-failure rate: {d.measured_fail.mean() * 100:.2f}%\n")

# main generators (n >= 5000)
g = d.groupby("method").agg(n=("id", "size"), fr=("measured_fail", "mean"))
g = g[g.n >= 5000].copy()
g["auroc"] = [auroc(d[d.method == m]) for m in g.index]
g = g.sort_values("fr", ascending=False)
print("=== per AI design method (n>=5000) ===")
for m, r in g.iterrows():
    print(
        f"  {NAMES.get(m, m):22s} fail={r.fr * 100:5.1f}%   CisFalcon AUROC={r.auroc:.3f}"
    )

c = (
    d.groupby("target_cell")
    .agg(n=("id", "size"), fr=("measured_fail", "mean"))
    .sort_values("fr", ascending=False)
)
print("\n=== per target cell ===")
for cell, r in c.iterrows():
    print(f"  {CELLS.get(cell, cell):18s} fail={r.fr * 100:5.1f}%")

# The table above is the finding; the figure is a bonus. matplotlib used to be imported at
# module top level, so an environment without it produced NO output at all rather than a
# degraded run. Same try/except the sibling scripts use (bootstrap_ci.py, triage_curve.py).
try:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
except Exception as e:  # figure is a bonus, never block the numbers
    print(f"\n(figure skipped: {e})")
    raise SystemExit(0)

# figure: two panels
fig, (a1, a2) = plt.subplots(1, 2, figsize=(11, 4.3))
INK, TEXT, TEAL, RED, GREY = "#0a0d13", "#e8ecf4", "#38e1c4", "#fb7185", "#6b7280"
for ax in (a1, a2):
    ax.set_facecolor(INK)
    for s in ax.spines.values():
        s.set_visible(False)
    ax.tick_params(colors=TEXT, labelsize=9)
fig.patch.set_facecolor(INK)

gm = g.sort_values("fr")
bars = a1.barh(
    [NAMES.get(m, m) for m in gm.index],
    gm.fr * 100,
    color=[RED if v > 10 else TEAL for v in gm.fr * 100],
    zorder=3,
)
for b, v in zip(bars, gm.fr * 100):
    a1.text(
        v + 0.4,
        b.get_y() + b.get_height() / 2,
        f"{v:.1f}%",
        va="center",
        color=TEXT,
        fontsize=10,
        fontweight="bold",
    )
a1.set_title(
    "Specificity-failure rate by AI design method",
    color=TEXT,
    fontsize=11.5,
    fontweight="bold",
    pad=8,
)
a1.set_xlabel("% of designs that fire in the wrong cell", color=TEXT, fontsize=9)
a1.set_xlim(0, max(gm.fr * 100) * 1.18)

cm = c.sort_values("fr")
bars2 = a2.barh(
    [CELLS.get(x, x) for x in cm.index],
    cm.fr * 100,
    color=[RED if v > 5 else TEAL for v in cm.fr * 100],
    zorder=3,
)
for b, v in zip(bars2, cm.fr * 100):
    a2.text(
        v + 0.2,
        b.get_y() + b.get_height() / 2,
        f"{v:.1f}%",
        va="center",
        color=TEXT,
        fontsize=10,
        fontweight="bold",
    )
a2.set_title(
    "Failure rate by target cell",
    color=TEXT,
    fontsize=11.5,
    fontweight="bold",
    pad=8,
)
a2.set_xlabel("% of designs that fire in the wrong cell", color=TEXT, fontsize=9)
a2.set_xlim(0, max(cm.fr * 100) * 1.25)

fig.text(
    0.5,
    0.02,
    "Failure labels are Gosai/Tewhey 2024 wet-lab MPRA measurements. CisFalcon maps them systematically "
    "and predicts where they cluster (pooled cross-lab AUROC 0.80).",
    color="#9aa3b2",
    fontsize=8.3,
    ha="center",
)
plt.subplots_adjust(left=0.16, right=0.98, top=0.90, bottom=0.20, wspace=0.55)
plt.savefig(HERE / "docs" / "failure_modes.png", dpi=150, facecolor=INK)
print("\nwrote docs/failure_modes.png")
