"""Audit fix #8: MEASURE whether the Claude agent layer improves the decision over
the deterministic gate alone, instead of asserting it. Sample real designs across
the decision boundary, run the full harness on each, and compare gate-only verdict
accuracy vs agent verdict accuracy against measured wet-lab truth."""

import json, pathlib, sys
import numpy as np, pandas as pd
from verifier import CisFalconVerifier

scored = pd.read_csv("data/gosai_designed/designed_scored.csv")
bench = pd.read_csv("data/gosai_designed/designed_benchmark.csv")[["id", "sequence"]]
d = scored.merge(bench, on="id")

# stratified sample emphasizing the boundary (|pred_gap| small) where agents could add value,
# plus clear fails and clear passes, balanced on measured truth
rng = np.random.RandomState(0)
d["absgap"] = d["pred_gap"].abs()
fails = d[d.measured_fail == 1]
passes = d[d.measured_fail == 0]
near = d.reindex(d["absgap"].sort_values().index)[:400]
sample = (
    pd.concat(
        [
            fails.sample(min(10, len(fails)), random_state=0),
            passes.sample(10, random_state=0),
            near.sample(min(10, len(near)), random_state=1),
        ]
    )
    .drop_duplicates("id")
    .reset_index(drop=True)
)
print(
    f"ablation sample n={len(sample)} (measured fail {int(sample.measured_fail.sum())})",
    flush=True,
)

v = CisFalconVerifier(use_agents=True)
rows = []
for _, r in sample.iterrows():
    tc = r["target_cell"]
    out = v.verify(r["sequence"], tc)
    gate_fail = out["gate"]["predicted_fail"]
    verd = out.get("verdict", {})
    agent_v = verd.get("verdict") if isinstance(verd, dict) else None
    rows.append(
        {
            "id": r["id"],
            "measured_fail": int(r["measured_fail"]),
            "gate_pred_fail": bool(gate_fail),
            "agent_verdict": agent_v,
            "pred_gap": round(float(r["pred_gap"]), 3),
        }
    )
    print(
        f"  {r['id'][:34]:34s} truth={int(r['measured_fail'])} gate_fail={gate_fail} agent={agent_v}",
        flush=True,
    )

res = pd.DataFrame(rows)
res.to_csv("data/gosai_designed/ablation.csv", index=False)
truth = res["measured_fail"].values.astype(bool)
gate = res["gate_pred_fail"].values.astype(bool)
# map agent verdict to a binary "flag as fail" (FAIL or BORDERLINE = flag)
agent_flag = res["agent_verdict"].isin(["FAIL", "BORDERLINE"]).values
print("\n===== ABLATION =====", flush=True)
print(f"gate-only  accuracy = {(gate == truth).mean():.3f}", flush=True)
print(
    f"agent-flag accuracy = {(agent_flag == truth).mean():.3f}  (FAIL|BORDERLINE = flag)",
    flush=True,
)
print(f"agent verdicts: {res['agent_verdict'].value_counts().to_dict()}", flush=True)
print(
    f"cases where agent DIFFERS from gate: {(agent_flag != gate).sum()}/{len(res)}",
    flush=True,
)
print(
    "Honest read: if accuracies are ~equal, the agent layer adds EXPLANATION/diagnosis, not accuracy - report that.",
    flush=True,
)
