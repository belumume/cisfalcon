# The Cross-Lab Enhancer-Specificity Benchmark

A public, leakage-immune benchmark for one question the AI-enhancer-design field has no standard
test for: **given a designed regulatory sequence, will it fire in the wrong cell type before you
synthesize it?**

`data/gosai_designed/designed_benchmark.csv` holds **93,435 AI-designed enhancers** with per-cell
measured MPRA activity and a transparent failure label.

The splits below are NOT a column in that file. They are produced deterministically by
`build_benchmark.py` from a fixed seed, so anyone re-running it gets the same assignment. Looking
for a `split` column in the CSV and finding none does not mean the splits are missing; run the
script.

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
| `method` | the generative method that produced it. The file carries exactly eight codes: `al` (AdaLead), `fsp` (FastSeqProp), `hmc` (Hamiltonian MC), `sa` (simulated annealing), `sa_rep` (simulated annealing, replicated), plus the three low-n unconstrained variants `al_uc`, `fsp_uc`, `sa_uc` (about 300 designs each) |
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
cell-prior-only 0.68 / fully-conditioned joint within (cell x generator) 0.66). Reproduce with
`python reproduce_flagship.py` (no GPU), and the decomposition with `python cell_prior_baseline.py`.
Score a competing model at the conditioned operating point too, not only the pooled one: `python
triage_conditioning_check.py` prints the per-stratum triage figures that go with the 0.66. It is an
open baseline for other models to beat.

### Leaderboard (the reference is 0.80; beat it)

Scored on the same 93,435-design failure-prediction task. The evaluation scope differs by row and is
stated, so the numbers are honest rather than implied to be one eval:

| Model | Cross-lab AUROC | Evaluated on |
|---|---:|---|
| Two-head ensemble (activity + chromatin accessibility) | **0.806** | full benchmark (`ensemble_ci.py`, all 93,435); the lift over the best single head has a 95% CI excluding 0 |
| CisFalcon activity CNN (the reference baseline) | **0.80** | full benchmark; 0.8013 (`reproduce_flagship.py`), 0.8016 on the ensemble's independent code path (`ensemble_ci.py`) |
| Chromatin-accessibility head alone | 0.789 | full benchmark (`ensemble_ci.py`, all 93,435), a fair cheaper single-model comparison |
| AlphaGenome (DeepMind, independent, never trained on any MPRA) | 0.688 | **different basis, not comparable to the rows above**: n=240 stratified *balanced* subsample (50% failures by construction), not the full 93,435 at a 6.29% base rate. Matched on those same 240 rows CisFalcon scores 0.673 vs AlphaGenome 0.688, paired delta +0.015, 95% CI [-0.038, +0.063] (includes zero, so indistinguishable). See `docs/independent-model-crosscheck.md`, reproduce with `alphagenome_matched.py` |
| GC-content | 0.51 | full benchmark, trivial baseline |
| Sequence length | 0.50 | full benchmark, trivial baseline |
| Random | 0.50 | chance |

Two independent-lineage models (an activity CNN and DeepMind's AlphaGenome) both separating the same
wet-lab failures well above chance is the evidence the signal is real, not one model family's artifact.

## Use / cite

- Score your model on `sequence`, evaluate against `measured_fail`, report on both splits.
- Source designs + measured MPRA: Gosai et al. / Tewhey (Zenodo 10698014). Scoring atlas:
  Castillo-Hair et al. 2025 (Zenodo 17410822). This benchmark packaging + the transparent
  gap/fail label: this repository (`github.com/belumume/cisfalcon`), MIT-licensed.
- If you use it, cite this repository and the two source datasets above.
