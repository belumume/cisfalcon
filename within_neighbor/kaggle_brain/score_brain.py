"""CROWN-JEWEL within-neighbor validation (Kaggle kernel, off-machine).

Tests the CisFalcon PARADIGM at IN-VIVO within-cortex neighbor resolution:
does a sequence-derived specificity gap, computed by an INDEPENDENT mouse-cortex
per-subclass model (DeepBICCN2, CREsted), separate enhancers that were IN-VIVO
On-Target from those that misfired (Off/Mixed) in a real enhancer-AAV screen?

Data (in-vivo ground truth): Allen/BICCN EnhancerBenchmark (Ben-Simon et al.,
Cell 2025) — 532 mouse-cortex enhancers, AAV-screened, LABEL_Specificity in
{On_Target, Off_Target, Mixed_Target, No_Labeling}, each with a target cortical
subclass (max_subclass_primary) and the enhancer_sequence.

Scorer (independent): DeepBICCN2 — mouse-cortex snATAC accessibility CNN,
per-subclass output. Predicts accessibility from SEQUENCE; the label is an
in-vivo FUNCTIONAL phenotype, so this is a genuine sequence->function test, not
a recapitulation of the selection criterion.

gap = pred[target_subclass] - max(pred[off_subclasses]); high gap = predicted
specific. AUROC of gap vs the in-vivo On-vs-Off label, + paired bootstrap 95% CI.
PRE-REGISTERED: CI excludes 0.50 => the paradigm predicts in-vivo within-cortex
specificity; near 0.50 => honest null. No tuning.

Runs on Kaggle (internet on): pip installs crested, git-clones the benchmark,
fetches DeepBICCN2 via CREsted's pooch registry.
"""

import json
import os
import subprocess
import sys

subprocess.run([sys.executable, "-m", "pip", "install", "-q", "crested"], check=False)

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

OUT = "/kaggle/working/brain_within_neighbor_result.json"
report = {"stage": "start"}


def log(**k):
    report.update(k)
    print(
        json.dumps(
            {
                kk: (vv if isinstance(vv, (int, float, str, bool, list)) else str(vv))
                for kk, vv in k.items()
            }
        )[:1500]
    )
    with open(OUT, "w") as f:
        json.dump(report, f, indent=2, default=str)


# ---- data ----
csv = None
for c in [
    "/kaggle/input/enhancer-genomic-data/enhancer_genomic_data.csv",
    "/kaggle/working/eb/code/random_forest_model/enhancer_genomic_data.csv",
]:
    if os.path.exists(c):
        csv = c
        break
if csv is None:
    subprocess.run(
        [
            "git",
            "clone",
            "--depth",
            "1",
            "https://github.com/AllenInstitute/EnhancerBenchmark",
            "/kaggle/working/eb",
        ],
        check=False,
    )
    csv = "/kaggle/working/eb/code/random_forest_model/enhancer_genomic_data.csv"
df = pd.read_csv(csv)
log(
    stage="data",
    n=len(df),
    spec_counts=df["LABEL_Specificity"].value_counts().to_dict(),
)

# ---- model ----
import crested  # noqa: E402
import keras  # noqa: E402

model_file, classes = crested.get_model("DeepBICCN2")
model = keras.models.load_model(model_file, compile=False)
in_shape = model.input_shape
seq_len = int(in_shape[1]) if isinstance(in_shape, tuple) else int(in_shape[0][1])
log(
    stage="model_loaded",
    input_shape=str(in_shape),
    seq_len=seq_len,
    n_classes=len(classes),
    classes=classes,
)

# ---- one-hot to the model's input length (center crop/pad) ----
_B = {"A": 0, "C": 1, "G": 2, "T": 3}


def one_hot(seq, L):
    s = str(seq).strip().upper()
    if len(s) > L:
        st = (len(s) - L) // 2
        s = s[st : st + L]
    oh = np.zeros((L, 4), dtype=np.float32)
    pad = (L - len(s)) // 2
    for i, b in enumerate(s):
        j = _B.get(b)
        if j is not None:
            oh[pad + i, j] = 1.0
    return oh


# ---- subclass name matching: label max_subclass_primary -> model class ----
def norm(x):
    return "".join(ch for ch in str(x).lower() if ch.isalnum())


class_norm = {norm(c): i for i, c in enumerate(classes)}


def match_class(subclass):
    n = norm(subclass)
    if n in class_norm:
        return class_norm[n]
    # relaxed: model class contained in / contains the label token
    for cn, i in class_norm.items():
        if n and (n in cn or cn in n):
            return i
    return None


