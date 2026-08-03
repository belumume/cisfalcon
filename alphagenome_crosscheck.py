"""Independent second-model cross-check: AlphaGenome vs CisFalcon.

CisFalcon ranks designed-enhancer specificity with the Castillo-Hair DHS64-MPRA activity
atlas (trained on measured MPRA activity). A fair question is whether the signal rests on
that one model family. This script cross-checks it against a model of a completely different
lineage: DeepMind's AlphaGenome (a genomic sequence-to-function model, never trained on any
MPRA), using its predicted chromatin ACCESSIBILITY (DNASE) rather than MPRA activity.

Method: for each designed enhancer, embed the 200 bp sequence centered in a 16,384 bp
N-padded window (AlphaGenome's minimum input length), predict DNASE in K562 / HepG2 / SK-N-SH,
take the mean predicted signal over the central design region per cell, and define the
specificity gap = target-cell signal - max(off-target signal). Then compare AlphaGenome's gap
to the wet-lab failure labels (AUROC) and to CisFalcon's own predicted gap (Spearman).

Honest caveats:
- This is a heavily OUT-OF-DISTRIBUTION use of AlphaGenome: a bare designed episomal enhancer
  in a 16 kb N-padded window is unlike the genomic context it was trained on. The number is a
  floor, not a ceiling, for what AlphaGenome could do with a purpose-built setup.
- Accessibility (DNASE) is a proxy for enhancer activity, not the MPRA readout itself.
- Reported on a stratified balanced subsample (N per (target_cell x fail) stratum), not the full set.

Result on 240 designs (balanced): AUROC 0.688 [95% CI 0.620, 0.752] vs the wet-lab failure
labels, and Spearman 0.80 (Pearson 0.82) agreement with CisFalcon's independent predicted gap.
Two independent-lineage models agreeing at 0.80 is evidence the specificity signal is not an
artifact of one model family. Committed scores: data/gosai_designed/alphagenome_crosscheck.json

Requires an AlphaGenome API key (free for non-commercial research:
deepmind.google.com/science/alphagenome). Set ALPHA_GENOME_API_KEY in the environment.
Run: ALPHA_GENOME_API_KEY=... python alphagenome_crosscheck.py
"""

import csv
import json
import os
import random
import sys
import time
from pathlib import Path

import numpy as np
from alphagenome.models import dna_client

KEY = os.environ["ALPHA_GENOME_API_KEY"]
LEN = 16384
ONT = {"K562": "EFO:0002067", "HepG2": "EFO:0001187", "SKNSH": "EFO:0003072"}
N_PER_STRATUM = 40
random.seed(1234)
HERE = Path(__file__).resolve().parent
BENCH = HERE / "data" / "gosai_designed" / "designed_benchmark.csv"
SCORED = HERE / "data" / "gosai_designed" / "designed_scored.csv"
# Never overwrite the committed evidence from a routine run. Same guard as
# closed_loop_powered.py and agent_ablation.py: a reproduce command must not be able to
# destroy the artifact it reproduces. --overwrite-committed opts in deliberately.
COMMITTED = HERE / "data" / "gosai_designed" / "alphagenome_crosscheck.json"
OUT = (
    COMMITTED
    if "--overwrite-committed" in sys.argv
    else HERE / "data" / "gosai_designed" / "alphagenome_crosscheck.local.json"
)


def load_sample():
    rows = []
    with BENCH.open() as f:
        for row in csv.DictReader(f):
            if row.get("target_cell") in ONT:
                rows.append(
                    (
                        row["id"],
                        row["sequence"],
                        row["target_cell"],
                        int(row["measured_fail"]),
                    )
                )
    from collections import defaultdict

    buckets = defaultdict(list)
    for r in rows:
        buckets[(r[2], r[3])].append(r)
    sample = []
    for v in buckets.values():
        random.shuffle(v)
        sample.extend(v[:N_PER_STRATUM])
    random.shuffle(sample)
    return sample


def load_cisfalcon_gaps():
    cf = {}
    if not SCORED.exists():
        return cf
    with SCORED.open() as f:
        rdr = csv.DictReader(f)
        col = next(
            (c for c in rdr.fieldnames if "pred" in c.lower() and "gap" in c.lower()),
            None,
        ) or next(
            (
                c
                for c in rdr.fieldnames
                if "gap" in c.lower() and "meas" not in c.lower()
            ),
            None,
        )
        for row in rdr:
            try:
                cf[row["id"]] = float(row[col])
            except Exception:
                pass
    return cf


