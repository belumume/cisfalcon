#!/usr/bin/env python
"""Deterministic splits for the cross-lab benchmark (`designed_benchmark.csv`).

Why this script exists: `build_benchmark.py` builds a DIFFERENT artifact. It reads the
atlas supplementary `media-10.xlsx`, filters to `{fsp, den, motif_embedding}`, and writes
`data/benchmark.csv` (an in-distribution atlas benchmark, ~9k rows, not committed here).
It never touches the 93,435-design cross-lab file, and its `HELDOUT_CELLS` names MCF7,
which is not one of this benchmark's three target cells. So it cannot produce these splits,
and BENCHMARK.md used to say it did.

This script regenerates both splits from the committed CSV alone. No GPU, no download.

    python make_splits.py                 # print the split summary
    python make_splits.py --write         # also write data/gosai_designed/designed_splits.csv

`split` (primary, stratified random 70/30, seed 0)
    Stratified by target_cell x method x measured_fail, so calibration and test carry
    matched failure distributions and discrimination is measured free of an easy/hard-cell
    confound. Deterministic: the same seed over the same committed rows, keyed by design
    `id`, gives byte-identical output on any machine.

`split_lco` (secondary, leave-cell-out)
    The benchmark has exactly three target cells, so leave-cell-out here is three folds
    rather than one fixed held-out set: calibrate on two cells, test on the third, three
    times. The fold label is therefore the design's own `target_cell`, and this column
    exists so the intent is explicit rather than implied. Failure rate is strongly
    cell-dependent (K562 0.59%, HepG2 8.20%, SKNSH 10.06%), so report the three folds
    separately and never pool them into a headline.
"""

import argparse
import hashlib
import pathlib

import numpy as np
import pandas as pd

HERE = pathlib.Path(__file__).resolve().parent
CSV = HERE / "data" / "gosai_designed" / "designed_benchmark.csv"
OUT = HERE / "data" / "gosai_designed" / "designed_splits.csv"

SEED = 0
TEST_FRAC = 0.30


def make_splits(df: pd.DataFrame) -> pd.DataFrame:
    """Return a frame of [id, split, split_lco], deterministic in the row ORDER of df."""
    # Sort by id first so the assignment does not depend on the CSV's row order.
    d = (
        df[["id", "target_cell", "method", "measured_fail"]]
        .sort_values("id")
        .reset_index(drop=True)
    )

    rng = np.random.default_rng(SEED)
    d["split"] = "calibration"
    strata = d["target_cell"] + "|" + d["method"] + "|" + d["measured_fail"].astype(str)
    for _, idx in d.groupby(strata, sort=True).groups.items():
        idx = np.asarray(idx)
        k = int(round(len(idx) * TEST_FRAC))
        if k:
            d.loc[idx[rng.permutation(len(idx))[:k]], "split"] = "test"

    # Leave-cell-out is three folds; the fold IS the target cell.
    d["split_lco"] = d["target_cell"]
    return d[["id", "split", "split_lco"]]


def summarize(df: pd.DataFrame, sp: pd.DataFrame) -> None:
    m = df.merge(sp, on="id", validate="one_to_one")
    rate = (
        lambda g: f"{g['measured_fail'].mean() * 100:5.2f}% ({int(g['measured_fail'].sum()):5d}/{len(g):5d})"
    )
    print(f"benchmark n={len(m):,}   overall fail = {rate(m)}")
    print("\n  primary stratified 70/30 split (`split`):")
    for name, g in m.groupby("split"):
        print(f"    {name:12s} n={len(g):6,d}  fail={rate(g)}")
    print(
        "\n  leave-cell-out folds (`split_lco`): hold out one, calibrate on the other two"
    )
    for name, g in m.groupby("split_lco"):
        print(f"    {name:12s} n={len(g):6,d}  fail={rate(g)}")
    print(
        "\n  stratified split, per method (matched failure distribution is the point):"
    )
    for name, g in m.groupby("method"):
        cal = g[g["split"] == "calibration"]["measured_fail"].mean() * 100
        tst = g[g["split"] == "test"]["measured_fail"].mean() * 100
        print(
            f"    {name:8s} n={len(g):6,d}  calibration {cal:5.2f}%   test {tst:5.2f}%"
        )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--write", action="store_true", help=f"write {OUT.name} beside the benchmark"
    )
    a = ap.parse_args()

    df = pd.read_csv(CSV, usecols=["id", "target_cell", "method", "measured_fail"])
    sp = make_splits(df)
    summarize(df, sp)

    body = sp.to_csv(index=False, lineterminator="\n").encode("utf-8")
    print(f"\n  split assignment sha256: {hashlib.sha256(body).hexdigest()}")
    print(
        "  (same on every platform; re-run to confirm before reporting a leaderboard number)"
    )

    if a.write:
        OUT.write_bytes(body)
        print(f"\n  wrote {OUT.relative_to(HERE)} ({len(sp):,} rows)")
    else:
        print(f"\n  (not written; pass --write to emit {OUT.name})")


if __name__ == "__main__":
    main()
