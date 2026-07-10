"""Ground the motif-level diagnosis in REAL transcription-factor binding models.

The agent layer names which TF motifs drive the predicted off-target cell. On its own
that is Claude's knowledge. Here we VERIFY it against the actual sequence: we pull real
position weight matrices from JASPAR (the standard TF-motif database) for a curated set
of cell-type-driver TFs, scan the designed enhancer with a log-odds PWM scan (FIMO-style,
both strands), and report which driver motifs are actually PRESENT and where. This turns
"Claude says GATA1 drives K562" into "the sequence contains 3 GATA1 (JASPAR MA0035) sites
scoring >= 85% of max" - a verifiable, database-grounded claim.

This is the same "verifier grounded in external measured ground truth" principle CisFalcon
applies to the activity model, applied one layer deeper to the motif diagnosis. (It is the
capability Claude Science's Regulation connector exposes; we call the primary source directly.)
"""

from __future__ import annotations
import json, math, pathlib, urllib.request, urllib.parse
import numpy as np

_CACHE = pathlib.Path(__file__).resolve().parent / "jaspar_cache"
_CACHE.mkdir(exist_ok=True)
_UA = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126.0"
}
_JASPAR = "https://jaspar.elixir.no/api/v1"

# curated cell-type-driver TFs for the CisFalcon cell panel (TF name -> the cell line it drives).
# These are canonical lineage-defining regulators; JASPAR resolves the latest CORE vertebrate PWM.
DRIVERS: dict[str, list[str]] = {
    "K562": ["GATA1", "TAL1", "KLF1", "GATA2", "NFE2"],  # erythroleukemia
    "HepG2": [
        "HNF4A",
        "CEBPA",
        "HNF1A",
        "FOXA2",
        "FOXA1",
    ],  # hepatocyte (specific-first)
    "SKNSH": ["GATA3", "PHOX2B", "HAND2", "ISL1", "TFAP2A"],  # neuroblastoma / neuronal
    "SJCRH30": ["MYOD1", "MYOG", "PAX3", "MYF5"],  # rhabdomyosarcoma / muscle
    "MCF7": ["ESR1", "GATA3", "FOXA1", "SPDEF"],  # breast (ER+)
    "GM12878": ["SPI1", "EBF1", "PAX5", "IRF4"],  # lymphoblastoid / B-cell
    "NT2_D1": ["POU5F1", "SOX2", "NANOG"],  # embryonal carcinoma / pluripotent
    "WERI_Rb1": ["CRX", "OTX2", "NRL"],  # retinoblastoma / photoreceptor
    "HEK293": ["SP1", "YY1"],  # embryonic kidney (broad)
    "HeLaS3": ["SP1", "AP1", "NFYA"],  # cervical (broad)
    "786_O": ["HIF1A", "EPAS1", "SP1"],  # renal
    "HMC3": ["SPI1", "IRF8", "CEBPB"],  # microglia / myeloid
}
_TF_TO_CELL = {tf: cell for cell, tfs in DRIVERS.items() for tf in tfs}


def _http_json(url: str):
    req = urllib.request.Request(url, headers=_UA)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def _resolve_pwm(tf: str) -> dict | None:
    """Search JASPAR for the TF, take the top CORE vertebrate PFM, return log-odds matrix.
    Cached to disk so a deployed instance does not hit JASPAR per request."""
    cf = _CACHE / f"{tf}.json"
    if cf.exists():
        return json.loads(cf.read_text())
    try:
        q = urllib.parse.urlencode(
            {
                "search": tf,
                "collection": "CORE",
                "tax_group": "vertebrates",
                "page_size": 5,
            }
        )
        res = _http_json(f"{_JASPAR}/matrix/?{q}")
        mid = None
        for m in res.get("results", []):
            if m.get("name", "").upper() == tf.upper():
                mid = m["matrix_id"]
                break
        if mid is None and res.get("results"):
            mid = res["results"][0]["matrix_id"]
        if mid is None:
            return None
        full = _http_json(f"{_JASPAR}/matrix/{mid}/")
        pfm = full.get("pfm")  # {"A":[...],"C":[...],"G":[...],"T":[...]}
        if not pfm:
            return None
        mat = np.array([pfm["A"], pfm["C"], pfm["G"], pfm["T"]], dtype=float)  # (4, L)
        col = mat.sum(axis=0) + 1e-9
        prob = (mat + 0.25) / (col + 1.0)  # pseudocount
        logodds = np.log2(prob / 0.25)  # vs uniform background
        maxscore = float(logodds.max(axis=0).sum())
        minscore = float(logodds.min(axis=0).sum())
        out = {
            "tf": tf,
            "matrix_id": mid,
            "cell": _TF_TO_CELL.get(tf, "?"),
            "logodds": logodds.tolist(),
            "length": mat.shape[1],
            "maxscore": maxscore,
            "minscore": minscore,
        }
        cf.write_text(json.dumps(out))
        return out
    except Exception:
        return None


