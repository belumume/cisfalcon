"""CisFalcon web backend — the deployed tool a bench scientist uses to check an
AI-designed enhancer BEFORE synthesis.

Wraps the verified gate (gate.py, ensembled atlas activity model) and the parallel
Claude agent layer (verifier.py) behind a small API, and serves the frontend.

Endpoints:
  GET  /api/health                 - liveness + model warm state
  GET  /api/meta                   - cell panel, verified headline numbers, screenaudit
  POST /api/predict   {sequence,target_cell}            - fast deterministic gate verdict (no API)
  POST /api/diagnose  {sequence,target_cell}            - gate + parallel Claude agents + motif redesign
  POST /api/batch     {sequences:[...],target_cell}     - triage ranking (safest-first) + failure-drop
  GET  /api/example                - a real caught cross-lab failure (for the demo)
"""

from __future__ import annotations
import os, sys, re, json, time, pathlib, threading
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

# make the verified cisfalcon package importable (gate.py, verifier.py live one dir up x2)
CISFALCON = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(CISFALCON))
import gate  # noqa: E402
import verifier  # noqa: E402
import motifs  # noqa: E402  (JASPAR-grounded motif scan of the input sequence)

FRONTEND = pathlib.Path(__file__).resolve().parent / "static"
SCREENAUDIT_JSON = CISFALCON / "screenaudit" / "screenaudit_result.json"

# verified headline numbers (independently re-derived from raw scored data 2026-07-10)
HEADLINE = {
    "crosslab_auroc": 0.8013,
    "crosslab_n": 93435,
    "base_fail_rate": 0.0629,
    "safest_half_fail_rate": 0.0191,
    # POOLED. Kept under its original key so any existing caller keeps working, but a machine
    # consumer reading only this number gets the same unconditioned figure every human-readable
    # surface has already been corrected away from, so the conditioned pair travels with it.
    # Conditioning does not propagate: an API field inherits none of the caveats on the page.
    "failure_reduction_pct": 70,
    "failure_reduction_pct_basis": "pooled across cells and generators",
    "failure_reduction_pct_conditioned": 41,
    "failure_reduction_pct_conditioned_basis": "macro-average within (cell x generator), 14 strata",
    # Tie-break dependent, so it travels with its spread rather than as a point estimate. Every
    # design inside a stratum ties on the prior (the prior IS the score), so the safer half is
    # decided by the shuffle: 90.3 to 90.7 across 12 seeds of the repo's own pandas sample, mean
    # 90.5. The 91 this used to report was seed 0 formatted to zero decimals, i.e. the top of the
    # range rounding up. A sweep keyed on "91%" missed this because the field is a bare number.
    "sequence_free_stratum_prior_null_pct": 90.5,
    "sequence_free_stratum_prior_null_range_pct": [90.3, 90.7],
    "sequence_free_stratum_prior_null_basis": (
        "pooled; tie-break dependent, range over 12 seeds (triage_conditioning_check.py)"
    ),
    "null_note": (
        "A rule using the stratum prior and NO sequence scores about 90% pooled, which beats the "
        "pooled 70%. The pooled figure therefore is not evidence of per-sequence skill; the "
        "41% conditioned figure is. See triage_conditioning_check.py and PREREG-ERRATA.md."
    ),
    "riskiest10_ppv": 0.27,
    "source": "93,435 independent designs (Gosai/Tewhey 2024; BODA/Malinois; zero sequence overlap)",
}

# /docs and /redoc are off. They were reachable but unlinked, so the only visitor who found the
# Swagger UI was one poking at the URL space, and what they got was a Try-it-out button wired
# straight into the internal API surface. The API is documented in the repository instead; this
# is an MIT-licensed open-source project, so nothing here is hidden, it is just not a front door.
app = FastAPI(
    title="CisFalcon",
    version="1.0",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,  # docs_url/redoc_url alone leave the raw schema served at /openapi.json
)
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)

# --- lightweight cost guard for the Claude agent layer (protects the demo credits) ---
_DIAGNOSE_LOCK = threading.Lock()
_DIAGNOSE_CALLS: list[float] = []
_DIAGNOSE_MAX_PER_HOUR = int(os.environ.get("CISFALCON_DIAGNOSE_CAP", "120"))

