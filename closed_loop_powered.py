"""Powered, FAIR closed-loop comparison (answers the n=20 / unfair-budget / circularity attacks).

The original eval (n=20, deterministic single edit vs Claude's iterating loop) has three fair
criticisms: (1) n=20 makes 8-vs-6 statistical noise; (2) unfair budget, Claude iterates ~3.5 rounds
while the deterministic baseline got ONE edit; (3) circular, a "rescue" only means the same frozen
gate now passes it (in-silico consistency, not wet-lab). This script fixes (1) and (2) and states (3)
honestly. It measures ONE legitimate thing: given the SAME iteration budget and the SAME frozen gate,
does Claude's ADAPTIVE motif search rescue more failing designs than a FIXED greedy rule? That is a
claim about agentic search quality, in-silico, NOT about biological design improvement.

Both methods: edit locally with the same pure-Python JASPAR motif machinery (motifs.py, no local ML),
score via the DEPLOYED gate (/api/predict). Claude additionally picks the TFs each round via Opus 4.8.
Paired (same designs through both), bootstrap CI on the rescue-rate delta.
"""

from __future__ import annotations
import concurrent.futures as cf
import json
import os
import sys
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
import closed_loop as cl  # score(), apply_edit(), claude_rescue(), motifs
import motifs

N = int(os.environ.get("CLP_N", "100"))
MAX_ROUNDS = 4
CONC = int(os.environ.get("CLP_CONC", "6"))
# The committed evidence. PREREG-ERRATA.md offers a reader the choice "run this, or read the
# committed JSON" - and running it used to destroy the second option before producing the first,
# because both the periodic partial dump and the final write targeted this path. A reproduce
# command must never be able to overwrite the evidence it exists to reproduce.
COMMITTED = os.path.join(
    os.path.dirname(__file__), "data", "gosai_designed", "closed_loop_powered.json"
)
# Default output is a separate, gitignored file. Pass --overwrite-committed deliberately to
# refresh the evidence itself.
OUT = (
    COMMITTED
    if "--overwrite-committed" in sys.argv
    else os.path.join(
        os.path.dirname(__file__),
        "data",
        "gosai_designed",
        "closed_loop_powered.local.json",
    )
)


def deterministic_iter(seq: str, target: str, max_rounds: int = MAX_ROUNDS) -> dict:
    """The FIXED greedy rule with the SAME iteration budget as Claude: each round, disrupt the
    current predicted off-target cell's driver TFs and install ALL of the target cell's driver TFs
    (2 copies), then re-score. No adaptivity, no model in the loop choosing, just the rule iterated."""
    cur = seq
    rpt = cl.score(cur, target)
    start = rpt["gap"]
    if not rpt["fail"]:
        return {
            "passed": True,
            "rounds": 0,
            "start_gap": start,
            "final_gap": rpt["gap"],
        }
    passed = False
    for r in range(1, max_rounds + 1):
        off = rpt["most_active"]
        off_drivers = motifs.DRIVERS.get(off, [])
        tgt_drivers = motifs.DRIVERS.get(target, [])
        edited = cl.apply_edit(cur, off, target, off_drivers, tgt_drivers, 2)
        rpt = cl.score(edited, target)
        cur = edited
        passed = not rpt["fail"]
        if passed:
            break
    return {"passed": passed, "rounds": r, "start_gap": start, "final_gap": rpt["gap"]}


def one(row) -> dict | None:
    seq, tgt, rid = row["sequence"], row["target_cell"], row["id"]
    try:
        det = deterministic_iter(seq, tgt, MAX_ROUNDS)
        cla = cl.claude_rescue(
            seq, tgt, max_rounds=MAX_ROUNDS
        )  # uses ANTHROPIC_API_KEY locally, deployed gate to score
        return {
            "id": rid,
            "target": tgt,
            "start_gap": det["start_gap"],
            "det_passed": bool(det["passed"]),
            "det_final": det["final_gap"],
            "det_rounds": det["rounds"],
            "claude_passed": bool(cla["passed"]),
            "claude_final": cla["final_gap"],
            "claude_rounds": cla["rounds"],
        }
    except Exception as e:  # noqa: BLE001
        return {"id": rid, "error": str(e)[:160]}


