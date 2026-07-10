"""CisFalcon gate: score a DNA sequence for predicted cell-type-specific activity.

The reusable core shared by the benchmark scorers and the agentic verifier harness.
Wraps the atlas DHS64-MPRA activity models (Castillo-Hair et al 2025) with the exact
encoding/output conventions verified from the atlas source (src/sequence.py,
src/definitions.py). For a NOVEL sequence (never in any model's training set) the
correct deployment mode is to ENSEMBLE the independent fold models; for a sequence
that a specific fold trained on, use score_out_of_fold instead (see score_oof.py).
"""

from __future__ import annotations
import pathlib, functools
import numpy as np

_MODELS_DIR = pathlib.Path(__file__).parent / "models"
INPUT_LEN = 500
MPRA_CELL_LINES = [
    "NT2_D1",
    "GM12878",
    "786_O",
    "SKNSH",
    "WERI_Rb1",
    "SJCRH30",
    "HepG2",
    "K562",
    "MCF7",
    "HeLaS3",
    "HEK293",
    "HMC3",
]
TARGET_CELLS = MPRA_CELL_LINES[
    :10
]  # the 10 target-eligible lines (single-in-panel designs)
CELL_IDX = {c: i for i, c in enumerate(MPRA_CELL_LINES)}
FOLDS = [0, 1, 3]  # atlas shipped model splits


def one_hot_encode(sequences, max_seq_len=INPUT_LEN, padding="left"):
    """Verbatim atlas convention: channels A,C,G,T; padding='left' = sequence at
    index 0, zeros filling to max_seq_len; N and unknowns -> all-zero column."""
    nuc = {
        "a": [1, 0, 0, 0],
        "c": [0, 1, 0, 0],
        "g": [0, 0, 1, 0],
        "t": [0, 0, 0, 1],
        "n": [0, 0, 0, 0],
    }
    out = np.zeros([len(sequences), max_seq_len, 4], dtype=np.float32)
    for i, seq in enumerate(sequences):
        seq = str(seq)
        if len(seq) > max_seq_len:
            seq = seq[:max_seq_len] if padding == "left" else seq[-max_seq_len:]
        oh = np.array([nuc.get(x, [0, 0, 0, 0]) for x in seq.lower()], dtype=np.float32)
        if len(oh) == 0:
            continue
        if padding == "left":
            out[i, : len(seq), :] = oh
        else:
            out[i, -len(seq) :, :] = oh
    return out


@functools.lru_cache(maxsize=None)
def _load_models(kind: str = "mpra"):
    import tensorflow as tf

    prefix = "dhs64_mpra_split" if kind == "mpra" else "dhs64_split"
    models = []
    for k in FOLDS:
        p = _MODELS_DIR / f"{prefix}{k}.h5"
        models.append(tf.keras.models.load_model(p, compile=False))
    return models


def score_sequences(sequences, kind: str = "mpra", batch_size: int = 128) -> np.ndarray:
    """Ensemble-predict activity (log2FC) per cell for NOVEL sequences.
    Returns (N, 12) in MPRA_CELL_LINES order. Ensemble = mean over independent folds
    (valid because a novel sequence is out-of-fold for every model)."""
    X = one_hot_encode(sequences)
    models = _load_models(kind)
    preds = [m.predict(X, batch_size=batch_size, verbose=0) for m in models]
    return np.mean(preds, axis=0)


def specificity_gap(pred: np.ndarray, target_cell: str, cells=None) -> np.ndarray:
    """gap = predicted(target) - max(predicted off-target), computed over `cells`
    (default: the 10 target-eligible lines). Positive gap = predicted most-active in
    target = predicted PASS; gap <= 0 = predicted FAIL of cell-type specificity."""
    cells = cells or TARGET_CELLS
    idx = [CELL_IDX[c] for c in cells]
    sub = pred[:, idx]
    ti = cells.index(target_cell)
    off = np.delete(sub, ti, axis=1)
    return sub[:, ti] - off.max(axis=1)


def verdict(sequences, target_cell: str, cells=None, kind: str = "mpra"):
    """Full gate verdict for a batch of designs all targeting `target_cell`.
    Returns list of dicts: predicted_gap, most_active_cell, predicted_fail, margin."""
    cells = cells or TARGET_CELLS
    pred = score_sequences(sequences, kind=kind)
    gaps = specificity_gap(pred, target_cell, cells)
    idx = [CELL_IDX[c] for c in cells]
    sub = pred[:, idx]
    out = []
    for i, g in enumerate(gaps):
        ma = cells[int(np.argmax(sub[i]))]
        out.append(
            {
                "predicted_gap": float(g),
                "most_active_cell": ma,
                "predicted_fail": bool(g <= 0),
                "margin": float(abs(g)),
            }
        )
    return out
