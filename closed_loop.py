"""Claude-driven closed-loop design rescue: the frozen gate SCORES, Claude OPTIMIZES.

The four-agent verifier DIAGNOSES; this makes Claude LOAD-BEARING for a capability the frozen gate
alone does not have: iterative design rescue. Claude (Opus 4.8) runs a genuine tool-using loop. It
proposes a grounded motif edit (disrupt the predicted off-target cell's driver TFs, install the target
cell's driver TFs), calls the FROZEN gate as a tool to re-score, reads the new specificity gap, and
iterates until the design PASSES (gap > 0) or it cannot improve further. Every edit is a real JASPAR
driver motif; Claude cannot invent sequence. This is an in-silico consistency loop (the same frozen
gate that flagged the design agrees the rescued design passes), NOT wet-lab validation.

Scoring runs on the DEPLOYED gate (POST /api/predict) so no local ML is needed; the edit machinery is
the same pure-Python JASPAR logic the deterministic /api/redesign uses, but here Claude picks the TFs
and decides when to stop.

Usage:
    ANTHROPIC_API_KEY=... python closed_loop.py --demo        # rescue one flagged design, show the loop
    ANTHROPIC_API_KEY=... python closed_loop.py --eval N=20    # measured rescue rate vs the deterministic rule
"""

from __future__ import annotations
import json, os, sys, time, urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "webapp", "backend"))
import motifs  # pure JASPAR PWM logic, no TensorFlow

BASE = os.environ.get("CISFALCON_BASE", "https://cisfalcon-lifesci.fly.dev")
PREDICT_URL = BASE + "/api/predict"
REDESIGN_URL = BASE + "/api/redesign"
OPTIMIZER_MODEL = "claude-opus-4-8"
UA = {"User-Agent": "Mozilla/5.0", "Content-Type": "application/json"}


def _post(url: str, payload: dict, timeout: int = 35) -> dict:
    body = json.dumps(payload).encode()
    last = None
    for attempt in range(4):
        try:
            req = urllib.request.Request(url, data=body, headers=UA)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read())
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"POST {url} failed: {last}")


def score(seq: str, target: str) -> dict:
    """Re-score with the frozen deployed gate."""
    d = _post(PREDICT_URL, {"sequence": seq, "target_cell": target})
    return {
        "gap": round(float(d["predicted_specificity_gap"]), 3),
        "most_active": d["predicted_most_active_cell"],
        "fail": bool(d["predicted_fail"]),
    }


def apply_edit(
    seq: str,
    off_cell: str,
    target_cell: str,
    disrupt_tfs: list,
    install_tfs: list,
    copies: int,
) -> str:
    """Apply a grounded motif edit (same machinery as /api/redesign, but Claude picks the TFs).
    Disrupt = overwrite the strongest sites of the named off-target driver TFs with neutral filler.
    Install = insert `copies` consensus copies of each named target driver TF. Only real drivers act."""
    edited = list(seq)
    off_drivers = set(motifs.DRIVERS.get(off_cell, []))
    want = {t for t in disrupt_tfs if t in off_drivers}
    for site in motifs.driver_sites(seq, off_cell, top=8):
        if site["tf"] not in want:
            continue
        p, L = site["pos"], site["length"]
        if p + L <= len(edited):
            filler = ("GAATTC" * (L // 6 + 1))[:L]
            edited[p : p + L] = list(filler)
    edited = "".join(edited)
    tgt_drivers = set(motifs.DRIVERS.get(target_cell, []))
    n = 0
    copies = max(1, min(int(copies or 2), 3))
    for tf in install_tfs:
        if tf not in tgt_drivers:
            continue
        cons = motifs.consensus_seq(tf)
        if not cons:
            continue
        for _ in range(copies):
            at = min(len(edited), 25 + n * (len(cons) + 10))
            edited = edited[:at] + cons + edited[at:]
            n += 1
    return edited[:500]


_TOOL = {
    "name": "apply_and_rescore",
    "description": (
        "Apply a grounded motif edit to the CURRENT design and re-score it with the frozen activity "
        "gate. Disrupts the named off-target driver TF sites and installs consensus copies of the named "
        "target driver TFs, then returns the new predicted specificity gap and most-active cell."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "disrupt_off_target_tfs": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Driver TF names of the predicted OFF-target cell to disrupt.",
            },
            "install_target_tfs": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Driver TF names of the TARGET cell to install.",
            },
            "copies_per_tf": {
                "type": "integer",
                "description": "Consensus copies per installed TF (1-3).",
            },
        },
        "required": ["disrupt_off_target_tfs", "install_target_tfs", "copies_per_tf"],
    },
}


