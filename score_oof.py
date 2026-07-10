"""B1/B2 out-of-fold scoring of the CisFalcon benchmark.

Runs the atlas DHS64-MPRA ACTIVITY models OUT-OF-FOLD (each design scored by the
model whose held-out test fold contains it -> non-circular, since the design was
NOT in that model's finetuning set). Compares three sequence-only pre-synthesis
signals against MEASURED wet-lab specificity failure:

  B1  activity model : predicted-activity specificity gap  (DHS64-MPRA, OOF)
  B0  accessibility  : shipped dhs_pred specificity gap    (DHS64, non-circular, all designs)
  B2  divergence/combo: accessibility + activity together  (the CisFalcon mechanism)

Encoding + output order copied verbatim from the atlas src (sequence.py / definitions.py).
"""

import json, pathlib, numpy as np, pandas as pd

D = pathlib.Path(__file__).parent / "data"
MODELS = pathlib.Path(__file__).parent / "models"
MPRA_CELL_LINES = [
    "NT2_D1",
    "GM12878",
    "786_O",
    "SKNSH",
    "WERI_Rb1",
    "SJCRH30",
    "HepG2",
    "K562",
    "MCF7",
    "HeLaS3",
    "HEK293",
    "HMC3",
]
TARGETS = MPRA_CELL_LINES[:10]  # target-eligible cells (single-in-panel)
INPUT_LEN = 500
OOF_FOLDS = [0, 1, 3]


def one_hot_encode(sequences, max_seq_len=INPUT_LEN, padding="left"):
    nuc = {
        "a": [1, 0, 0, 0],
        "c": [0, 1, 0, 0],
        "g": [0, 0, 1, 0],
        "t": [0, 0, 0, 1],
        "n": [0, 0, 0, 0],
    }
    out = np.zeros([len(sequences), max_seq_len, 4])
    for i, seq in enumerate(sequences):
        if len(seq) > max_seq_len:
            seq = seq[:max_seq_len] if padding == "left" else seq[-max_seq_len:]
        oh = np.array([nuc.get(x, [0, 0, 0, 0]) for x in seq.lower()])
        if padding == "left":
            out[i, : len(seq), :] = oh
        else:
            out[i, -len(seq) :, :] = oh
    return out


def spearman(x, y):
    xr = pd.Series(x).rank().values
    yr = pd.Series(y).rank().values
    return np.corrcoef(xr, yr)[0, 1]


def auroc(score, y):
    # higher score => predicted positive (fail)
    y = np.asarray(y)
    order = np.argsort(score, kind="mergesort")
    ranks = np.empty(len(score))
    ranks[order] = np.arange(1, len(score) + 1)
    n1 = y.sum()
    n0 = len(y) - n1
    if n1 == 0 or n0 == 0:
        return float("nan")
    return (ranks[y == 1].sum() - n1 * (n1 + 1) / 2) / (n1 * n0)


def auprc(score, y):
    y = np.asarray(y)
    order = np.argsort(-score, kind="mergesort")
    ys = y[order]
    tp = np.cumsum(ys)
    fp = np.cumsum(1 - ys)
    prec = tp / (tp + fp)
    rec = tp / max(y.sum(), 1)
    # average precision (area under PR via step)
    ap = 0.0
    prev_r = 0.0
    for p, r in zip(prec, rec):
        ap += p * (r - prev_r)
        prev_r = r
    return ap


