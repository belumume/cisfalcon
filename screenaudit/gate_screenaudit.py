"""ScreenAudit gate: the SAME verifier pattern as CisFalcon, applied to a DISJOINT
domain (published CRISPR screens instead of AI enhancers). Deterministic signal =
hit-call DISCORDANCE: how many of a screen's published hits flip to non-hit (and
vice versa) when the same per-gene scores are re-thresholded / renormalized by a
defensible alternate rule. Corroborated framing (Billmann 2023 Cell Systems;
Dempster 2019 Nat Commun): gene SCORES are often concordant, but the binary HIT
CALL is method-dependent - that fragility is exactly what a scientist needs flagged.

Data: BioGRID ORCS per-screen rows carry per-gene score.1-5 + the authors' HIT flag.
Pluggable into verifier.py's agent layer: the finding (per-screen discordance +
example flipped hits) is what the mechanism/precedent/adversary lenses reason over.
"""

from __future__ import annotations
import numpy as np


def rederive_hits(
    scores: np.ndarray,
    published_hit: np.ndarray,
    method: str = "zscore",
    q: float = 0.05,
):
    """Re-derive binary hit calls from a per-gene score vector under an alternate rule.
    `published_hit` sets the DIRECTION and rough stringency to match (so we compare
    like-for-like: same number-ish of hits, alternate boundary). Returns a boolean
    hit vector."""
    s = np.asarray(scores, dtype=float)
    ph = np.asarray(published_hit).astype(bool)
    n_pub = int(ph.sum())
    if n_pub == 0:
        return np.zeros(len(s), bool)
    # direction: are published hits the LOW-score tail (dropout/essential) or HIGH tail?
    low = s[ph].mean() < s[~ph].mean() if (~ph).any() else True
    if method == "zscore":
        z = (s - np.nanmean(s)) / (np.nanstd(s) + 1e-9)
        thr = np.nanquantile(z, q) if low else np.nanquantile(z, 1 - q)
        return (z <= thr) if low else (z >= thr)
    if method == "topN":  # alternate: take exactly n_pub most-extreme by raw score
        order = np.argsort(s) if low else np.argsort(-s)
        out = np.zeros(len(s), bool)
        out[order[:n_pub]] = True
        return out
    raise ValueError(method)


def discordance(scores, published_hit, method="zscore", q=0.05) -> dict:
    """Compare published hits vs alternate-rule hits. Returns Jaccard, % of published
    hits that flip to non-hit, and counts - the ScreenAudit signal for one screen."""
    ph = np.asarray(published_hit).astype(bool)
    alt = rederive_hits(scores, ph, method=method, q=q)
    inter = (ph & alt).sum()
    union = (ph | alt).sum()
    jacc = inter / union if union else 1.0
    flipped_out = int(
        (ph & ~alt).sum()
    )  # published hits that are NOT hits under the alternate rule
    flipped_in = int((~ph & alt).sum())
    return {
        "n_genes": int(len(ph)),
        "n_published_hits": int(ph.sum()),
        "jaccard": round(float(jacc), 3),
        "pct_published_hits_lost": round(100 * flipped_out / max(int(ph.sum()), 1), 1),
        "flipped_out": flipped_out,
        "flipped_in": flipped_in,
        "method": method,
    }


def verdict_from_discordance(d: dict) -> str:
    pct = d["pct_published_hits_lost"]
    return "FRAGILE" if pct >= 25 else ("BORDERLINE" if pct >= 10 else "ROBUST")


if __name__ == "__main__":
    # Synthetic self-test: validate the logic before real ORCS data arrives.
    rng = np.random.RandomState(0)
    n = 2000
    scores = rng.normal(0, 1, n)
    # published hits = bottom ~5% (dropout/essential), but with noise near the boundary
    thr = np.quantile(scores, 0.05)
    published = scores <= thr
    # flip a few near-boundary calls to simulate method-dependent published hits
    boundary = np.argsort(np.abs(scores - thr))[:40]
    published[boundary[::2]] = ~published[boundary[::2]]
    d = discordance(scores, published, method="zscore", q=0.05)
    print("SYNTHETIC screen discordance:", d, "->", verdict_from_discordance(d))
    d2 = discordance(scores, published, method="topN")
    print("SYNTHETIC (topN alt rule):   ", d2, "->", verdict_from_discordance(d2))
    assert 0 <= d["jaccard"] <= 1 and d["n_published_hits"] > 0
    print(
        "gate logic OK - ready to run on real BioGRID ORCS screens once the API key is available"
    )