_verifier_agents: Optional[verifier.CisFalconVerifier] = None
_verifier_rule = verifier.CisFalconVerifier(use_agents=False)
_warm = {"models": False}


# A key being SET is not the same as a call SUCCEEDING, and conflating the two is what put a
# 500 on the two buttons the README tells readers to click: the key was present and valid, the
# account had no credit balance, so /api/health advertised agents:true, the frontend rendered the
# buttons, and every click raised. The graceful fallback existed but was gated on the key being
# ABSENT, so it could never fire for a failing call. Track the failure and let the same fallback
# carry it.
_agents_degraded: dict[str, object] = {"reason": None, "since": None}


def _mark_agents_degraded(exc: Exception) -> None:
    msg = str(exc)
    if "credit balance" in msg.lower():
        reason = "the Anthropic account backing this deployment is out of credit"
    elif "authentication" in msg.lower() or "401" in msg:
        reason = "the Anthropic API key is not accepted"
    elif "rate" in msg.lower() and "limit" in msg.lower():
        reason = "the Anthropic API is rate limiting this deployment"
    else:
        reason = f"the Anthropic API call failed: {type(exc).__name__}"
    _agents_degraded["reason"] = reason
    _agents_degraded["since"] = time.time()


def _agents_configured() -> bool:
    """Is a key present? Configuration only. Says nothing about whether a call works."""
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def _agents_available() -> bool:
    """Can the agent layer actually serve a request right now?"""
    return _agents_configured() and _agents_degraded["reason"] is None


def _get_agent_verifier() -> verifier.CisFalconVerifier:
    global _verifier_agents
    if _verifier_agents is None:
        _verifier_agents = verifier.CisFalconVerifier(use_agents=True)
    return _verifier_agents


_DNA = re.compile(r"^[ACGTUNacgtun]+$")


def _strip_fasta(seq: str) -> str:
    """Drop FASTA header line(s) BEFORE collapsing whitespace, so a pasted
    `>header\nACGT...` record works (stripping whitespace first would delete the
    newline that separates header from sequence). Also handles line-wrapped FASTA."""
    lines = [ln for ln in (seq or "").splitlines() if not ln.lstrip().startswith(">")]
    return re.sub(r"\s+", "", "\n".join(lines))


def _clean_seq(seq: str) -> str:
    seq = _strip_fasta(seq)
    if not seq:
        raise HTTPException(400, "empty sequence")
    if len(seq) < 50:
        raise HTTPException(400, "sequence too short (need >= 50 bp)")
    if len(seq) > 5000:
        raise HTTPException(400, "sequence too long (max 5000 bp)")
    if not _DNA.match(seq):
        raise HTTPException(400, "sequence must be DNA (A/C/G/T/N)")
    return seq.upper().replace("U", "T")


def _check_target(cell: str) -> str:
    if cell not in gate.TARGET_CELLS:
        raise HTTPException(400, f"target_cell must be one of {gate.TARGET_CELLS}")
    return cell


class PredictReq(BaseModel):
    sequence: str
    target_cell: str = Field(
        ..., description="one of the 10 target-eligible cell lines"
    )


class BatchReq(BaseModel):
    sequences: list[str]
    target_cell: str


@app.on_event("startup")
def _warm_models():
    def go():
        try:
            gate.score_sequences(["ACGT" * 60])  # force model load once
            _warm["models"] = True
        except Exception as e:  # pragma: no cover
            print("warm failed:", e, flush=True)

    threading.Thread(target=go, daemon=True).start()


@app.get("/api/health")
def health():
    return {
        "ok": True,
        "models_warm": _warm["models"],
        # `agents` answers "can it serve a request", which is what the frontend needs in order to
        # decide whether to offer the buttons. `agents_configured` answers the separate and much
        # weaker question "is a key present". Reporting only the second is what advertised a
        # capability that raised on every click.
        "agents": _agents_available(),
        "agents_configured": _agents_configured(),
        "agents_degraded_reason": _agents_degraded["reason"],
    }


@app.get("/api/meta")
def meta():
    sa = None
    if SCREENAUDIT_JSON.exists():
        sa = json.loads(SCREENAUDIT_JSON.read_text())
    return {
        "target_cells": gate.TARGET_CELLS,
        "all_cells": gate.MPRA_CELL_LINES,
        "headline": HEADLINE,
        "screenaudit": sa,
        "agents_enabled": _agents_available(),
    }