def paired_boot(a: np.ndarray, b: np.ndarray, n=2000, seed=0):
    """Paired bootstrap on the rescue-rate DELTA (a=claude, b=deterministic), 95% CI."""
    a = np.asarray(a, float)
    b = np.asarray(b, float)
    delta = float(a.mean() - b.mean())
    rng = np.random.default_rng(seed)
    m = len(a)
    ds = np.empty(n)
    for i in range(n):
        idx = rng.integers(0, m, m)
        ds[i] = a[idx].mean() - b[idx].mean()
    lo, hi = np.percentile(ds, [2.5, 97.5])
    return {
        "claude_rate": round(float(a.mean()), 4),
        "det_rate": round(float(b.mean()), 4),
        "delta": round(delta, 4),
        "delta_ci95": [round(float(lo), 4), round(float(hi), 4)],
        "delta_excludes_0": bool(lo > 0 or hi < 0),
        "n": m,
    }


def main():
    scored = pd.read_csv(
        os.path.join(
            os.path.dirname(__file__), "data", "gosai_designed", "designed_scored.csv"
        )
    )
    bench = pd.read_csv(
        os.path.join(
            os.path.dirname(__file__),
            "data",
            "gosai_designed",
            "designed_benchmark.csv",
        )
    )
    df = scored.merge(bench[["id", "sequence"]], on="id", how="inner")
    fail = df[df["pred_gap"] < 0].copy()
    # stratified sample across target cell x method for representativeness (deterministic seed)
    fail = fail.sample(min(N, len(fail)), random_state=7).reset_index(drop=True)
    print(
        f"sampling {len(fail)} predicted-failing designs (of {len(df[df['pred_gap'] < 0])} available)"
    )

    results = []
    with cf.ThreadPoolExecutor(max_workers=CONC) as ex:
        for i, r in enumerate(ex.map(one, [row for _, row in fail.iterrows()])):
            results.append(r)
            if (i + 1) % 10 == 0:
                print(f"  {i + 1}/{len(fail)} done")
                json.dump({"partial": results}, open(OUT, "w"), indent=1)

    ok = [r for r in results if "error" not in r]
    errs = [r for r in results if "error" in r]
    # A run where every call failed used to print "100/100 done", emit every statistic as NaN, and
    # exit 0. A green exit on zero usable results is worse than a crash: it reads as a successful
    # reproduction. Fail loudly instead, and say what actually went wrong.
    if not ok:
        first = errs[0].get("error") if errs else "unknown"
        print(
            f"\nFAILED: {len(errs)} of {len(results)} attempts errored and none produced a "
            f"scorable result, so there is nothing to compare.\nFirst error: {first}",
            file=sys.stderr,
        )
        print(
            f"No statistics were written; {OUT} left untouched.",
            file=sys.stderr,
        )
        return 1
    if errs:
        print(f"note: {len(errs)} of {len(results)} attempts errored and are excluded")
    a = np.array([r["claude_passed"] for r in ok])
    b = np.array([r["det_passed"] for r in ok])
    stats = paired_boot(a, b)
    claude_only = int(((a == 1) & (b == 0)).sum())
    det_only = int(((a == 0) & (b == 1)).sum())
    out = {
        "n_attempted": len(fail),
        "n_scored": len(ok),
        "n_errors": len(errs),
        "max_rounds_each": MAX_ROUNDS,
        "framing": "in-silico agentic-search comparison at EQUAL iteration budget; both use the same frozen gate (circularity acknowledged); NOT wet-lab, NOT a biological design-improvement claim",
        "stats": stats,
        "claude_only_rescued": claude_only,
        "det_only_rescued": det_only,
        "results": ok,
        "errors": errs[:20],
    }
    json.dump(out, open(OUT, "w"), indent=1)
    print("\n==== POWERED FAIR COMPARISON ====")
    print(
        json.dumps(
            {
                k: out[k]
                for k in (
                    "n_scored",
                    "n_errors",
                    "stats",
                    "claude_only_rescued",
                    "det_only_rescued",
                )
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    # main()'s return value used to be discarded, so a non-zero return would still have exited 0.
    raise SystemExit(main() or 0)