def main():
    import tensorflow as tf

    bm = pd.read_csv(D / "benchmark.csv")
    seqs = pd.read_csv(D / "benchmark_sequences.csv").set_index("id")["sequence"]
    bm["sequence"] = bm["id"].map(seqs)
    tsv = pd.read_csv(
        D / "enhancer_mpra_processed.tsv", sep="\t", low_memory=False
    ).set_index("id")
    splits = json.load(open(D / "mpra_data_splits.json"))

    # out-of-fold model assignment
    oof = {}
    for k in OOF_FOLDS:
        for i in splits[k]["test"]:
            if i not in oof:
                oof[i] = k
    bm["oof"] = bm["id"].map(oof)
    m = bm[bm["oof"].notna()].copy()
    m["oof"] = m["oof"].astype(int)
    print(f"benchmark n={len(bm)}  |  OOF-covered (folds {OOF_FOLDS} test) n={len(m)}")

    lfc = [f"log2FC_{c}" for c in TARGETS]
    acc = [f"dhs_pred_{c}" for c in TARGETS]
    meta = tsv[lfc + acc]
    m = m.join(meta, on="id").dropna(subset=lfc + acc).reset_index(drop=True)
    print(f"after joining measured log2FC + accessibility preds: n={len(m)}")

    ti = np.array([TARGETS.index(c) for c in m["target_cell"]])
    r = np.arange(len(m))
    offmask = np.eye(len(TARGETS))[ti].astype(bool)
    L = m[lfc].values.astype(float)
    A = m[acc].values.astype(float)
    meas_gap = L[r, ti] - np.where(offmask, -np.inf, L).max(1)
    acc_gap = A[r, ti] - np.where(offmask, -np.inf, A).max(1)
    fail = (meas_gap <= 0).astype(int)

    # ---- run activity models OUT-OF-FOLD ----
    X = one_hot_encode(m["sequence"].tolist())
    pred = np.full((len(m), 12), np.nan)
    for k in OOF_FOLDS:
        idx = np.where(m["oof"].values == k)[0]
        if len(idx) == 0:
            continue
        model = tf.keras.models.load_model(
            MODELS / f"dhs64_mpra_split{k}.h5", compile=False
        )
        pred[idx] = model.predict(X[idx], batch_size=128, verbose=0)
        print(f"  scored fold {k}: {len(idx)} designs")
    P = pred[:, :10]  # target-eligible cells
    act_gap = P[r, ti] - np.where(offmask, -np.inf, P).max(1)

    def report(name, fail_score):
        print(
            f"  {name:28s} AUROC={auroc(fail_score, fail):.3f}  AUPRC={auprc(fail_score, fail):.3f}"
        )

    print(f"\nmeasured fail rate on OOF subset: {fail.mean() * 100:.1f}%  (n={len(m)})")
    print("fail-discrimination (higher fail-score = predicted-fail):")
    report("B0 accessibility gap", -acc_gap)
    report("B1 activity gap (OOF)", -act_gap)
    # B2 combiner: fit 2-feature logistic on calibration split, eval on held-out test split
    m["_acc"] = acc_gap
    m["_act"] = act_gap
    m["_fail"] = fail
    tr = m["split"] == "calibration"
    te = m["split"] == "test"
    try:
        from sklearn.linear_model import LogisticRegression

        Xtr = m.loc[tr, ["_acc", "_act"]].values
        Xte = m.loc[te, ["_acc", "_act"]].values
        clf = LogisticRegression(max_iter=1000).fit(Xtr, m.loc[tr, "_fail"].values)
        s_te = clf.predict_proba(Xte)[:, 1]
        yte = m.loc[te, "_fail"].values
        print(
            f"\nheld-out TEST split (n={te.sum()}), combiner calibrated on calibration split:"
        )
        print(
            f"  B0 accessibility  AUROC={auroc(-m.loc[te, '_acc'].values, yte):.3f}  AUPRC={auprc(-m.loc[te, '_acc'].values, yte):.3f}"
        )
        print(
            f"  B1 activity(OOF)  AUROC={auroc(-m.loc[te, '_act'].values, yte):.3f}  AUPRC={auprc(-m.loc[te, '_act'].values, yte):.3f}"
        )
        print(
            f"  B2 combined       AUROC={auroc(s_te, yte):.3f}  AUPRC={auprc(s_te, yte):.3f}"
        )
    except Exception as e:
        print("sklearn combiner skipped:", e)

    print(
        f"\ncorrelations (OOF subset): Spearman(acc_gap,meas)={spearman(acc_gap, meas_gap):.3f}  "
        f"Spearman(act_gap,meas)={spearman(act_gap, meas_gap):.3f}  "
        f"Spearman(acc_gap,act_gap)={spearman(acc_gap, act_gap):.3f}"
    )
    # flag lowest-quartile precision for the best single signal
    for name, g in [("accessibility", acc_gap), ("activity", act_gap)]:
        q = np.quantile(g, 0.25)
        fl = g <= q
        print(
            f"  flag lowest-25% {name} gap -> {fail[fl].mean() * 100:.1f}% really failed (base {fail.mean() * 100:.1f}%)"
        )


if __name__ == "__main__":
    main()