@app.post("/api/predict")
def predict(req: PredictReq):
    seq = _clean_seq(req.sequence)
    cell = _check_target(req.target_cell)
    t0 = time.time()
    report = verifier.gate_report(seq, cell, _verifier_rule.calib)
    report["rule_verdict"] = verifier._rule_verdict(report)
    report["ms"] = int((time.time() - t0) * 1000)
    report["seq_len"] = len(seq)
    return report


def _rate_ok() -> bool:
    now = time.time()
    with _DIAGNOSE_LOCK:
        while _DIAGNOSE_CALLS and now - _DIAGNOSE_CALLS[0] > 3600:
            _DIAGNOSE_CALLS.pop(0)
        if len(_DIAGNOSE_CALLS) >= _DIAGNOSE_MAX_PER_HOUR:
            return False
        _DIAGNOSE_CALLS.append(now)
        return True


def _scan_summary(scan: Optional[dict]) -> str:
    if not scan:
        return ""
    lines = []
    for cell, d in scan.get("by_cell", {}).items():
        if d["tfs"]:
            tfs = ", ".join(
                f"{tf} ({v['n_sites']} sites, JASPAR {v['matrix_id']})"
                for tf, v in d["tfs"].items()
            )
            lines.append(
                f"{cell} driver motifs actually present in the sequence: {tfs}"
            )
        else:
            lines.append(f"{cell} driver motifs present in the sequence: NONE")
    return (
        "GROUNDED MOTIF SCAN (JASPAR log-odds PWM scan of the actual sequence):\n"
        + "\n".join(lines)
    )


def _motif_redesign(
    client, report: dict, scan: Optional[dict] = None
) -> Optional[dict]:
    """Focused agent: name the driver TF motif families for the predicted winning
    off-target cell vs the intended target, and the concrete redesign, GROUNDED in the
    real JASPAR motif scan of the sequence. The actionable diagnosis a bare classifier
    and a generic AI reviewer cannot give."""
    schema = {
        "type": "object",
        "properties": {
            "off_target_cell": {"type": "string"},
            "off_target_drivers": {"type": "array", "items": {"type": "string"}},
            "target_drivers_to_add": {"type": "array", "items": {"type": "string"}},
            "redesign": {"type": "string"},
        },
        "required": ["off_target_drivers", "target_drivers_to_add", "redesign"],
    }
    scan_txt = _scan_summary(scan)
    user = (
        f"An AI-designed enhancer intended to be specific to {report['target_cell']} is predicted "
        f"most-active in {report['predicted_most_active_cell']} instead (specificity gap "
        f"{report['predicted_specificity_gap']}). Per-cell predicted activity (log2FC): "
        f"{json.dumps(report['predicted_profile_log2fc'])}.\n\n{scan_txt}\n\n"
        f"Using the grounded motif scan above as evidence, name the transcription-factor motifs "
        f"that drive the predicted off-target cell ({report['predicted_most_active_cell']}) and "
        f"should be REMOVED (prefer motifs the scan confirms are present), the TF motifs that drive "
        f"{report['target_cell']} specificity and should be ADDED (prefer ones the scan shows are "
        f"absent), and a one-sentence concrete redesign. Cite the scanned evidence; use real TF names."
    )
    try:
        return verifier._agent(
            client,
            verifier.LENS_MODEL,
            "You are a cis-regulatory design expert. Ground every claim in the provided JASPAR "
            "motif scan. Give a precise, mechanistic, actionable motif-level redesign. No hedging.",
            user,
            schema=schema,
        )
    except Exception:
        return None


