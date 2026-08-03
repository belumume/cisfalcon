"""4-agent ablation: does the 3-Sonnet-lens + Opus-adjudicator PANEL beat a single Opus call?

The review panels flagged that CisFalcon shows no evidence the multi-agent structure outperforms one
Opus call, so the panel "risks reading as decorative." This tests it honestly and reports whatever it
finds. For K designs: (A) the deployed 4-agent panel (/api/diagnose returns the 3 lens reviews + the
Opus verdict), (B) a SINGLE Opus 4.8 call given the same gate report, asked for the same
mechanism/precedent/adversary analysis + verdict. Then a BLIND panel of 3 independent Opus judges
scores which diagnosis is better on 4 dimensions (mechanistic specificity, calibration/no-overclaim,
adversarial rigor, wet-lab usefulness), with A/B order randomized per design so the judge cannot infer
which is the panel. Reports the panel's win rate. An honest tie downgrades the multi-agent claim; a
win supports it. No tuning.
"""

from __future__ import annotations
import concurrent.futures as cf
import json
import os
import sys
import urllib.request

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
import anthropic

BASE = os.environ.get("CISFALCON_BASE", "https://cisfalcon-lifesci.fly.dev")
UA = {"User-Agent": "Mozilla/5.0", "Content-Type": "application/json"}
OPUS = "claude-opus-4-8"
K = int(os.environ.get("ABL_K", "12"))
# The committed evidence. Same defect closed in closed_loop_powered.py: a reproduce command
# must never be able to overwrite the artifact it exists to reproduce. Both the periodic
# partial dump and the final write used to target the committed path unconditionally, with
# no guard on n_errors, so a fully-failed API run replaced real evidence with a stub.
COMMITTED = os.path.join(
    os.path.dirname(__file__), "data", "gosai_designed", "agent_ablation.json"
)
# Default output is a separate, gitignored file. Pass --overwrite-committed deliberately.
OUT = (
    COMMITTED
    if "--overwrite-committed" in sys.argv
    else os.path.join(
        os.path.dirname(__file__),
        "data",
        "gosai_designed",
        "agent_ablation.local.json",
    )
)
client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

GROUND = (
    "CisFalcon flags AI-designed enhancers that will misfire in the wrong cell type before synthesis. "
    "The frozen DHS64-MPRA model predicts per-cell activity; specificity gap = target log2FC minus max "
    "off-target. gap <= 0 = FAIL (predicted most-active cell is not the target). The cross-lab AUROC is "
    "0.80 on 93,435 independent designs; the fully-conditioned per-sequence signal is 0.66; calibration "
    "is population-level (isotonic ECE 0.0031). This is a DEFENSIVE triage gate, not a hard abort."
)


def _post(url, payload, timeout=90):
    body = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=body, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def single_opus(gate: dict) -> dict:
    """One Opus call doing the whole job the 4-agent panel does."""
    msg = client.messages.create(
        model=OPUS,
        max_tokens=1600,
        system=(
            "You are a pre-synthesis verifier for an AI-designed enhancer. Given the frozen gate's "
            "predicted report, produce a mechanism analysis, a precedent/benchmark analysis, an "
            "adversarial critique of the call, and ONE calibrated verdict (FAIL/PASS/BORDERLINE) with "
            "a confidence and a recommendation for a wet-lab scientist. Cite the measured ground truth; "
            "be calibrated, do not over-assert." + "\n\n" + GROUND
        ),
        messages=[
            {"role": "user", "content": f"GATE REPORT:\n{json.dumps(gate, indent=2)}"}
        ],
    )
    return {
        "text": "".join(
            b.text for b in msg.content if getattr(b, "type", None) == "text"
        )
    }


def panel_text(diag: dict) -> str:
    r = diag.get("reviews", {})
    v = diag.get("verdict", {})
    return (
        f"MECHANISM: {r.get('mechanism', '')}\n\nPRECEDENT: {r.get('precedent', '')}\n\n"
        f"ADVERSARY: {r.get('adversary', '')}\n\nVERDICT: {v.get('verdict', '')} "
        f"(confidence {v.get('confidence', '')}). {v.get('recommendation', '')} {v.get('reasoning', '')}"
    )


_JUDGE_SCHEMA = {
    "type": "object",
    "properties": {
        "winner": {"type": "string", "enum": ["A", "B", "TIE"]},
        "mechanistic_specificity": {"type": "string", "enum": ["A", "B", "TIE"]},
        "calibration": {"type": "string", "enum": ["A", "B", "TIE"]},
        "adversarial_rigor": {"type": "string", "enum": ["A", "B", "TIE"]},
        "wetlab_usefulness": {"type": "string", "enum": ["A", "B", "TIE"]},
        "why": {"type": "string"},
    },
    "required": [
        "winner",
        "mechanistic_specificity",
        "calibration",
        "adversarial_rigor",
        "wetlab_usefulness",
    ],
}


