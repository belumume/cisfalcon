"""Render the AUROC decomposition figure: 'here is exactly where the signal lives.'

Makes the honest grouped-prior decomposition a visible feature instead of a number
buried in scripts. Every value is the committed, Claude-Science-re-derived number
(see docs/SCIENCE-AUDIT.md). Pure matplotlib, no GPU, no model load.

    python make_decomposition_figure.py   ->   docs/decomposition.png
"""

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

# (label, AUROC, kind) — kind drives the colour: signal / prior / baseline
ROWS = [
    ("Pooled cross-lab (deployment number)", 0.8013, "signal"),
    ("Within-cell macro (cell prior removed)", 0.7473, "signal"),
    ("Per-generator macro", 0.7260, "signal"),
    ("Cell-prior only (base rate, no sequence)", 0.6784, "prior"),
    ("Joint cell x generator (fully conditioned)", 0.6624, "signal"),
    ("GC-content baseline", 0.5113, "baseline"),
    ("Random", 0.5000, "baseline"),
]

COLORS = {"signal": "#38e1c4", "prior": "#f4b740", "baseline": "#6b7280"}
INK = "#0a0d13"
TEXT = "#e8ecf4"

labels = [r[0] for r in ROWS][::-1]
vals = [r[1] for r in ROWS][::-1]
cols = [COLORS[r[2]] for r in ROWS][::-1]

fig, ax = plt.subplots(figsize=(9.2, 4.6))
fig.patch.set_facecolor(INK)
ax.set_facecolor(INK)
bars = ax.barh(labels, vals, color=cols, height=0.62, zorder=3)
ax.axvline(0.5, color="#6b7280", lw=1, ls="--", zorder=2)
for b, v in zip(bars, vals):
    ax.text(
        v + 0.006,
        b.get_y() + b.get_height() / 2,
        f"{v:.2f}",
        va="center",
        ha="left",
        color=TEXT,
        fontsize=11,
        fontweight="bold",
    )
ax.set_xlim(0.45, 0.86)
ax.set_xlabel(
    "cross-lab AUROC (higher = better separation of specificity failures)",
    color=TEXT,
    fontsize=10,
)
ax.set_title(
    "Where the signal lives: the pooled 0.80 decomposed, honestly",
    color=TEXT,
    fontsize=13,
    fontweight="bold",
    pad=12,
)
for s in ax.spines.values():
    s.set_visible(False)
ax.tick_params(colors=TEXT, labelsize=9.5)
ax.set_xticks([0.5, 0.6, 0.7, 0.8])
# legend note (centered under the chart, manual line breaks)
fig.text(
    0.5,
    0.045,
    "The pooled 0.80 is the deployment number for a mixed batch. Remove the cell base rate and\n"
    "per-sequence discrimination is 0.75; remove BOTH cell and generator base rates (fully\n"
    "conditioned) and it is 0.66, still well above every trivial baseline. Both are reported.",
    color="#9aa3b2",
    fontsize=8.8,
    ha="center",
    va="bottom",
)
plt.subplots_adjust(left=0.29, right=0.97, top=0.90, bottom=0.30)
plt.savefig("docs/decomposition.png", dpi=150, facecolor=INK)
print("wrote docs/decomposition.png")
