"""Cross-lab baseline decomposition: is the AUROC 0.80 per-SEQUENCE discrimination,
or just a shared cell-line PRIOR (which cell tends to win)?

Answers the strongest reviewer attack ("right answer, wrong reason") by computing:
  1. pooled cross-lab AUROC (CisFalcon, -pred_gap vs measured_fail)
  2. cell-prior-only baseline (target-cell base fail-rate, NO sequence) -> pure prior
  3. within-target-cell AUROC (cell prior removed) -> per-sequence signal
  4. joint within-(target-cell x generator) AUROC (BOTH base-rate axes removed)
     -> the fully-conditioned per-sequence signal reported in README/PREREG

Result (93,435 Gosai/Tewhey designs): pooled 0.8013, cell-prior 0.678,
within-cell macro 0.747 (HepG2 0.833, SKNSH 0.731, K562 0.678), joint
within-(cell x generator) macro 0.662 over the strata with >=10 fail and >=10 pass.
The within-cell macro exceeds the cell-prior baseline, so the gate adds real
per-sequence signal beyond the cell prior; removing the generator base-rate too
leaves 0.662, still well above 0.50 and every trivial baseline. The pooled 0.80 is
the deployment number for a mixed batch; 0.662 is the fully-conditioned per-sequence
discrimination. Reproducible; no sklearn.
"""

import csv, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
SCORED = os.path.join(HERE, "data", "gosai_designed", "designed_scored.csv")
MIN_PER_CLASS = 10  # a stratum needs >=10 fail and >=10 pass to yield a stable AUROC


def auroc(pairs):
    """pairs: (label, score); higher score = more likely positive (fail). Rank-sum, ties averaged."""
    pos = [s for l, s in pairs if l == 1]
    neg = [s for l, s in pairs if l == 0]
    if not pos or not neg:
        return None, len(pos), len(neg)
    allp = sorted([(s, 0) for s in neg] + [(s, 1) for s in pos])
    ranks = [0.0] * len(allp)
    i = 0
    while i < len(allp):
        j = i
        while j < len(allp) and allp[j][0] == allp[i][0]:
            j += 1
        avg = (i + 1 + j) / 2.0
        for k in range(i, j):
            ranks[k] = avg
        i = j
    rsum = sum(ranks[k] for k in range(len(allp)) if allp[k][1] == 1)
    npos, nneg = len(pos), len(neg)
    return (rsum - npos * (npos + 1) / 2) / (npos * nneg), npos, nneg


def main(path=SCORED):
    rows = []
    with open(path, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            try:
                rows.append(
                    (
                        r["target_cell"],
                        r["method"],
                        int(float(r["measured_fail"])),
                        float(r["pred_gap"]),
                    )
                )
            except Exception:
                pass
    print(f"n = {len(rows)}")

    pooled, npo, nne = auroc([(l, -g) for c, m, l, g in rows])
    print(
        f"POOLED cross-lab AUROC (-pred_gap):        {pooled:.4f}  (fail {npo}, pass {nne}, rate {npo / (npo + nne):.4f})"
    )

    cells = {}
    for c, m, l, g in rows:
        cells.setdefault(c, [0, 0])
        cells[c][1] += 1
        cells[c][0] += l
    rate = {c: v[0] / v[1] for c, v in cells.items()}
    prior, _, _ = auroc([(l, rate[c]) for c, m, l, g in rows])
    print(f"CELL-PRIOR baseline AUROC (no sequence):    {prior:.4f}")
    for c in sorted(cells):
        print(f"    {c}: base fail-rate {rate[c]:.3f} (n={cells[c][1]})")

    macro = []
    print("WITHIN-CELL AUROC (per-sequence, cell prior removed):")
    for c in sorted(cells):
        a, p, n = auroc([(l, -g) for cc, mm, l, g in rows if cc == c])
        if a is not None:
            macro.append(a)
            print(f"    {c}: {a:.4f} (fail {p}, pass {n})")
    print(f"    MACRO-AVG within-cell AUROC:            {sum(macro) / len(macro):.4f}")

    # BOTH base-rate axes removed at once: the fully-conditioned per-sequence signal.
    # This is the 0.66 cited in README (honest-numbers table) and PREREG section 6.
    strata = {}
    for c, m, l, g in rows:
        strata.setdefault((c, m), []).append((l, -g))
    joint = []
    print(
        f"JOINT within-(cell x generator) AUROC (both priors removed, >={MIN_PER_CLASS}/class):"
    )
    for key in sorted(strata):
        a, p, n = auroc(strata[key])
        if a is not None and p >= MIN_PER_CLASS and n >= MIN_PER_CLASS:
            joint.append(a)
            print(f"    {key[0]} x {key[1]}: {a:.4f} (fail {p}, pass {n})")
    print(
        f"    MACRO-AVG joint AUROC ({len(joint)} strata):        {sum(joint) / len(joint):.4f}"
        "   <- fully-conditioned per-sequence signal"
    )


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else SCORED)