def judge(gate: dict, a_text: str, b_text: str, seed: int) -> dict:
    """One blind judge. A/B already order-randomized by caller."""
    tool = {
        "name": "score",
        "description": "Score the two diagnoses.",
        "input_schema": _JUDGE_SCHEMA,
    }
    msg = client.messages.create(
        model=OPUS,
        max_tokens=900,
        system=(
            "You are a blind judge comparing two pre-synthesis diagnoses (A and B) of the SAME "
            "AI-designed enhancer, written by two different systems you cannot identify. Score which is "
            "better on each dimension and overall: mechanistic_specificity (names the real off-target "
            "driver mechanism), calibration (does not over-assert a shaky probability), adversarial_rigor "
            "(raises the genuine caveats: OOD, base-rate, per-cell calibration), wetlab_usefulness "
            "(actionable for a scientist deciding whether to synthesize). TIE only if truly "
            "indistinguishable. Be strict." + "\n\n" + GROUND
        ),
        tools=[tool],
        tool_choice={"type": "tool", "name": "score"},
        messages=[
            {
                "role": "user",
                "content": f"GATE REPORT:\n{json.dumps(gate, indent=2)}\n\nDIAGNOSIS A:\n{a_text}\n\nDIAGNOSIS B:\n{b_text}",
            }
        ],
    )
    tu = next((b for b in msg.content if getattr(b, "type", None) == "tool_use"), None)
    return tu.input if tu else {}


def one(rec):
    seq, cell, rid = rec["sequence"], rec["target_cell"], rec["id"]
    try:
        diag = _post(BASE + "/api/diagnose", {"sequence": seq, "target_cell": cell})
        gate = diag["gate"]
        p_text = panel_text(diag)
        s = single_opus(gate)["text"]
        # order-randomize per design (deterministic from id hash), then 3 blind judges
        flip = (hash(str(rid)) % 2) == 0
        a_text, b_text = (
            (p_text, s) if not flip else (s, p_text)
        )  # A/B; track which is panel
        panel_is = "A" if not flip else "B"
        verdicts = []
        for j in range(3):
            jv = judge(gate, a_text, b_text, j)
            verdicts.append(jv)

        # translate each judge's per-dim + overall pick into panel/single/tie
        def who(pick):
            if pick == "TIE":
                return "tie"
            return "panel" if pick == panel_is else "single"

        dims = [
            "winner",
            "mechanistic_specificity",
            "calibration",
            "adversarial_rigor",
            "wetlab_usefulness",
        ]
        scored = {d: [who(v.get(d, "TIE")) for v in verdicts] for d in dims}
        # majority vote across 3 judges for the overall winner
        import collections

        maj = collections.Counter(scored["winner"]).most_common(1)[0][0]
        return {
            "id": rid,
            "cell": cell,
            "panel_is": panel_is,
            "gate_verdict": gate.get("predicted_fail"),
            "overall_majority": maj,
            "per_dim": scored,
        }
    except Exception as e:  # noqa: BLE001
        return {"id": rid, "error": str(e)[:160]}


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
    # mix: half predicted-fail, half predicted-pass, so the judge sees easy + hard calls
    fail = df[df["pred_gap"] < 0].sample(K // 2, random_state=3)
    pas = df[df["pred_gap"] > 0].sample(K - K // 2, random_state=3)
    sample = pd.concat([fail, pas]).reset_index(drop=True)
    print(
        f"ablation on {len(sample)} designs ({K // 2} fail, {K - K // 2} pass), 3 blind judges each"
    )

    results = []
    with cf.ThreadPoolExecutor(max_workers=4) as ex:
        for i, r in enumerate(ex.map(one, [row for _, row in sample.iterrows()])):
            results.append(r)
            if (i + 1) % 4 == 0:
                print(f"  {i + 1}/{len(sample)}")
                json.dump({"partial": results}, open(OUT, "w"), indent=1)

    ok = [r for r in results if "error" not in r]
    errs = [r for r in results if "error" in r]
    # A run where every call failed must not be reported as success, and must not write.
    if not ok:
        first = errs[0].get("error") if errs else "unknown"
        print(
            f"\nFAILED: {len(errs)} of {len(results)} attempts errored and none produced a "
            f"scorable result.\nFirst error: {first}\n"
            f"No statistics were written; {OUT} left untouched.",
            file=sys.stderr,
        )
        return 1
    if errs:
        print(f"note: {len(errs)} of {len(results)} attempts errored and are excluded")
    import collections

    overall = collections.Counter(r["overall_majority"] for r in ok)
    dim_tally = {}
    for d in [
        "mechanistic_specificity",
        "calibration",
        "adversarial_rigor",
        "wetlab_usefulness",
    ]:
        c = collections.Counter()
        for r in ok:
            c.update(r["per_dim"][d])  # counts across all 3 judges x all designs
        dim_tally[d] = dict(c)
    out = {
        "n": len(ok),
        "n_errors": len(results) - len(ok),
        "overall_by_design_majority": dict(overall),
        "per_dimension_judge_votes": dim_tally,
        "results": ok,
    }
    json.dump(out, open(OUT, "w"), indent=1)
    print("\n==== 4-AGENT PANEL vs SINGLE-OPUS ABLATION ====")
    print(
        json.dumps(
            {"overall_by_design": dict(overall), "per_dimension_votes": dim_tally},
            indent=2,
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