# ---- score all sequences ----
seqs = df["enhancer_sequence"].astype(str).tolist()
X = np.stack([one_hot(s, seq_len) for s in seqs])
preds = model.predict(X, batch_size=128, verbose=0)
preds = np.asarray(preds)
if preds.ndim == 3:  # (n, L, classes)-style -> reduce over length
    preds = preds.mean(axis=1)
log(stage="scored", preds_shape=str(preds.shape))

# ---- specificity gap per enhancer ----
gaps = np.full(len(df), np.nan)
mapped = 0
for i, sub in enumerate(df["max_subclass_primary"].tolist()):
    ti = match_class(sub)
    if ti is None or ti >= preds.shape[1]:
        continue
    p = preds[i]
    off = np.delete(p, ti)
    gaps[i] = float(p[ti] - off.max())
    mapped += 1
df["gap"] = gaps
log(stage="gaps", mapped=mapped, unmapped=int(np.isnan(gaps).sum()))


def boot_auroc(labels, vals, n=1000, seed=0):
    labels = np.asarray(labels).astype(int)
    vals = np.asarray(vals, float)
    m = ~np.isnan(vals)
    labels, vals = labels[m], vals[m]
    point = float(roc_auc_score(labels, vals))
    rng = np.random.default_rng(seed)
    bs = []
    for _ in range(n):
        idx = rng.integers(0, len(vals), len(vals))
        if labels[idx].min() != labels[idx].max():
            bs.append(roc_auc_score(labels[idx], vals[idx]))
    lo, hi = np.percentile(bs, [2.5, 97.5])
    return dict(
        auroc=round(point, 4),
        ci95=[round(float(lo), 4), round(float(hi), 4)],
        ci_excl_chance=bool(lo > 0.5),
        n_pos=int((labels == 1).sum()),
        n_neg=int((labels == 0).sum()),
    )


# ---- pre-registered tests ----
results = {}
# (A) clean binary: On_Target(1) vs Off_Target(0)
a = df[df["LABEL_Specificity"].isin(["On_Target", "Off_Target"])].copy()
a["y"] = (a["LABEL_Specificity"] == "On_Target").astype(int)
results["on_vs_off"] = boot_auroc(a["y"].values, a["gap"].values)
# (B) On_Target(1) vs Off+Mixed(0) -- more power
b = df[df["LABEL_Specificity"].isin(["On_Target", "Off_Target", "Mixed_Target"])].copy()
b["y"] = (b["LABEL_Specificity"] == "On_Target").astype(int)
results["on_vs_offmixed"] = boot_auroc(b["y"].values, b["gap"].values)
# (C) ON_target binary column
results["ON_target_col"] = boot_auroc(df["ON_target"].values, df["gap"].values)

# ---- incremental-value: does the SEQUENCE gap add over MEASURED accessibility? ----
# baselines on the same On-vs-Off subset + a logistic combining gap + max_acc.
from sklearn.linear_model import LogisticRegression  # noqa: E402
from sklearn.model_selection import cross_val_predict  # noqa: E402

inc = {}
for col in ["max_scaled_acc_mouse", "gini_index", "GC.content"]:
    if col in a.columns:
        inc[col] = boot_auroc(a["y"].values, a[col].values)
# combined gap + max_acc (5-fold CV to avoid overfit), AUROC of the CV prob
av = a.dropna(subset=["gap", "max_scaled_acc_mouse"]).copy()
if len(av) > 30 and av["y"].nunique() == 2:
    Xc = av[["gap", "max_scaled_acc_mouse"]].values
    Xg = av[["gap"]].values
    Xa = av[["max_scaled_acc_mouse"]].values
    yv = av["y"].values
    for nm, X in [("gap_only_cv", Xg), ("acc_only_cv", Xa), ("gap+acc_cv", Xc)]:
        pr = cross_val_predict(
            LogisticRegression(max_iter=1000), X, yv, cv=5, method="predict_proba"
        )[:, 1]
        inc[nm] = boot_auroc(yv, pr)
results["incremental_value"] = inc

# per-enhancer dump for local re-analysis
dump_cols = [
    "Enhancer_ID",
    "LABEL_Specificity",
    "ON_target",
    "max_subclass_primary",
    "gap",
    "max_scaled_acc_mouse",
    "gini_index",
    "GC.content",
    "accessibility_mouse",
]
df[[c for c in dump_cols if c in df.columns]].to_csv(
    "/kaggle/working/brain_gaps_with_baselines.csv", index=False
)

log(stage="DONE", results=results)
print("\n==== FINAL ====")
print(
    json.dumps(
        {"model": "DeepBICCN2", "n_classes": len(classes), "results": results}, indent=2
    )
)