def pad(seq):
    seq = seq.strip().upper()
    left = (LEN - len(seq)) // 2
    return "N" * left + seq + "N" * (LEN - len(seq) - left), left, left + len(seq)


def cell_signal(dnase, curie, c0, c1):
    meta = dnase.metadata
    cols = [i for i, oc in enumerate(meta["ontology_curie"]) if oc == curie]
    return float(np.nanmean(dnase.values[c0:c1, cols])) if cols else None


def auroc(score, label):
    from scipy.stats import rankdata

    s = -np.asarray(score)
    pos = label == 1
    neg = label == 0
    if pos.sum() == 0 or neg.sum() == 0:
        return float("nan")
    r = rankdata(s)
    return (r[pos].sum() - pos.sum() * (pos.sum() + 1) / 2) / (pos.sum() * neg.sum())


def main():
    model = dna_client.create(KEY)
    sample = load_sample()
    cf = load_cisfalcon_gaps()
    ag_gap, y, cf_gap, ids = [], [], [], []
    t0 = time.time()
    for i, (sid, seq, tc, fail) in enumerate(sample):
        padded, c0, c1 = pad(seq)
        try:
            out = model.predict_sequence(
                sequence=padded,
                organism=dna_client.Organism.HOMO_SAPIENS,
                requested_outputs=[dna_client.OutputType.DNASE],
                ontology_terms=list(ONT.values()),
            )
        except Exception as e:
            print(f"[{i}] {sid[:30]} ERR {str(e)[:70]}")
            time.sleep(2)
            continue
        sig = {c: cell_signal(out.dnase, ONT[c], c0, c1) for c in ONT}
        if any(v is None for v in sig.values()):
            continue
        off = max(v for c, v in sig.items() if c != tc)
        ag_gap.append(sig[tc] - off)
        y.append(fail)
        cf_gap.append(cf.get(sid, float("nan")))
        ids.append(sid)
        if (i + 1) % 20 == 0:
            print(
                f"[{i + 1}/{len(sample)}] scored={len(ag_gap)} elapsed={time.time() - t0:.0f}s"
            )

    ag = np.array(ag_gap)
    y = np.array(y)
    cfg = np.array(cf_gap)
    a = auroc(ag, y)
    rng = np.random.default_rng(7)
    idx = np.arange(len(y))
    boots = [
        auroc(ag[b], y[b])
        for b in (rng.choice(idx, len(idx), replace=True) for _ in range(2000))
    ]
    boots = [x for x in boots if x == x]
    lo, hi = np.percentile(boots, [2.5, 97.5])
    from scipy.stats import pearsonr, spearmanr

    m = ~np.isnan(cfg)
    rs = spearmanr(ag[m], cfg[m]).correlation if m.sum() > 5 else float("nan")
    rp = pearsonr(ag[m], cfg[m])[0] if m.sum() > 5 else float("nan")

    print(
        f"\nAlphaGenome DNASE gap vs wet-lab measured_fail: n={len(y)} base_fail={y.mean():.3f}"
    )
    print(f"AUROC={a:.4f}  95% CI [{lo:.4f}, {hi:.4f}]  (chance 0.50)")
    print(
        f"agreement with CisFalcon (independent lineages): Spearman={rs:.3f} Pearson={rp:.3f} (n={int(m.sum())})"
    )

    OUT.write_text(
        json.dumps(
            {
                "method": "AlphaGenome DNASE, 16kb N-padded, target - max(off-target) over K562/HepG2/SKNSH",
                "n": int(len(y)),
                "base_fail": float(y.mean()),
                "auroc": float(a),
                "auroc_ci95": [float(lo), float(hi)],
                "spearman_vs_cisfalcon": float(rs),
                "pearson_vs_cisfalcon": float(rp),
                "ids": ids,
                "ag_gap": [float(x) for x in ag],
                "y": [int(x) for x in y],
                "cf_gap": [None if x != x else float(x) for x in cfg],
            },
            indent=1,
        )
    )
    print(f"saved -> {OUT}")


if __name__ == "__main__":
    main()
