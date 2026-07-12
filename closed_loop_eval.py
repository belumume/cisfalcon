"""Measured value of the Claude closed-loop optimizer vs the deterministic single-edit rule.

For N predicted-failing designs (sampled diverse across target cells), run:
  - deterministic_rescue: the single fixed /api/redesign edit (disrupt top off-target sites + install
    up to 6 target motifs, once).
  - claude_rescue: Claude (Opus) iterates grounded motif edits, using the frozen gate as a tool, until
    the design PASSES or it aborts.
Report rescue rate for each, mean Claude rounds, and the LIFT = designs Claude rescues that the single
deterministic edit does not. Honest, in-silico (the frozen gate agrees the rescue passes), not wet-lab.

    ANTHROPIC_API_KEY=... python closed_loop_eval.py N=20
"""

from __future__ import annotations
import json, os, sys, time
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
import closed_loop as cl

N = 20
for a in sys.argv[1:]:
    if a.startswith("N="):
        N = int(a.split("=")[1])

DATA = os.path.join(os.path.dirname(__file__), "data", "gosai_designed")


def sample_failing(n: int):
    bench = pd.read_csv(
        os.path.join(DATA, "designed_benchmark.csv"),
        usecols=["id", "target_cell", "method", "sequence"],
    )
    scored = pd.read_csv(
        os.path.join(DATA, "designed_scored.csv"), usecols=["id", "pred_gap"]
    )
    df = bench.merge(scored, on="id")
    fail = df[df["pred_gap"] < -0.2].copy()  # clearly predicted-failing
    # diverse: spread across target cells + methods, deterministic order (no RNG)
    fail = fail.sort_values(["target_cell", "method", "pred_gap"]).reset_index(
        drop=True
    )
    step = max(1, len(fail) // (n * 2))
    picks = fail.iloc[::step].head(n * 2)  # oversample; some may pass on the live gate
    return picks[["id", "target_cell", "method", "sequence", "pred_gap"]].to_dict(
        "records"
    )


def main():
    cands = sample_failing(N)
    print(
        f"sampled {len(cands)} predicted-failing candidates; targeting {N} that fail on the live gate\n"
    )
    rows = []
    for c in cands:
        if len(rows) >= N:
            break
        seq, tgt = c["sequence"], c["target_cell"]
        try:
            start = cl.score(seq, tgt)
        except Exception as e:  # noqa: BLE001
            print(f"  {c['id'][:24]}: score error, skip ({e})")
            continue
        if not start["fail"]:
            continue  # only rescue designs that actually fail on the live gate
        try:
            det = cl.deterministic_rescue(seq, tgt)
        except Exception:
            det = {"passed": None}
        try:
            cla = cl.claude_rescue(seq, tgt, max_rounds=4)
        except Exception as e:  # noqa: BLE001
            print(f"  {c['id'][:24]}: claude error, skip ({e})")
            continue
        row = {
            "id": c["id"],
            "target": tgt,
            "method": c["method"],
            "start_gap": start["gap"],
            "det_passed": det.get("passed"),
            "det_gap": det.get("final_gap"),
            "claude_passed": cla["passed"],
            "claude_gap": cla["final_gap"],
            "claude_rounds": cla["rounds"],
        }
        rows.append(row)
        print(
            f"  {len(rows):2d}. {tgt:6s} {c['method'][:14]:14s} start {start['gap']:+.2f} | "
            f"det {'PASS' if det.get('passed') else 'fail'} | "
            f"claude {'PASS' if cla['passed'] else 'fail'} ({cla['rounds']}r -> {cla['final_gap']:+.2f})"
        )

    det_pass = sum(1 for r in rows if r["det_passed"])
    cla_pass = sum(1 for r in rows if r["claude_passed"])
    lift = [r for r in rows if r["claude_passed"] and not r["det_passed"]]
    regress = [r for r in rows if r["det_passed"] and not r["claude_passed"]]
    mean_rounds = round(sum(r["claude_rounds"] for r in rows) / max(1, len(rows)), 2)
    summary = {
        "n_failing_designs": len(rows),
        "deterministic_single_edit_rescued": det_pass,
        "claude_loop_rescued": cla_pass,
        "claude_only_rescues_lift": len(lift),
        "deterministic_only_rescues": len(regress),
        "claude_mean_rounds": mean_rounds,
    }
    print("\n=== SUMMARY ===")
    print(json.dumps(summary, indent=2))
    out = os.path.join(
        os.path.dirname(__file__), "data", "gosai_designed", "closed_loop_eval.json"
    )
    json.dump({"summary": summary, "rows": rows}, open(out, "w"), indent=2)
    print(f"\nwrote {out}")


if __name__ == "__main__":
    main()
