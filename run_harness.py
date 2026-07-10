"""Full end-to-end harness run (gate + Claude agents) on the real designs.
No mock: real models for the gate, real first-party API for the reasoning layer.
"""

import json, pathlib, sys
from verifier import CisFalconVerifier

designs = json.loads(pathlib.Path("real_designs.json").read_text())
v = CisFalconVerifier(use_agents=True)

for d in designs:
    print(
        f"\n{'=' * 70}\nDESIGN {d['id']}  target={d['target_cell']}  "
        f"(measured gap {d['measured_gap']:+.2f}, measured_fail={d['measured_fail']})\n{'=' * 70}"
    )
    out = v.verify(d["sequence"], d["target_cell"])
    g = out["gate"]
    print(
        f"GATE: predicted_gap={g['predicted_specificity_gap']:+.3f} "
        f"predicted_fail={g['predicted_fail']} p_fail={g['calibrated_fail_probability']:.3f} "
        f"most_active={g['predicted_most_active_cell']}"
    )
    for lens, txt in out.get("reviews", {}).items():
        s = txt if isinstance(txt, str) else json.dumps(txt)
        print(f"  [{lens}] {s[:220].strip()}")
    verd = out["verdict"]
    if isinstance(verd, dict) and not verd.get("refused"):
        print(
            f"VERDICT: {verd.get('verdict')}  conf={verd.get('confidence')}  "
            f"-> {verd.get('recommendation')}"
        )
        print(f"  reasoning: {str(verd.get('reasoning', ''))[:280]}")
    else:
        print(f"VERDICT raw: {verd}")
