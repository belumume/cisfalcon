"""Correlate CisFalcon predicted variant effects vs measured satMut effects.
Input : variant_scored.csv.gz  Output: correlation_summary.csv, correlation_per_element.csv
"""

import numpy as np, pandas as pd
from scipy import stats
from sklearn.metrics import roc_auc_score

from pathlib import Path

# Resolve against the repo root, not the caller's cwd. The file lives at data/, and this
# read used to be a bare relative "variant_scored.csv.gz", so step 3 of the documented
# pipeline failed from a clean clone at every working directory.
_REPO = Path(__file__).resolve().parent.parent
_IN = _REPO / "data" / "variant_scored.csv.gz"
if not _IN.exists():
    raise SystemExit(
        f"missing input: {_IN}\n"
        "Run satmut/score_variants_gpu.py first, or check out the committed copy."
    )
sc = pd.read_csv(_IN)

# Outputs beside the script, not in the caller's cwd, for the same reason.
_OUT = Path(__file__).resolve().parent


def boot_ci(x, y, fn, n=2000, seed=0):
    rng = np.random.default_rng(seed)
    N = len(x)
    v = []
    for _ in range(n):
        i = rng.integers(0, N, N)
        try:
            v.append(fn(x[i], y[i]))
        except Exception:
            pass
    return np.percentile(v, [2.5, 97.5])


def analyze(d, label):
    x, y = d.pred_effect.values, d.measured_effect.values
    pr, pp = stats.pearsonr(x, y)
    sr, sp = stats.spearmanr(x, y)
    big = (np.abs(y) >= 1).astype(int)
    au = roc_auc_score(big, np.abs(x)) if 10 <= big.sum() <= len(big) - 10 else np.nan
    au_ci = boot_ci(
        np.abs(x),
        big,
        lambda a, b: roc_auc_score(b, a) if 0 < b.sum() < len(b) else np.nan,
    )
    return dict(
        label=label,
        n=len(d),
        pearson=pr,
        pearson_p=pp,
        pearson_ci=tuple(
            np.round(boot_ci(x, y, lambda a, b: stats.pearsonr(a, b)[0]), 3)
        ),
        spearman=sr,
        spearman_p=sp,
        spearman_ci=tuple(
            np.round(boot_ci(x, y, lambda a, b: stats.spearmanr(a, b)[0]), 3)
        ),
        n_large=int(big.sum()),
        auroc_large=au,
        auroc_large_ci=tuple(np.round(au_ci, 3)),
    )


pd.DataFrame(
    [
        analyze(sc[sc.cell == "HepG2"], "HepG2"),
        analyze(sc[sc.cell == "K562"], "K562"),
        analyze(sc, "Pooled"),
    ]
).to_csv(_OUT / "correlation_summary.csv", index=False)

pe = []
for e in sc.element.unique():
    d = sc[sc.element == e]
    pr, pp = stats.pearsonr(d.pred_effect, d.measured_effect)
    sr, sp = stats.spearmanr(d.pred_effect, d.measured_effect)
    pe.append(
        dict(
            element=e,
            cell=d.cell.iloc[0],
            n=len(d),
            pearson=round(pr, 3),
            pearson_p=f"{pp:.1e}",
            spearman=round(sr, 3),
            spearman_p=f"{sp:.1e}",
        )
    )
pd.DataFrame(pe).to_csv(_OUT / "correlation_per_element.csv", index=False)
print("wrote correlation tables")
