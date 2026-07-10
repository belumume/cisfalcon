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


def gap_of(pred2d, idxmap):
    out = []
    for i, t in enumerate(targets):
        sub = {c: float(pred2d[i, idxmap[c]]) for c in SHARED}
        out.append(sub[t] - max(v for c, v in sub.items() if c != t))
    return out


print("scoring with ACTIVITY (dhs64_mpra)...")
p_act = np.asarray(gate.score_sequences(seqs, kind="mpra"))
assert p_act.ndim == 2 and p_act.shape[1] == 12, f"activity shape {p_act.shape}"
act_auroc = auroc(labels, [-g for g in gap_of(p_act, MPRA_IDX)])

print("scoring with ACCESSIBILITY (dhs64)...")
p_acc = np.asarray(gate.score_sequences(seqs, kind="acc"))
# The accessibility model is MULTI-HEAD: score_sequences returns (n_heads, N, 64) =
# [logsignal, binary] over the 64 DHS biosamples. Report each head separately; logsignal is
# the continuous accessibility analogue of the activity log2FC. Averaging the heads (the earlier
# bug) collapses the wrong axis and mis-indexes the cells.
print("\n=== CROSS-LAB, matched subset ===")
print(f"ACTIVITY gate AUROC (dhs64-mpra):     {act_auroc:.4f}")
if p_acc.ndim == 3:
    names = {0: "logsignal", 1: "binary"}
    for h in range(p_acc.shape[0]):
        assert p_acc[h].shape[1] > max(DHS64_IDX.values())
        a_h = auroc(labels, [-g for g in gap_of(p_acc[h], DHS64_IDX)])
        print(
            f"ACCESSIBILITY head {h} ({names.get(h, '?')}) AUROC: {a_h:.4f}   activity adds {act_auroc - a_h:+.4f}"
        )
else:
    a = auroc(labels, [-g for g in gap_of(np.squeeze(p_acc), DHS64_IDX)])
    print(
        f"ACCESSIBILITY-only AUROC (dhs64):     {a:.4f}   activity adds {act_auroc - a:+.4f}"
    )
