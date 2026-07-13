"""Calibrate a low-complexity/repeat floor for the CisFalcon gate.

The activity floor (calibrate_floor.py) catches sequences weakly active everywhere
(random noise). It does NOT catch degenerate/repetitive sequences (homopolymers like
poly-A, or short-period tandem repeats like ACGT-repeat) which can SPURIOUSLY over-
activate the CNN and clear the floor with a confident-looking verdict. A base-
composition entropy check catches poly-A but not a balanced tandem repeat (ACGT-repeat
has 25% of each base, so its base entropy is maximal). A k-mer DIVERSITY metric catches
both.

sequence_complexity(seq) = min over k in {2,3} of (distinct k-mers / max possible),
computed on the ACGT-filtered signal (non-ACGT maps to N=zero in the model, carrying no
signal). ~1.0 for real/random diverse sequences; near 0 for homopolymers and tandem
repeats. This calibrates the threshold on the 1000 real gosai designs so the real
false-flag rate is ~0, and confirms every degenerate case falls below it.
"""

import os, sys, csv, random

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np

random.seed(0)
np.random.seed(0)


def sequence_complexity(seq: str) -> float:
    """Low-complexity score in [0,1]: min over k in {2,3} of distinct-kmer fraction on
    the ACGT-filtered signal. Catches homopolymers AND balanced tandem repeats."""
    s = "".join(c for c in str(seq).upper() if c in "ACGT")
    L = len(s)
    if L < 6:
        return 0.0
    vals = []
    for k in (2, 3):
        kmers = {s[i : i + k] for i in range(L - k + 1)}
        maxk = min(4**k, L - k + 1)
        vals.append(len(kmers) / maxk)
    return float(min(vals))


BM = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "data",
    "gosai_designed",
    "designed_benchmark.csv",
)
N = 1000

real = []
with open(BM, newline="") as f:
    for row in csv.DictReader(f):
        s = row["sequence"].strip().upper()
        if set(s) <= set("ACGT") and 100 <= len(s) <= 500:
            real.append(s)
random.shuffle(real)
real = real[:N]
Lmed = int(np.median([len(s) for s in real]))
print(f"real designs: n={len(real)} median_len={Lmed}")


def rnd(n):
    return "".join(random.choice("ACGT") for _ in range(n))


randm = [rnd(len(s)) for s in real]

degenerate = {
    "poly-A x200": "A" * 200,
    "poly-N x200": "N" * 200,
    "ACGT x50 (period-4 tandem)": "ACGT" * 50,
    "RNA ACGU x50": "ACGU" * 50,
    "CA x100 (period-2)": "CA" * 100,
    "special/repeat": "ACGT123!@# ACGT\n\tACGT" * 10,
    "AT-repeat x100": "AT" * 100,
    "GGGGCCCC x25": "GGGGCCCC" * 25,
}

cr = np.array([sequence_complexity(s) for s in real])
cn = np.array([sequence_complexity(s) for s in randm])


def show(name, x):
    q = np.percentile(x, [0, 1, 5, 10, 25, 50])
    print(
        f"{name:22s} n={len(x)}  min/1/5/10/25/50 = " + " ".join(f"{v:.3f}" for v in q)
    )


print("\n=== sequence_complexity (min distinct-kmer frac, k in {2,3}) ===")
show("REAL designs", cr)
show("RANDOM (len-matched)", cn)
print("\ndegenerate cases:")
for name, s in degenerate.items():
    print(f"  {name:28s} complexity={sequence_complexity(s):.4f}")

print(
    "\n=== candidate thresholds: fraction flagged low_complexity (complexity < t) ==="
)
worst_degen = max(sequence_complexity(s) for s in degenerate.values())
for t in [0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40]:
    print(
        f"t={t:4.2f}: REAL flagged={(cr < t).mean():6.2%}  RANDOM flagged={(cn < t).mean():6.2%}  "
        f"degenerate all-below={all(sequence_complexity(s) < t for s in degenerate.values())}"
    )

# highest threshold with REAL false-flag == 0 AND all degenerate below it
cand = [round(x, 3) for x in np.arange(0.10, 0.501, 0.005)]
best = None
for t in cand:
    if (cr < t).mean() == 0.0 and all(
        sequence_complexity(s) < t for s in degenerate.values()
    ):
        best = t
print(f"\nworst (highest) degenerate complexity = {worst_degen:.4f}")
print(f"min REAL complexity = {cr.min():.4f}")
print(
    f"Suggested threshold (REAL false-flag == 0 AND all degenerate flagged, maximized): {best}"
)
