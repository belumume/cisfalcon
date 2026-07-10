"""Cross-lab ACCESSIBILITY-ONLY baseline vs the ACTIVITY gate, matched, on the Gosai designs.
Answers the reviewer's strong-baseline question: does the activity model add over accessibility
on the cross-lab set (not just in-distribution, where activity 0.90 vs accessibility 0.79)?

Scores a stratified subset of the 93,435 Gosai designs with BOTH the atlas DHS64-MPRA activity
models (kind='mpra') and the DHS64 accessibility models (kind='acc'), computes the same
specificity gap over the 3 shared cells (K562/HepG2/SKNSH), and reports AUROC vs measured_fail
for each. No sklearn."""

import csv, random
import numpy as np
import gate

BENCH = "data/gosai_designed/designed_benchmark.csv"
SHARED = ["K562", "HepG2", "SKNSH"]
N_PER_CELL = 2000  # stratified subset; ~6000 total, ~370 failures -> stable AUROC


def auroc(labels, scores):
    pairs = sorted(zip(scores, labels))
    ranks = [0.0] * len(pairs)
    i = 0
    while i < len(pairs):
        j = i
        while j < len(pairs) and pairs[j][0] == pairs[i][0]:
            j += 1
        avg = (i + 1 + j) / 2.0
        for k in range(i, j):
            ranks[k] = avg
        i = j
    npos = sum(labels)
    nneg = len(labels) - npos
    if npos == 0 or nneg == 0:
        return None
    rsum = sum(ranks[k] for k in range(len(pairs)) if pairs[k][1] == 1)
    return (rsum - npos * (npos + 1) / 2) / (npos * nneg)


rng = random.Random(0)
by_cell = {c: [] for c in SHARED}
with open(BENCH, encoding="utf-8") as fh:
    r = csv.DictReader(fh)
    for row in r:
        c = row.get("target_cell")
        if c in by_cell:
            by_cell[c].append(row)
subset = []
for c in SHARED:
    rows = by_cell[c]
    rng.shuffle(rows)
    subset.extend(rows[:N_PER_CELL])
print(f"subset n = {len(subset)} (stratified {N_PER_CELL}/cell)")

seqs = [row["sequence"] for row in subset]
targets = [row["target_cell"] for row in subset]


# measured fail: target not most-active among the 3 measured shared cells
def measured_fail(row):
    vals = {c: float(row[c]) for c in SHARED}
    return 0 if max(vals, key=vals.get) == row["target_cell"] else 1


labels = [measured_fail(row) for row in subset]
print(
    f"measured failures: {sum(labels)} / {len(labels)} ({sum(labels) / len(labels):.3f})"
)

# CORRECT per-kind column indices. The activity (dhs64_mpra) head is 12 MPRA cells;
# the accessibility (dhs64) head is 64 DHS biosamples in a DIFFERENT order (atlas
# selected_biosample_metadata). Indexing the 64-wide accessibility output with the
# 12-cell MPRA CELL_IDX (the earlier bug) reads the wrong cells and gives a garbage
# accessibility number. The DHS64 indices below are verified from the atlas metadata.
MPRA_IDX = {"K562": 7, "HepG2": 6, "SKNSH": 3}  # == gate.CELL_IDX for these cells
DHS64_IDX = {"K562": 57, "HepG2": 49, "SKNSH": 30}


def gaps_for(kind):
    idxmap = MPRA_IDX if kind == "mpra" else DHS64_IDX
    pred = np.squeeze(np.asarray(gate.score_sequences(seqs, kind=kind)))
    if pred.ndim > 2:  # collapse any trailing (fold/head) axis to (N, C)
        pred = pred.reshape(pred.shape[0], pred.shape[1], -1).mean(axis=-1)
    need = max(idxmap.values())
    assert pred.shape[1] > need, (
        f"{kind} output width {pred.shape[1]} <= {need}; index map invalid"
    )
    out = []
    for i, t in enumerate(targets):
        sub = {c: float(pred[i, idxmap[c]]) for c in SHARED}
        out.append(sub[t] - max(v for c, v in sub.items() if c != t))
    return out


print("scoring with ACTIVITY (dhs64_mpra)...")
act_gaps = gaps_for("mpra")
print("scoring with ACCESSIBILITY (dhs64)...")
acc_gaps = gaps_for("acc")

act_auroc = auroc(labels, [-g for g in act_gaps])
acc_auroc = auroc(labels, [-g for g in acc_gaps])
print("\n=== CROSS-LAB, matched subset ===")
print(f"ACTIVITY gate AUROC (dhs64-mpra):     {act_auroc:.4f}")
print(f"ACCESSIBILITY-only AUROC (dhs64):     {acc_auroc:.4f}")
print(f"activity adds over accessibility:     {act_auroc - acc_auroc:+.4f}")