def claude_rescue(
    seq: str,
    target: str,
    max_rounds: int = 4,
    verbose: bool = False,
    score_fn=None,
    client=None,
) -> dict:
    """Claude (Opus) tool-using loop that rescues a failing design using the gate as a tool.
    score_fn(seq, target) -> {gap, most_active, fail}; defaults to the deployed-API scorer.
    client: an anthropic client; created from ANTHROPIC_API_KEY if not given.
    Both are injectable so the SAME loop runs server-side (local gate) or from the CLI (deployed API)."""
    _score = score_fn or score
    if client is None:
        import anthropic

        client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    cur = seq
    rpt = _score(cur, target)
    off = rpt["most_active"]
    history = [
        {"round": 0, "gap": rpt["gap"], "most_active": off, "passed": not rpt["fail"]}
    ]
    if not rpt["fail"]:
        return {
            "passed": True,
            "final_gap": rpt["gap"],
            "rounds": 0,
            "history": history,
            "final_seq": cur,
            "start_gap": rpt["gap"],
        }
    off_drivers = motifs.DRIVERS.get(off, [])
    tgt_drivers = motifs.DRIVERS.get(target, [])
    sys_prompt = (
        "You are a cis-regulatory design-rescue agent. An AI-designed enhancer meant to be specific to "
        f"{target} is predicted most-active in {off} instead, so it FAILS (the specificity gap must be > 0 "
        "to pass). Iteratively edit it so the frozen activity model predicts it most-active in its target. "
        f"You may ONLY disrupt the off-target cell's real driver TFs ({', '.join(off_drivers) or 'none'}) and "
        f"install the target cell's real driver TFs ({', '.join(tgt_drivers) or 'none'}); you cannot invent "
        "sequence. Call apply_and_rescore, read the new gap, and iterate. Stop the moment the gap is positive "
        "(PASS), or abort if an edit does not improve the gap. Be efficient; prefer the smallest edit that works."
    )
    messages = [
        {
            "role": "user",
            "content": (
                f"Current design: predicted specificity gap {rpt['gap']} (negative = failing), most-active {off}, "
                f"target {target}. Rescue it to a positive gap."
            ),
        }
    ]
    passed = False
    for rnd in range(1, max_rounds + 1):
        resp = client.messages.create(
            model=OPTIMIZER_MODEL,
            max_tokens=2000,
            system=sys_prompt,
            tools=[_TOOL],
            messages=messages,
        )
        messages.append({"role": "assistant", "content": resp.content})
        tu = next(
            (b for b in resp.content if getattr(b, "type", None) == "tool_use"), None
        )
        if tu is None:
            break  # Claude stopped / aborted
        edited = apply_edit(
            cur,
            off,
            target,
            tu.input.get("disrupt_off_target_tfs", []),
            tu.input.get("install_target_tfs", []),
            tu.input.get("copies_per_tf", 2),
        )
        rpt = _score(edited, target)
        cur = edited
        passed = not rpt["fail"]
        history.append(
            {
                "round": rnd,
                "gap": rpt["gap"],
                "most_active": rpt["most_active"],
                "passed": passed,
            }
        )
        if verbose:
            print(
                f"  round {rnd}: gap {rpt['gap']}, most-active {rpt['most_active']}, {'PASS' if passed else 'fail'}"
            )
        messages.append(
            {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": tu.id,
                        "content": f"After the edit: specificity gap {rpt['gap']}, most-active {rpt['most_active']}, "
                        f"{'PASS (gap > 0)' if passed else 'still failing (gap <= 0)'}.",
                    }
                ],
            }
        )
        if passed:
            break
    return {
        "passed": passed,
        "final_gap": rpt["gap"],
        "rounds": len(history) - 1,
        "history": history,
        "final_seq": cur,
        "start_gap": history[0]["gap"],
    }


def deterministic_rescue(seq: str, target: str) -> dict:
    """The single fixed deterministic edit (the current /api/redesign), as the baseline."""
    d = _post(REDESIGN_URL, {"sequence": seq, "target_cell": target})
    return {
        "passed": bool(d.get("fixed")),
        "final_gap": d.get("after", {}).get("predicted_specificity_gap"),
        "start_gap": d.get("before", {}).get("predicted_specificity_gap"),
    }


if __name__ == "__main__":
    args = sys.argv[1:]
    if "--demo" in args:
        ex = (
            _post(BASE + "/api/example", {})
            if False
            else json.loads(
                urllib.request.urlopen(
                    urllib.request.Request(BASE + "/api/example", headers=UA)
                ).read()
            )
        )
        seq, tgt = ex["sequence"], ex.get("target_cell", "HepG2")
        print(f"Rescuing the flagship design (target {tgt}, {len(seq)}bp)...")
        r = claude_rescue(seq, tgt, verbose=True)
        print(
            json.dumps(
                {
                    k: r[k]
                    for k in ("passed", "start_gap", "final_gap", "rounds", "history")
                },
                indent=2,
            )
        )
    else:
        print(__doc__)