_B = {"A": 0, "C": 1, "G": 2, "T": 3}
_COMP = {"A": "T", "C": "G", "G": "C", "T": "A", "N": "N"}


def _revcomp(seq: str) -> str:
    return "".join(_COMP.get(b, "N") for b in reversed(seq))


def _scan_one(seq: str, pwm: dict, rel_thresh: float = 0.85) -> list[dict]:
    lo = np.array(pwm["logodds"])  # (4, L)
    L = pwm["length"]
    thr = pwm["minscore"] + rel_thresh * (pwm["maxscore"] - pwm["minscore"])
    hits = []
    for strand, s in (("+", seq), ("-", _revcomp(seq))):
        idx = [_B.get(b, -1) for b in s]
        for i in range(len(s) - L + 1):
            win = idx[i : i + L]
            if -1 in win:
                continue
            score = float(sum(lo[win[j], j] for j in range(L)))
            if score >= thr:
                pos = i if strand == "+" else len(s) - i - L
                hits.append(
                    {
                        "pos": pos,
                        "strand": strand,
                        "score": round(score, 2),
                        "rel": round(
                            (score - pwm["minscore"])
                            / (pwm["maxscore"] - pwm["minscore"]),
                            3,
                        ),
                    }
                )
    hits.sort(key=lambda h: -h["score"])
    return hits[:8]


def scan_sequence(
    seq: str, target_cell: str, off_target_cell: str | None = None
) -> dict:
    """Scan the designed enhancer for driver motifs of the target cell and (if given) the
    predicted off-target cell. Returns grounded, verifiable motif evidence."""
    seq = seq.upper().replace("U", "T")
    cells = [c for c in (off_target_cell, target_cell) if c and c in DRIVERS]
    if not cells:
        cells = [target_cell] if target_cell in DRIVERS else []
    result = {}
    for cell in dict.fromkeys(cells):  # dedupe, keep order
        tfs = {}
        for tf in DRIVERS.get(cell, []):
            pwm = _resolve_pwm(tf)
            if not pwm:
                continue
            hits = _scan_one(seq, pwm)
            if hits:
                tfs[tf] = {
                    "matrix_id": pwm["matrix_id"],
                    "n_sites": len(hits),
                    "top": hits[:3],
                }
        result[cell] = {
            "n_driver_tfs_present": len(tfs),
            "total_sites": sum(v["n_sites"] for v in tfs.values()),
            "tfs": tfs,
        }
    return {
        "target_cell": target_cell,
        "off_target_cell": off_target_cell,
        "by_cell": result,
        "source": "JASPAR CORE vertebrates (log-odds PWM scan, both strands, rel>=0.85)",
    }


def consensus_seq(tf: str) -> str | None:
    """The maximum-scoring DNA string for a TF's PWM (its consensus binding site)."""
    pwm = _resolve_pwm(tf)
    if not pwm:
        return None
    lo = np.array(pwm["logodds"])  # (4, L)
    bases = "ACGT"
    return "".join(bases[int(np.argmax(lo[:, j]))] for j in range(pwm["length"]))


def driver_sites(seq: str, cell: str, top: int = 3) -> list[dict]:
    """Top scoring driver-motif sites for a cell, with positions/length (for disruption)."""
    seq = seq.upper().replace("U", "T")
    sites = []
    for tf in DRIVERS.get(cell, []):
        pwm = _resolve_pwm(tf)
        if not pwm:
            continue
        for h in _scan_one(seq, pwm):
            sites.append(
                {
                    "tf": tf,
                    "matrix_id": pwm["matrix_id"],
                    "pos": h["pos"],
                    "strand": h["strand"],
                    "length": pwm["length"],
                    "score": h["score"],
                }
            )
    sites.sort(key=lambda s: -s["score"])
    return sites[:top]


if __name__ == "__main__":
    import sys, csv as _csv

    # self-test on the real hero failure (HepG2-designed, fires in K562)
    hero = "20211213_141901__715602__47::hmc__hepg2__0"
    seq = "ACGT" * 100
    bench = (
        pathlib.Path(__file__).resolve().parents[2]
        / "data"
        / "gosai_designed"
        / "designed_benchmark.csv"
    )
    if bench.exists():
        for row in _csv.DictReader(open(bench)):
            if row["id"] == hero:
                seq = row["sequence"]
                break
    out = scan_sequence(seq, "HepG2", "K562")
    print(json.dumps(out, indent=2)[:1500])
    for cell, d in out["by_cell"].items():
        print(
            f"{cell}: {d['n_driver_tfs_present']} driver TFs present, {d['total_sites']} sites -> {list(d['tfs'])}"
        )
