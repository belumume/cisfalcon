"""CisFalcon benchmark builder.

Turns the atlas measured MPRA results (Supp Table 9 = media-10.xlsx) into a
reproducible held-out failure benchmark for the pre-synthesis specificity gate.

Failure label (transparent, independent of the atlas's opaque specificity_score):
a design FAILS specificity if it is NOT the most-active in its own measured target
cell type, i.e. gap = target_log2FC - max(off-target log2FC) <= 0.

Splits (both saved):
- `split` = stratified random 70/30 (stratified by target_cell x source x fail,
  fixed seed) -> calibration/test have MATCHED failure distributions. Primary split
  for measuring the gate's discrimination (AUPRC etc.), free of easy/hard-cell confound.
- `split_lco` = leave-CELL-TYPES-out (a fixed held-out set of target cell types).
  Secondary generalization stress-test: does the gate transfer to cells it never
  calibrated on? Note failure rate is strongly cell-type-dependent, so this split is
  reported separately, not used as the headline metric.
"""

import argparse, pathlib
import numpy as np, pandas as pd

LOG2FC_PREFIX = "log2FC_"
AI_SOURCES = {"fsp", "den", "motif_embedding"}
HELDOUT_CELLS = {"HepG2", "K562", "MCF7"}  # secondary leave-cell-out test set
SEED = 0
TEST_FRAC = 0.30


def _norm(s):
    return str(s).upper().replace("_", "").replace("-", "")


def build(xlsx):
    df = pd.read_excel(xlsx)
    log2fc = [c for c in df.columns if c.startswith(LOG2FC_PREFIX)]
    panel_norm = {_norm(c[len(LOG2FC_PREFIX) :]): c for c in log2fc}

    d = df[~df["category"].astype(str).str.contains("control")].copy()
    d = d[d["target"].notna()]

    def target_col(t):
        s = str(t)
        if s.startswith("(") or "," in s:
            return None
        return panel_norm.get(_norm(s))

    d["target_col"] = d["target"].map(target_col)
    d = d[d["target_col"].notna()]
    d = d[d["source"].isin(AI_SOURCES)]
    d = d.dropna(subset=log2fc).copy()

    def gap(r):
        tc = r["target_col"]
        return r[tc] - max(r[c] for c in log2fc if c != tc)

    d["gap"] = d.apply(gap, axis=1)
    d["fail"] = (d["gap"] <= 0).astype(int)
    d["target_cell"] = d["target_col"].str[len(LOG2FC_PREFIX) :]

    # primary: stratified random split (matched fail distribution)
    rng = np.random.default_rng(SEED)
    d["_strata"] = d["target_cell"] + "|" + d["source"] + "|" + d["fail"].astype(str)
    d["split"] = "calibration"
    for _, idx in d.groupby("_strata").groups.items():
        idx = list(idx)
        k = int(round(len(idx) * TEST_FRAC))
        for i in rng.permutation(len(idx))[:k]:
            d.loc[idx[i], "split"] = "test"

    # secondary: leave-cell-types-out
    d["split_lco"] = np.where(
        d["target_cell"].isin(HELDOUT_CELLS), "test", "calibration"
    )

    return d[
        ["id", "target_cell", "source", "gap", "fail", "split", "split_lco", "sequence"]
    ].reset_index(drop=True)


def summarize(bm):
    r = lambda x: f"{x.mean() * 100:5.1f}% ({int(x.sum())}/{len(x)})"
    print(f"benchmark n={len(bm)}  |  FAIL(gap<=0) overall = {r(bm['fail'])}")
    print("  primary stratified split:")
    for sp, g in bm.groupby("split"):
        print(f"    {sp:11s} n={len(g):4d}  fail={r(g['fail'])}")
    print("  leave-cell-out split (generalization stress-test):")
    for sp, g in bm.groupby("split_lco"):
        print(
            f"    {sp:11s} n={len(g):4d}  fail={r(g['fail'])}  cells={sorted(g['target_cell'].unique())}"
        )
    print("  by method:")
    for s, g in bm.groupby("source"):
        print(f"    {s:16s} n={len(g):4d}  fail={r(g['fail'])}")
    print("  by target cell (failure is cell-type-dependent -> calibrate per-cell):")
    for c, g in bm.groupby("target_cell"):
        if len(g) >= 50:
            print(f"    {c:10s} n={len(g):4d}  fail={r(g['fail'])}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--xlsx", default="media-10.xlsx")
    ap.add_argument(
        "--out", default=str(pathlib.Path(__file__).parent / "data" / "benchmark.csv")
    )
    a = ap.parse_args()
    bm = build(a.xlsx)
    pathlib.Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    bm.drop(columns=["sequence"]).to_csv(a.out, index=False)
    bm[["id", "sequence"]].to_csv(a.out.replace(".csv", "_sequences.csv"), index=False)
    print(f"wrote {a.out} ({len(bm)} rows) + sequences\n")
    summarize(bm)
