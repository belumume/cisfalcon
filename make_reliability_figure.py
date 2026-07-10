"""Reliability diagram for the calibrated failure probability (held-out).

Visual proof that the isotonic calibration is real: fit on a random half of the 93,435
cross-lab designs, then on the OTHER half bin the predicted P(fail) and plot it against
the observed failure rate. A calibrated model sits on the diagonal. Annotates held-out ECE.
CPU, seconds, no GPU. Writes docs/cisfalcon_calibration.png.
"""

import numpy as np
import pandas as pd
from pathlib import Path
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from sklearn.isotonic import IsotonicRegression

DATA = Path(__file__).parent / "data"
OUT = Path(__file__).parent / "docs" / "cisfalcon_calibration.png"
OUT.parent.mkdir(exist_ok=True)

df = (
    pd.read_csv(DATA / "gosai_designed" / "designed_scored.csv")
    .rename(columns={"measured_fail": "fail"})[["pred_gap", "fail"]]
    .dropna()
)
df["fail"] = df["fail"].astype(int)

rng = np.random.default_rng(0)
perm = rng.permutation(len(df))
half = len(df) // 2
A, B = df.iloc[perm[:half]], df.iloc[perm[half:]]

iso = IsotonicRegression(increasing=False, out_of_bounds="clip").fit(
    A["pred_gap"].values, A["fail"].values
)
p = iso.predict(B["pred_gap"].values)
y = B["fail"].values.astype(float)

n_bins = 10
edges = np.linspace(0, 1, n_bins + 1)
idx = np.clip(np.digitize(p, edges[1:-1]), 0, n_bins - 1)
conf, obs, cnt = [], [], []
ece = 0.0
for b in range(n_bins):
    m = idx == b
    if not m.any():
        continue
    conf.append(p[m].mean())
    obs.append(y[m].mean())
    cnt.append(int(m.sum()))
    ece += m.mean() * abs(p[m].mean() - y[m].mean())
conf, obs, cnt = np.array(conf), np.array(obs), np.array(cnt)

fig, ax = plt.subplots(figsize=(5.2, 5.2), dpi=150)
ax.plot([0, 1], [0, 1], "--", color="#888", lw=1, label="perfect calibration")
sizes = 30 + 300 * (cnt / cnt.max())
ax.scatter(
    conf,
    obs,
    s=sizes,
    c="#1a7f5a",
    alpha=0.85,
    edgecolor="white",
    linewidth=0.8,
    zorder=3,
    label="held-out bins (size = n)",
)
ax.plot(conf, obs, "-", color="#1a7f5a", lw=1.2, alpha=0.6, zorder=2)
ax.set_xlabel("predicted failure probability")
ax.set_ylabel("observed failure rate")
ax.set_xlim(-0.02, 1.02)
ax.set_ylim(-0.02, 1.02)
ax.set_title(
    f"CisFalcon failure-risk calibration\nheld-out ECE = {ece:.4f}  (n = {len(B):,} cross-lab designs)",
    fontsize=10,
)
ax.legend(loc="upper left", fontsize=8, frameon=False)
ax.grid(True, alpha=0.2)
fig.tight_layout()
fig.savefig(OUT, bbox_inches="tight")
print(f"wrote {OUT}  |  held-out ECE={ece:.4f}  |  bins={len(conf)}")