@app.post("/api/diagnose")
def diagnose(req: PredictReq):
    seq = _clean_seq(req.sequence)
    cell = _check_target(req.target_cell)
    if not _agents_available():
        # graceful fallback: deterministic gate + rule verdict, agents disabled
        out = _verifier_rule.verify(seq, cell)
        out["agents"] = False
        return out
    if not _rate_ok():
        raise HTTPException(
            429, "diagnosis rate limit reached; try the fast gate check"
        )
    t0 = time.time()
    try:
        v = _get_agent_verifier()
        out = v.verify(seq, cell)
    # Deliberately broad: the contract is that NO upstream failure reaches the user as a 500.
    # Narrowing this to known Anthropic exception types would reintroduce the defect for every
    # failure mode not yet seen, which is the one class that matters here.
    except Exception as exc:
        _mark_agents_degraded(exc)
        out = _verifier_rule.verify(seq, cell)
        out["agents"] = False
        out["agents_note"] = (
            f"Agent layer unavailable: {_agents_degraded['reason']}. "
            "This is the deterministic gate verdict, which needs no API and is what every "
            "published number in this repo is computed from."
        )
        return out
    out["agents"] = True
    # when the gate predicts a problem, add JASPAR-grounded motif evidence + a grounded redesign
    if out["gate"]["predicted_fail"] or out["gate"]["predicted_specificity_gap"] < 0.5:
        scan = motifs.scan_sequence(
            seq, cell, off_target_cell=out["gate"]["predicted_most_active_cell"]
        )
        out["motif_scan"] = scan
        redesign = _motif_redesign(v._client, out["gate"], scan=scan)
        if redesign:
            out["redesign"] = redesign
    out["ms"] = int((time.time() - t0) * 1000)
    return out


@app.post("/api/motifs")
def motif_scan(req: PredictReq):
    """JASPAR-grounded motif scan of the sequence for the target + predicted off-target
    cell (fast, no Claude API). Verifiable evidence for the diagnosis."""
    seq = _clean_seq(req.sequence)
    cell = _check_target(req.target_cell)
    report = verifier.gate_report(seq, cell, _verifier_rule.calib)
    scan = motifs.scan_sequence(
        seq, cell, off_target_cell=report["predicted_most_active_cell"]
    )
    scan["predicted_most_active_cell"] = report["predicted_most_active_cell"]
    scan["predicted_specificity_gap"] = report["predicted_specificity_gap"]
    return scan


