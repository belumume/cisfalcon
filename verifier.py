"""CisFalcon verifier: a pre-synthesis QC gate for AI-designed cell-type-specific enhancers.

DEFENSIVE tool. It predicts, from sequence alone and before any DNA is synthesized,
whether an AI-designed regulatory element will FAIL its intended cell-type specificity
in the wet lab. It prevents wasted synthesis; it does not design DNA.

Two layers:
  1. Gate (deterministic ML): the ensembled atlas activity model (gate.py) predicts the
     12-cell-type activity profile, the specificity gap for the intended target, and a
     failure probability calibrated on held-out measured MPRA data.
  2. Reasoning (Claude, first-party API, parallel agents): independent agents interpret the
     mechanism, ground the risk in the measured benchmark, and adversarially challenge the
     call; a synthesizer returns the final verdict. This is the "built with Claude" layer.

Ground truth (leakage-immune, cross-lab): AUROC 0.80 discriminating measured specificity
failures on 93,435 independent AI-designed enhancers (Gosai et al 2024, zero training overlap),
vs 0.50 baselines. Triage ranker, not a hard gate: riskiest 2% -> 7.8x enrichment (PPV 0.49).
The per-sequence signal with cell and generator base-rates removed is 0.66. In-distribution
0.896 is a sanity check with a near-duplicate-leakage caveat; the cross-lab number is flagship.
"""

from __future__ import annotations
import os, json, pathlib, concurrent.futures as cf
import numpy as np, pandas as pd

import gate  # local: encoder + ensembled model + specificity_gap

_DATA = pathlib.Path(__file__).parent / "data"
ORCH_MODEL = "claude-opus-4-8"  # synthesizer / adjudicator
LENS_MODEL = "claude-sonnet-5"  # parallel reasoning lenses


# ----------------------------------------------------------------------------- gate layer
class Calibration:
    """Maps a predicted specificity gap to an empirical failure probability, fit by
    isotonic regression on held-out (predicted_gap, measured_fail) pairs. Falls back to a
    documented sigmoid if the calibration file is absent."""

    def __init__(self, path=_DATA / "calibration.csv"):
        self.iso = None
        if path.exists():
            df = pd.read_csv(path)
            try:
                from sklearn.isotonic import IsotonicRegression

                self.iso = IsotonicRegression(
                    increasing=False, out_of_bounds="clip"
                ).fit(df["pred_gap"].values, df["fail"].values)
                self.base = float(df["fail"].mean())
            except Exception:
                self.iso = None
        self.base = getattr(self, "base", 0.36)

    def p_fail(self, gap: float) -> float:
        if self.iso is not None:
            return float(self.iso.predict([gap])[0])
        # documented fallback: logistic centered at gap=0 (fail if not most-active in target)
        return float(1.0 / (1.0 + np.exp(3.0 * gap)))


def gate_report(
    sequence: str, target_cell: str, calib: Calibration | None = None
) -> dict:
    """Deterministic gate verdict for one design."""
    calib = calib or Calibration()
    pred = gate.score_sequences([sequence])[0]  # (12,) predicted log2FC
    gaps = gate.specificity_gap(pred[None, :], target_cell)
    gap = float(gaps[0])
    idx = [gate.CELL_IDX[c] for c in gate.TARGET_CELLS]
    profile = {c: round(float(pred[gate.CELL_IDX[c]]), 3) for c in gate.MPRA_CELL_LINES}
    most_active = gate.TARGET_CELLS[int(np.argmax(pred[idx]))]
    p_fail = calib.p_fail(gap)
    return {
        "target_cell": target_cell,
        "predicted_specificity_gap": round(gap, 3),
        "predicted_most_active_cell": most_active,
        "predicted_fail": bool(gap <= 0),
        "calibrated_fail_probability": round(p_fail, 3),
        "predicted_profile_log2fc": profile,
        "off_target_risk_cells": sorted(
            [
                c
                for c in gate.TARGET_CELLS
                if c != target_cell
                and pred[gate.CELL_IDX[c]] >= pred[gate.CELL_IDX[target_cell]]
            ],
            key=lambda c: -pred[gate.CELL_IDX[c]],
        ),
    }


# ------------------------------------------------------------------------- reasoning layer
GROUND_TRUTH = (
    "Leakage-immune cross-lab validation of this gate: on 93,435 INDEPENDENT AI-designed enhancers "
    "from a different lab, activity model, and generators the model never saw (Gosai et al 2024, "
    "Nature; zero training overlap), it discriminates measured wet-lab specificity failures at AUROC "
    "0.80, versus 0.50 for GC-content and length baselines. It is a triage RANKER, not a hard abort "
    "gate: at the 6.3% base failure rate, flagging the riskiest 2% enriches for real failures 7.8x "
    "(PPV 0.49) and the riskiest 10% captures 43% of all failures. The genuine per-sequence signal, "
    "with both the target-cell and generator base-rates removed, is AUROC 0.66 (strong on failure-"
    "prone designs, near chance on the best-optimized ones). An in-distribution sanity check scores "
    "0.896 but carries a near-duplicate-leakage caveat, so the cross-lab number is the flagship. "
    "Failure is defined transparently: a design FAILS if it is not most-active in its intended target "
    "cell (specificity gap <= 0). The emitted failure probability is calibrated marginally on this "
    "design population (a design it prints as 70% risk fails about 70% of the time across the "
    "population), not conditioned per target cell, so treat its absolute value as a population-level "
    "estimate."
)

