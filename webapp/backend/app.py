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
from fastapi.responses import FileResponse
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
    "failure_reduction_pct": 70,
    "riskiest10_ppv": 0.27,
    "source": "93,435 independent designs (Gosai/Tewhey 2024; BODA/Malinois; zero sequence overlap)",
}

app = FastAPI(title="CisFalcon", version="1.0")
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


def _agents_available() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


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
        "agents": _agents_available(),
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
    v = _get_agent_verifier()
    out = v.verify(seq, cell)
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
        }
        for i, (idx, v) in enumerate(ranked)
    ]
    n_fail = sum(1 for v in verdicts if v["predicted_fail"])
    half = ranked[: max(1, n // 2)]
    half_fail = sum(1 for _, v in half if v["predicted_fail"]) / len(half)
    overall_fail = n_fail / n
    reduction = round(100 * (1 - half_fail / overall_fail)) if overall_fail > 0 else 0
    return {
        "n": n,
        "target_cell": cell,
        "predicted_fail_count": n_fail,
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
        "note": "A real BODA/Malinois design optimized for HepG2 specificity. Measured: barely touches HepG2, fires 6.5-fold in K562.",
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

    @app.get("/")
    def index():
        return FileResponse(str(FRONTEND / "index.html"))

    @app.get("/{path:path}")
    def spa(path: str):
        f = (FRONTEND / path).resolve()
        if str(f).startswith(str(FRONTEND.resolve())) and f.is_file():
            return FileResponse(str(f))
        return FileResponse(str(FRONTEND / "index.html"))