@app.post("/api/redesign")
def redesign(req: PredictReq):
    """CLOSED LOOP: take a failing design, apply the mechanistic motif edit the diagnosis
    prescribes (disrupt the driver motifs of the predicted off-target cell, inject the
    missing target-cell driver motifs), and RE-SCORE with the same gate. This is an
    IN-SILICO SELF-CONSISTENCY check on one example, NOT wet-lab validation: the same model
    that flagged the design re-scores its own proposed edit. The predicted specificity gap
    moving in the right direction shows the diagnosis names a specific, mechanistically
    grounded edit that the model responds to sensibly; it is not proof the redesign works
    in cells."""
    seq = _clean_seq(req.sequence)
    cell = _check_target(req.target_cell)
    before = verifier.gate_report(seq, cell, _verifier_rule.calib)
    off = before["predicted_most_active_cell"]

    edits = []
    edited = list(seq)
    # 1. disrupt the strongest off-target driver-motif sites (break the erroneous grammar)
    for site in motifs.driver_sites(seq, off, top=5):
        p, L = site["pos"], site["length"]
        if p + L <= len(edited):
            filler = ("GAATTC" * (L // 6 + 1))[:L]  # neutral, non-driver filler
            edited[p : p + L] = list(filler)
            edits.append(
                {"action": "disrupt", "tf": site["tf"], "cell": off, "pos": int(p)}
            )
    edited = "".join(edited)

    # 2. install the missing target-cell driver motifs (two copies each, target-specific first)
    scan = motifs.scan_sequence(seq, cell, off)
    present = set(scan["by_cell"].get(cell, {}).get("tfs", {}).keys())
    off_tfs = set(motifs.DRIVERS.get(off, []))
    n_inj = 0
    for tf in motifs.DRIVERS.get(cell, []):
        if (
            tf in present or tf in off_tfs
        ):  # skip already-present and shared-with-off-target TFs
            continue
        cons = motifs.consensus_seq(tf)
        if not cons:
            continue
        for _copy in range(
            2
        ):  # two copies to reliably raise target activity above off-targets
            at = min(len(edited), 25 + n_inj * (len(cons) + 10))
            edited = edited[:at] + cons + edited[at:]
            edits.append(
                {"action": "add", "tf": tf, "cell": cell, "motif": cons, "pos": int(at)}
            )
            n_inj += 1
        if n_inj >= 6:
            break
    edited = edited[:500]

    after = verifier.gate_report(edited, cell, _verifier_rule.calib)
    return {
        "before": {
            k: before[k]
            for k in (
                "predicted_most_active_cell",
                "predicted_specificity_gap",
                "predicted_fail",
                "calibrated_fail_probability",
            )
        },
        "after": {
            k: after[k]
            for k in (
                "predicted_most_active_cell",
                "predicted_specificity_gap",
                "predicted_fail",
                "calibrated_fail_probability",
            )
        },
        "gap_delta": round(
            after["predicted_specificity_gap"] - before["predicted_specificity_gap"], 3
        ),
        "fixed": bool(before["predicted_fail"] and not after["predicted_fail"]),
        "edits": edits,
        "edited_sequence": edited,
    }


@app.post("/api/rescue")
def rescue(req: PredictReq):
    """CLAUDE CLOSED-LOOP OPTIMIZER: Claude (Opus) rescues a failing design by ITERATING grounded motif
    edits, calling the frozen gate as a tool to re-score after each round. This is a capability the gate
    alone does not have (it scores, it does not optimize). Powered, equal-budget comparison
    (closed_loop_powered.py, n=97): the adaptive agent rescues 26.8% vs a fixed greedy rule's 24.7%
    (delta +2.1pp, 95% CI includes zero), so it does NOT beat a fixed rule at equal budget; the value is
    the live agentic tool-use loop itself. In-silico consistency (the same frozen gate agrees the rescue
    passes), NOT wet-lab. Bounded to 4 rounds to fit the request timeout."""
    seq = _clean_seq(req.sequence)
    cell = _check_target(req.target_cell)
    if not _agents_available():
        # The old text asserted the key was unset, which is the wrong diagnosis whenever the key
        # is present and the call is what failed. Report the reason actually observed.
        why = _agents_degraded["reason"] or "ANTHROPIC_API_KEY is not set"
        raise HTTPException(503, f"Claude rescue needs the agent layer: {why}")
    if not _rate_ok():
        raise HTTPException(429, "rescue rate limit reached; try again shortly")
    import closed_loop

    v = _get_agent_verifier()

    def _local_score(s, t):
        r = verifier.gate_report(s, t, _verifier_rule.calib)
        return {
            "gap": round(float(r["predicted_specificity_gap"]), 3),
            "most_active": r["predicted_most_active_cell"],
            "fail": bool(r["predicted_fail"]),
        }

    t0 = time.time()
    try:
        out = closed_loop.claude_rescue(
            seq, cell, max_rounds=4, score_fn=_local_score, client=v._client
        )
    # Same contract as /api/diagnose: an upstream failure becomes an honest 503, never a 500.
    except Exception as exc:
        _mark_agents_degraded(exc)
        raise HTTPException(
            503, f"Claude rescue is unavailable: {_agents_degraded['reason']}"
        ) from exc
    out["ms"] = int((time.time() - t0) * 1000)
    return out


MAX_BATCH = (
    64  # scores well within the request timeout on shared-cpu-8x; larger = split
)


@app.post("/api/batch")
def batch(req: BatchReq):
    cell = _check_target(req.target_cell)
    if len(req.sequences) > MAX_BATCH:
        raise HTTPException(
            400,
            f"batch too large ({len(req.sequences)} designs); max {MAX_BATCH} per "
            f"request so each check stays fast. Split into smaller batches.",
        )
    seqs = []
    for s in req.sequences:
        s2 = _strip_fasta(s)
        if s2 and _DNA.match(s2) and 50 <= len(s2) <= 5000:
            seqs.append(s2.upper().replace("U", "T"))
    if not seqs:
        raise HTTPException(400, "no valid DNA sequences (need 50-5000 bp each)")
    verdicts = gate.verdict(seqs, cell)
    ranked = sorted(enumerate(verdicts), key=lambda t: -t[1]["predicted_gap"])
    n = len(ranked)
    order = [
        {
            "rank": i + 1,
            "input_index": idx,
            "predicted_gap": round(v["predicted_gap"], 3),
            "predicted_most_active_cell": v["most_active_cell"],
            "predicted_fail": v["predicted_fail"],
            "low_activity": v.get("low_activity", False),
            "low_complexity": v.get("low_complexity", False),
        }
        for i, (idx, v) in enumerate(ranked)
    ]
    n_fail = sum(1 for v in verdicts if v["predicted_fail"])
    n_low = sum(1 for v in verdicts if v.get("low_activity"))
    n_low_cplx = sum(1 for v in verdicts if v.get("low_complexity"))
    half = ranked[: max(1, n // 2)]
    half_fail = sum(1 for _, v in half if v["predicted_fail"]) / len(half)
    overall_fail = n_fail / n
    reduction = round(100 * (1 - half_fail / overall_fail)) if overall_fail > 0 else 0
    return {
        "n": n,
        "target_cell": cell,
        "predicted_fail_count": n_fail,
        "low_activity_count": n_low,
        "low_complexity_count": n_low_cplx,
        "predicted_fail_rate": round(overall_fail, 4),
        "safest_half_fail_rate": round(half_fail, 4),
        "failure_reduction_pct_safest_half": reduction,
        "ranking": order,
    }


@app.get("/api/example")
def example():
    """A real cross-lab caught failure (the demo hero): a Gosai/Malinois design optimized
    for HepG2 that fires in K562. Sequence + the measured wet-lab truth."""
    hero = CISFALCON / "data" / "gosai_designed" / "hero.json"
    if hero.exists():
        return json.loads(hero.read_text())
    return {
        "id": "20211213_141901__715602__47::hmc__hepg2__0",
        "target_cell": "HepG2",
        "measured": {"HepG2": -0.1, "K562": 6.5, "SKNSH": -0.4},
        "note": "A real BODA/Malinois design optimized for HepG2 specificity. Measured: barely touches HepG2, fires ~90x (log2FC 6.5) in K562.",
    }


@app.get("/api/example-brain")
def example_brain():
    """A real brain-cell (SKNSH neuroblastoma) failure: a Gosai/Malinois design optimized
    for the brain-derived SKNSH line that instead fires in K562. Grounds the Gladstone
    brain-disease angle in a live, shown example, not just the cross-lab 0.73 number."""
    hero = CISFALCON / "data" / "gosai_designed" / "brain_hero.json"
    if hero.exists():
        return json.loads(hero.read_text())
    return {
        "id": "20211213_142237__606687__146::hmc__sknsh__0",
        "target_cell": "SKNSH",
        "measured": {"K562": 5.75, "HepG2": 0.79, "SKNSH": 0.53},
        "note": "A real design optimized for the brain-derived SKNSH line; measured, it fires in K562, not its brain target.",
    }


@app.get("/api/example-batch")
def example_batch():
    """A real mixed batch of HepG2-targeted designs (measured pass + fail) so the triage
    ranking demonstrates the actual failure-rate reduction, not a degenerate all-fail set."""
    f = CISFALCON / "data" / "gosai_designed" / "batch_example.json"
    designs = json.loads(f.read_text()) if f.exists() else []
    return {"target_cell": "HepG2", "sequences": [d["seq"] for d in designs]}


# --- serve the frontend at the root; API stays under /api ---
if (FRONTEND / "assets").is_dir():
    app.mount("/assets", StaticFiles(directory=str(FRONTEND / "assets")), name="assets")

if FRONTEND.exists():
    # No-store so a redeploy is never masked by a browser's cached HTML/JS/CSS.
    # The frontend is tiny; correctness (always the current code) beats micro-caching.
    _NOCACHE = {"Cache-Control": "no-store, max-age=0"}

    @app.get("/")
    def index():
        return FileResponse(str(FRONTEND / "index.html"), headers=_NOCACHE)

    @app.get("/{path:path}")
    def spa(path: str):
        # The catch-all used to swallow the /api/ prefix too, so a mistyped endpoint returned
        # HTTP 200 with 47KB of index.html. A scripted consumer read that as success and then
        # failed opaquely on an HTML body. Unknown /api routes get a real JSON 404; only
        # non-API paths fall through to the SPA, which is what a client router actually needs.
        if path == "api" or path.startswith("api/"):
            return JSONResponse(
                {"detail": f"no such API endpoint: /{path}"},
                status_code=404,
                headers=_NOCACHE,
            )
        f = (FRONTEND / path).resolve()
        if str(f).startswith(str(FRONTEND.resolve())) and f.is_file():
            return FileResponse(str(f), headers=_NOCACHE)
        return FileResponse(str(FRONTEND / "index.html"), headers=_NOCACHE)
