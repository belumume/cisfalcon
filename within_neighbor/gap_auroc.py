"""Route-agnostic within-neighbor specificity-gap validation harness.

Validates that the CisFalcon PARADIGM (a specificity gap from a FROZEN EXTERNAL
activity model separates enhancers by their intended vs off-target cell) extends
from cross-LINEAGE (the shipped 0.80 result) to within-LINEAGE-NEIGHBOR
resolution (e.g. melanoma MEL vs MES states, or neighboring immune subtypes).

This file is model-agnostic on purpose: the scoring pipeline
(one-hot -> model -> gap -> AUROC + paired bootstrap CI) is identical across
every candidate route the route-exhaustion workflow is ranking. Plug in a
`predict_fn(seq) -> np.ndarray` and the target/off-target index sets, and it
produces the pre-registered number: AUROC of the gap separating
target-specific (label 1) from off-target-cross-active (label 0) enhancers,
with a 1000x paired bootstrap 95% CI.

PRE-REGISTERED ACCEPTANCE (fixed before any number is seen):
  * CI excludes 0.50  -> the paradigm generalizes to within-neighbor; lead with it.
  * CI includes 0.50  -> report the NULL honestly (cross-lineage-strong,
                          within-neighbor-weak). A legitimate boundary finding.
Do NOT tune toward a win. Report whatever the held-out number is.

HONESTY GUARDS baked in:
  * Scoring the design-oracle's OWN designed enhancers is circular; pass
    `leakage_note` describing exactly what split this is (e.g. "held-out chr2
    natural enhancers, model never trained on them") and it is echoed into the
    result JSON so the framing can never drift from the data.
  * This is a POSITIVE CONTROL that the gap metric discriminates neighboring
    states unless the enhancers were designed by a DIFFERENT model than the
    scorer; the result JSON records `independence` verbatim.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from typing import Callable, Sequence

import numpy as np
from sklearn.metrics import roc_auc_score

_BASES = {"A": 0, "C": 1, "G": 2, "T": 3, "U": 3}


def one_hot_500(seq: str, length: int = 500) -> np.ndarray:
    """One-hot a DNA/RNA string to (length, 4). Center-crop if longer, center-pad
    with zeros if shorter (N / unknown bases -> all-zero column). Deterministic."""
    s = seq.strip().upper().replace("\n", "")
    if len(s) > length:
        start = (len(s) - length) // 2
        s = s[start : start + length]
    oh = np.zeros((length, 4), dtype=np.float32)
    pad = (length - len(s)) // 2
    for i, b in enumerate(s):
        j = _BASES.get(b)
        if j is not None:
            oh[pad + i, j] = 1.0
    return oh


def revcomp_one_hot(oh: np.ndarray) -> np.ndarray:
    """Reverse-complement a one-hot (length,4): reverse positions AND swap A<->T, C<->G."""
    return oh[::-1, ::-1].copy()


@dataclass
class GapConfig:
    """Which model outputs are the target-cell vs off-target-cell activity."""

    target_idx: Sequence[int]  # e.g. MEL topics [16, 15]
    off_idx: Sequence[int]  # e.g. MES topics [18]
    reduce: str = "mean"  # "mean" or "max" over the index set
    average_strands: bool = True  # average fwd + revcomp predictions

    def _reduce(self, v: np.ndarray) -> float:
        r = np.max if self.reduce == "max" else np.mean
        return float(r(v))

    def gap(self, pred: np.ndarray) -> float:
        """pred: 1-D per-class model output. gap = target_activity - max/mean off-target."""
        return self._reduce(pred[list(self.target_idx)]) - self._reduce(
            pred[list(self.off_idx)]
        )


def score_sequences(
    seqs: Sequence[str],
    predict_fn: Callable[[np.ndarray, np.ndarray], np.ndarray],
    cfg: GapConfig,
) -> np.ndarray:
    """predict_fn(fwd_oh, rc_oh) -> 1-D per-class output for ONE sequence.
    (Wrap any Keras/Kipoi model so it returns the (n_class,) vector.)"""
    gaps = np.empty(len(seqs), dtype=np.float64)
    for i, s in enumerate(seqs):
        oh = one_hot_500(s)
        if cfg.average_strands:
            p = 0.5 * (
                predict_fn(oh, revcomp_one_hot(oh))
                + predict_fn(revcomp_one_hot(oh), oh)
            )
        else:
            p = predict_fn(oh, revcomp_one_hot(oh))
        gaps[i] = cfg.gap(np.asarray(p).ravel())
    return gaps


def paired_bootstrap_auroc(
    labels: np.ndarray, gaps: np.ndarray, n_boot: int = 1000, seed: int = 0
) -> dict:
    """AUROC of `gaps` separating label-1 (target-specific) from label-0, with a
    paired (resample-the-same-indices) bootstrap 95% CI. seed fixed for repro."""
    labels = np.asarray(labels).astype(int)
    gaps = np.asarray(gaps, dtype=np.float64)
    assert set(np.unique(labels)) <= {0, 1}, "labels must be 0/1"
    point = float(roc_auc_score(labels, gaps))
    rng = np.random.default_rng(seed)
    n = len(gaps)
    boot = np.empty(n_boot)
    got = 0
    for _ in range(n_boot):
        idx = rng.integers(0, n, n)
        if labels[idx].min() == labels[idx].max():
            continue  # degenerate resample (one class) -> skip
        boot[got] = roc_auc_score(labels[idx], gaps[idx])
        got += 1
    boot = boot[:got]
    lo, hi = np.percentile(boot, [2.5, 97.5])
    return {
        "auroc": round(point, 4),
        "ci95": [round(float(lo), 4), round(float(hi), 4)],
        "ci_excludes_chance": bool(lo > 0.50),
        "n_pos": int((labels == 1).sum()),
        "n_neg": int((labels == 0).sum()),
        "n_boot_effective": got,
    }


@dataclass
class ValidationResult:
    route: str
    model: str
    data: str
    leakage_note: str
    independence: str
    metrics: dict = field(default_factory=dict)

    def verdict(self) -> str:
        m = self.metrics
        if not m:
            return "no metrics"
        if m["ci_excludes_chance"]:
            return (
                f"WITHIN-NEIGHBOR GENERALIZATION DEMONSTRATED: AUROC {m['auroc']} "
                f"(95% CI {m['ci95'][0]}-{m['ci95'][1]}, excludes 0.50). {self.leakage_note}"
            )
        return (
            f"NULL / boundary finding: AUROC {m['auroc']} "
            f"(95% CI {m['ci95'][0]}-{m['ci95'][1]}, includes 0.50) -> the paradigm "
            f"is cross-lineage-strong but within-neighbor-weak on this route. {self.leakage_note}"
        )

    def to_json(self, path: str) -> None:
        d = asdict(self)
        d["verdict"] = self.verdict()
        with open(path, "w", encoding="utf-8") as f:
            json.dump(d, f, indent=2)


def run(
    route: str,
    model: str,
    data: str,
    seqs: Sequence[str],
    labels: Sequence[int],
    predict_fn: Callable[[np.ndarray, np.ndarray], np.ndarray],
    cfg: GapConfig,
    leakage_note: str,
    independence: str,
    out_json: str | None = None,
    n_boot: int = 1000,
) -> ValidationResult:
    gaps = score_sequences(seqs, predict_fn, cfg)
    metrics = paired_bootstrap_auroc(np.asarray(labels), gaps, n_boot=n_boot)
    res = ValidationResult(route, model, data, leakage_note, independence, metrics)
    if out_json:
        res.to_json(out_json)
    return res


if __name__ == "__main__":
    # Self-test: synthetic separable data -> harness produces AUROC ~1.0 with a
    # tight CI that excludes chance. Proves the pipeline before any real model.
    rng = np.random.default_rng(0)
    n = 200
    lab = np.array([1] * (n // 2) + [0] * (n // 2))
    # fake a 4-class model whose class-0 is high for label-1 seqs, class-1 for label-0
    fake_gaps = np.where(lab == 1, rng.normal(1.2, 0.6, n), rng.normal(-1.2, 0.6, n))
    m = paired_bootstrap_auroc(lab, fake_gaps, n_boot=1000)
    print("self-test separable:", m)
    assert m["auroc"] > 0.9 and m["ci_excludes_chance"], "harness broken"
    # null case: gaps independent of label -> AUROC ~0.5, CI includes chance
    null_gaps = rng.normal(0, 1, n)
    mn = paired_bootstrap_auroc(lab, null_gaps, n_boot=1000)
    print("self-test null:      ", mn)
    assert not mn["ci_excludes_chance"], "null case should include chance"
    print("HARNESS OK")
