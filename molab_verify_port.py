import os, time, threading, urllib.request, json, numpy as np, pandas as pd, tensorflow as tf

M = "/tmp/m"
RES = f"{M}/verify.txt"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
CELLS = [
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
TARGETS = CELLS[:10]
_LUT = np.full(256, -1, dtype=np.int64)
for _ch, _i in zip("acgt", range(4)):
    _LUT[ord(_ch)] = _i
    _LUT[ord(_ch.upper())] = _i


def log(s):
    with open(RES, "a") as f:
        f.write(s + "\n")


def onehot(seqs, L=500):
    out = np.zeros((len(seqs), L, 4), dtype=np.float32)
    for i, s in enumerate(seqs):
        b = np.frombuffer(str(s)[:L].encode("ascii", "ignore"), dtype=np.uint8)
        idx = _LUT[b]
        v = idx >= 0
        out[i, np.arange(len(b))[v], idx[v]] = 1.0
    return out


def spearman(x, y):
    return float(
        np.corrcoef(pd.Series(x).rank().values, pd.Series(y).rank().values)[0, 1]
    )


def auroc(sc, yy):
    yy = np.asarray(yy)
    o = np.argsort(sc, kind="mergesort")
    r = np.empty(len(sc))
    r[o] = np.arange(1, len(sc) + 1)
    n1 = yy.sum()
    n0 = len(yy) - n1
    return (
        float((r[yy == 1].sum() - n1 * (n1 + 1) / 2) / (n1 * n0))
        if n1 and n0
        else float("nan")
    )


def run():
    try:
        # split map for out-of-fold
        sp_path = f"{M}/mpra_data_splits.json"
        if not (os.path.exists(sp_path) and os.path.getsize(sp_path) > 100):
            req = urllib.request.Request(
                "https://zenodo.org/records/17410822/files/mpra_data_splits.json?download=1",
                headers={
                    "User-Agent": UA,
                    "Referer": "https://zenodo.org/records/17410822",
                },
            )
            with (
                urllib.request.urlopen(req, timeout=300) as r,
                open(sp_path, "wb") as f,
            ):
                f.write(r.read())
        splits = json.load(open(sp_path))
        oof = {}
        for k in [0, 1, 3]:
            for i in splits[k]["test"]:
                oof.setdefault(i, k)

        df = pd.read_csv(f"{M}/atlas.tsv", sep="\t", low_memory=False)
        lfc = [f"log2FC_{c}" for c in TARGETS]

        # rebuild the AI-design single-in-panel benchmark from atlas.tsv (same logic as build_benchmark.py)
        def norm(s):
            return str(s).upper().replace("_", "").replace("-", "")

        panel = {norm(c): f"log2FC_{c}" for c in TARGETS}
        d = df[~df["category"].astype(str).str.contains("control", na=False)].copy()
        d = d[d["target"].notna()]
        d["tcol"] = d["target"].map(
            lambda t: None
            if (str(t).startswith("(") or "," in str(t))
            else panel.get(norm(t))
        )
        d = d[d["tcol"].notna()]
        d = d[d["source"].isin(["fsp", "den", "motif_embedding"])].dropna(subset=lfc)
        d["oof"] = d["id"].map(oof)
        d = d[d["oof"].notna()].copy()
        d["oof"] = d["oof"].astype(int)
        d["target_cell"] = d["tcol"].str[len("log2FC_") :]
        log(f"benchmark designs (AI, single-target, OOF-covered): {len(d)}")

        models = {
            k: tf.keras.models.load_model(f"{M}/mpra{k}.h5", compile=False)
            for k in [0, 1, 3]
        }
        L = d[lfc].values.astype(float)
        ti = np.array([TARGETS.index(c) for c in d["target_cell"]])
        r = np.arange(len(d))
        offmask = np.eye(len(TARGETS))[ti].astype(bool)
        meas_gap = L[r, ti] - np.where(offmask, -np.inf, L).max(1)
        fail = (meas_gap <= 0).astype(int)

        seqs = d["sequence"].tolist()
        pred = np.empty((len(d), 12), dtype=np.float32)
        for k in [0, 1, 3]:
            idx = np.where(d["oof"].values == k)[0]
            X = onehot([seqs[j] for j in idx])
            pred[idx] = models[k].predict(X, batch_size=2048, verbose=0)
            log(f"  scored OOF fold {k}: {len(idx)}")
        P = pred[:, :10]
        act_gap = P[r, ti] - np.where(offmask, -np.inf, P).max(1)
        log(
            f"[PORT-CHECK] n={len(d)} fail={fail.mean() * 100:.1f}% | "
            f"Spearman(pred,meas gap)={spearman(act_gap, meas_gap):.3f} | "
            f"AUROC(specificity)={auroc(-act_gap, fail):.3f}  (expect ~0.85 rho, ~0.91 AUROC if port is correct)"
        )
        log("DONE")
    except Exception as e:
        log("ERROR: " + repr(e)[:300])


open(RES, "w").close()
threading.Thread(target=run, daemon=True).start()
print("STARTED port-verification thread; poll /tmp/m/verify.txt")