LENSES = {
    "mechanism": (
        "You are a regulatory-genomics reviewer. Given a model-predicted per-cell-type activity "
        "profile for an AI-designed enhancer and its intended target cell, explain in mechanistic "
        "terms whether it is predicted to be cell-type SPECIFIC, and name the specific off-target "
        "cell types that are the risk. Be concrete and brief." +
        " Answer in 2 to 4 sentences of plain prose. Do not use markdown, headers, bold, or bullet lists."
    ),
    "precedent": (
        "You are a QC analyst grounding a prediction in measured data. Given the design's predicted "
        "specificity gap and target cell, state what the held-out benchmark implies about this "
        "design's failure probability, and how much to trust it. Cite the ground-truth numbers." +
        " Answer in 2 to 4 sentences of plain prose. Do not use markdown, headers, bold, or bullet lists."
    ),
    "adversary": (
        "You are an adversarial skeptic. Argue the gate's verdict on this design could be WRONG: "
        "model blind spots, out-of-distribution sequence features, calibration limits, target cells "
        "the model predicts poorly. Default to raising real doubts, not rubber-stamping." +
        " Answer in 2 to 4 sentences of plain prose. Do not use markdown, headers, bold, or bullet lists."
    ),
}


def _agent(client, model, system, user, schema=None):
    kw = dict(
        model=model,
        max_tokens=2000,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    if schema:
        kw["tools"] = [
            {
                "name": "report",
                "description": "Return the structured result.",
                "input_schema": schema,
            }
        ]
        kw["tool_choice"] = {"type": "tool", "name": "report"}
    resp = client.messages.create(**kw)
    if resp.stop_reason == "refusal":
        return {"refused": True}
    if schema:
        for b in resp.content:
            if getattr(b, "type", None) == "tool_use":
                return b.input
        return {}
    return "".join(b.text for b in resp.content if getattr(b, "type", None) == "text")


class CisFalconVerifier:
    def __init__(self, use_agents: bool = True):
        self.calib = Calibration()
        self.use_agents = use_agents
        self._client = None
        if use_agents:
            import anthropic

            self._client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    def verify(self, sequence: str, target_cell: str) -> dict:
        if target_cell not in gate.TARGET_CELLS:
            raise ValueError(f"target_cell must be one of {gate.TARGET_CELLS}")
        report = gate_report(sequence, target_cell, self.calib)
        out = {"gate": report}
        if not self.use_agents:
            out["verdict"] = _rule_verdict(report)
            return out

        ctx = (
            f"{GROUND_TRUTH}\n\nDESIGN under review (predicted, pre-synthesis):\n"
            f"{json.dumps(report, indent=2)}"
        )
        with cf.ThreadPoolExecutor(max_workers=3) as ex:
            lens_out = dict(
                zip(
                    LENSES,
                    ex.map(
                        lambda kv: _agent(self._client, LENS_MODEL, kv[1], ctx),
                        LENSES.items(),
                    ),
                )
            )
        verdict_schema = {
            "type": "object",
            "properties": {
                "verdict": {"type": "string", "enum": ["FAIL", "PASS", "BORDERLINE"]},
                "confidence": {"type": "number"},
                "recommendation": {"type": "string"},
                "reasoning": {"type": "string"},
                "grounded_in": {"type": "string"},
            },
            "required": ["verdict", "confidence", "recommendation", "reasoning"],
        }
        synth = _agent(
            self._client,
            ORCH_MODEL,
            "You are the CisFalcon adjudicator. Synthesize the gate report and the three "
            "independent reviews into ONE pre-synthesis verdict for a wet-lab scientist deciding "
            "whether to synthesize this AI-designed enhancer. This is a DEFENSIVE gate: a FAIL "
            "means 'do not synthesize, it will likely miss its target cell'. Be calibrated and "
            "cite the measured ground truth.",
            f"{ctx}\n\nINDEPENDENT REVIEWS:\n{json.dumps(lens_out, indent=2)}",
            schema=verdict_schema,
        )
        out["reviews"] = lens_out
        out["verdict"] = synth
        return out


def _rule_verdict(report: dict) -> dict:
    p = report["calibrated_fail_probability"]
    v = "FAIL" if report["predicted_fail"] else ("BORDERLINE" if p > 0.4 else "PASS")
    return {
        "verdict": v,
        "confidence": round(abs(p - 0.5) * 2, 2),
        "recommendation": (
            "do not synthesize; predicted to miss target cell"
            if v == "FAIL"
            else "predicted specific; reasonable to synthesize"
            if v == "PASS"
            else "borderline; consider redesign or add controls"
        ),
        "grounded_in": "gate calibration only (agents disabled)",
    }


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--seq", required=True)
    ap.add_argument("--target", required=True)
    ap.add_argument("--no-agents", action="store_true")
    a = ap.parse_args()
    v = CisFalconVerifier(use_agents=not a.no_agents)
    print(json.dumps(v.verify(a.seq, a.target), indent=2))
