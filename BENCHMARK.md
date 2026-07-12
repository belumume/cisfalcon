# The Cross-Lab Enhancer-Specificity Benchmark

A public, leakage-immune benchmark for one question the AI-enhancer-design field has no standard
test for: **given a designed regulatory sequence, will it fire in the wrong cell type before you
synthesize it?**

`data/gosai_designed/designed_benchmark.csv` holds **93,435 AI-designed enhancers** with per-cell
measured MPRA activity, a transparent failure label, and reproducible splits.

## Why this benchmark exists

Generative models now design cell-type-specific enhancers, and a large fraction silently misfire in
the wrong cell. There is no shared, leakage-controlled benchmark for the *pre-synthesis QC* task, so
every group evaluates specificity differently and often on data their model has seen. This benchmark
fixes both: the labels are a transparent function of measured activity (no opaque score), and the
designs come from a **different lab** than the scoring model was trained on.

## What "leakage-immune" means here

The activity model scored against (the DHS64-MPRA atlas, Castillo-Hair et al. 2025) was finetuned on
the Seelig lab's own ~9,000-enhancer MPRA. The designs in this benchmark are the Gosai/Tewhey
(Broad/JAX) designed-enhancer library. **Zero overlap** in designs or lab. So a model's score on this
set is a genuine cross-lab generalization measurement that memorization cannot inflate.

## Schema (`designed_benchmark.csv`, 93,435 rows)

| column | meaning |
|---|---|
| `id` | design identifier (encodes the generator method + intended target cell) |
| `target_cell` | the cell type the design was built to be active in |
| `method` | the generative method that produced it (fsp, den, motif_embedding, hmc, sa, ...) |
| `sequence` | the designed DNA (fixed length) |
| `K562`, `HepG2`, `SKNSH` | measured MPRA activity (log2FC) per cell type |
| `measured_gap` | `target_activity - max(off-target activity)`; > 0 = specific, <= 0 = fails |
| `measured_fail` | 1 if the design is NOT most-active in its own target cell (the label) |

The label is **fully transparent and reconstructable** from the activity columns; it does not depend
on any model's opaque specificity score.

## The task

Predict `measured_fail` from `sequence` alone, before synthesis, so a lab can triage a design library
and spend synthesis budget on the designs most likely to work. Report AUROC/AUPRC against
`measured_fail`, and rank by predicted specificity gap.

## Splits (`build_benchmark.py`)

- **Primary (stratified random 70/30, fixed seed):** calibration/test have matched failure
  distributions, stratified by target cell x method x fail, so discrimination is measured free of an
  easy/hard-cell confound.
- **Secondary (leave-cell-types-out):** a held-out set of target cells the model never calibrated on,
  a generalization stress test. Failure rate is strongly cell-type-dependent, so this is reported
  separately, never as the headline.

## Reference baseline

CisFalcon's frozen-atlas ensemble (this repo) scores **cross-lab AUROC 0.80** on this benchmark
(random = 0.50), with a transparent decomposition (pooled 0.80 / within-cell-macro 0.75 /
cell-prior-only 0.66). Reproduce with `python reproduce_flagship.py` (no GPU). It is an open baseline
for other models to beat.

## Use / cite

- Score your model on `sequence`, evaluate against `measured_fail`, report on both splits.
- Source designs + measured MPRA: Gosai et al. / Tewhey (Zenodo 10698014). Scoring atlas:
  Castillo-Hair et al. 2025 (Zenodo 17410822). This benchmark packaging + the transparent
  gap/fail label: this repository (`github.com/belumume/cisfalcon`), MIT-licensed.
- If you use it, cite this repository and the two source datasets above.
