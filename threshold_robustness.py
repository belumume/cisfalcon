"""Failure-threshold robustness of the cross-lab AUROC: is the 0.80 an artifact of the
pre-committed gap<=0 binarization, or stable across reasonable failure definitions?

Result (93,435 Gosai designs): AUROC stays in a 0.73-0.85 band across thresholds
(0.85 at gap<=-0.5, the decisive failures; 0.801 at the committed gap<=0; 0.73 at
gap<=1.0, including marginal near-boundary calls), far above the 0.50 trivial baselines
at every threshold. The 0.80 is an honest middle, not a cherry-picked cutoff. No sklearn."""

import csv, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
SCORED = os.path.join(HERE, "data", "gosai_designed", "designed_scored.csv")


def auroc(labels, scores):
    pairs = sorted(zip(scores, labels))
    ranks = [0.0] * len(pairs)
    i = 0
    while i < len(pairs):
        j = i
        while j < len(pairs) and pairs[j][0] == pairs[i][0]:
            j += 1
        a = (i + 1 + j) / 2.0
        for k in range(i, j):
            ranks[k] = a
        i = j
    npos = sum(labels)
    nneg = len(labels) - npos
    if not npos or not nneg:
        return None
    rsum = sum(ranks[k] for k in range(len(pairs)) if pairs[k][1] == 1)
    return (rsum - npos * (npos + 1) / 2) / (npos * nneg)


def main(path=SCORED):
    rows = []
    with open(path, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            try:
                rows.append(
                    (
                        float(r["measured_gap"]),
                        float(r["pred_gap"]),
                        int(float(r["measured_fail"])),
                    )
                )
            except Exception:
                pass
    print(f"n = {len(rows)}")
    print(
        "FAILURE-THRESHOLD ROBUSTNESS (fail := measured_gap <= t); score = -pred_gap:"
    )
    for t in [-0.5, 0.0, 0.5, 1.0]:
        # BENCHMARK.md: measured_gap ships rounded to 3 decimals, so re-deriving the label
        # from it puts five genuinely-positive-gap rows on the wrong side of zero and gives
        # 5,879 where the committed label sums to 5,874. At the committed threshold, use the
        # committed label - this row is the anchor every other script is reconciled against.
        if t == 0.0:
            labels = [mf for _, _, mf in rows]
            star = "  <- committed threshold (committed measured_fail label)"
        else:
            labels = [1 if mg <= t else 0 for mg, _, _ in rows]
            star = ""
        a = auroc(labels, [-pg for _, pg, _ in rows])
        rate = sum(labels) / len(labels)
        print(
            f"  t={t:+.1f}: AUROC {a:.4f}  (fail rate {rate:.3f}, n_fail {sum(labels)}){star}"
        )


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else SCORED)
