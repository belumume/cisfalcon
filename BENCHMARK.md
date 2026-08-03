# The Cross-Lab Enhancer-Specificity Benchmark

A public, leakage-immune benchmark for one question the AI-enhancer-design field has no standard
test for: **given a designed regulatory sequence, will it fire in the wrong cell type before you
synthesize it?**

`data/gosai_designed/designed_benchmark.csv` holds **93,435 AI-designed enhancers** with per-cell
measured MPRA activity and a transparent failure label.

The splits below are NOT a column in that file. `python make_splits.py` regenerates both from the
committed CSV alone, from a fixed seed, and prints a sha256 of the assignment so two submitters can
confirm they scored the same partition. Looking for a `split` column in the CSV and finding none
does not mean the splits are missing; run the script.

Corrections and the dated record of what in this repository has been retracted or re-derived live in
[`PREREG-ERRATA.md`](PREREG-ERRATA.md); read it alongside anything below.

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

One rounding caveat, because it changes a count: `measured_gap` ships rounded to 3 decimals (max
deviation from the recomputed value 5.0e-4), so five rows with a genuinely positive gap round to
exactly 0.0. `(measured_gap <= 0).sum()` is therefore 5,879 while the shipped `measured_fail` label
sums to 5,874. Recomputing the gap from the three activity columns reproduces 5,874 exactly.
**Recompute from `K562`/`HepG2`/`SKNSH`, or use `measured_fail` directly; do not re-derive the label
from the rounded `measured_gap`.** The base rate rounds to 6.29% either way, so no headline moves.

## The task

Predict `measured_fail` from `sequence` alone, before synthesis, so a lab can triage a design library
and spend synthesis budget on the designs most likely to work. Report AUROC/AUPRC against
`measured_fail`, and rank by predicted specificity gap.

## Splits (`make_splits.py`)

Run `python make_splits.py` (no GPU, seconds) to print both splits and their sha256, or
`python make_splits.py --write` to emit `data/gosai_designed/designed_splits.csv` keyed by `id`.

The split assignment sha256 is pinned to
`5628e8ca09d0d33ef49e50d8d699409e3127a2169edf3c87ce1a1c9143fea331`. `make_splits.py` asserts
against that value and exits non-zero on a mismatch, so an environment that produces a different
partition fails loudly instead of printing a different hash under the same reassuring caption. If
it mismatches, report that rather than a leaderboard number: the partition is not comparable.

- **Primary `split` (stratified random 70/30, seed 0):** calibration 65,404 / test 28,031, stratified
  by target cell x method x `measured_fail`, so both sides carry matched failure distributions
  (6.29% each) and discrimination is measured free of an easy/hard-cell confound. Rows are sorted by
  `id` before assignment, so the partition does not depend on the CSV's row order.
- **Secondary `split_lco` (leave-cell-out):** this benchmark has exactly three target cells, so
  leave-cell-out is three folds rather than one fixed held-out set. Calibrate on two cells, test on
  the third, three times. Failure rate is strongly cell-dependent (K562 0.59%, HepG2 8.20%,
  SKNSH 10.06%), so report the three folds separately and never pool them into a headline.

`build_benchmark.py` does **not** produce these splits. It builds a separate in-distribution
benchmark from the atlas supplementary `media-10.xlsx` (not committed here) and writes
`data/benchmark.csv`; its held-out cell list names MCF7, which is not one of this benchmark's three
cells. Use `make_splits.py` for this file.

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
stated, so the numbers are honest rather than implied to be one eval.

**Read these with the right interval, or you will read a difference that is not there.** At n=93,435
the design-level 95% CI is about +/-0.005 (the reference baseline's is [0.796, 0.807]), which makes
small gaps look decisive. The honest interval for "does this generalize" is the cluster bootstrap
over the 24 cell x generator strata, and for the reference baseline that is **[0.614, 0.895]** wide,
because the ranker is strong on failure-prone generators and near chance on the best-optimized ones
(`bootstrap_ci.py`, 2000 resamples, seed 0). So treat sub-0.02 differences between rows as not
separable, and report both intervals for any model you add.

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

- Score your model on `sequence`, evaluate against `measured_fail`, and report on both splits from
  `python make_splits.py` (quote the printed sha256 so the partition is checkable). Report the
  design-level and the cluster CI, not just the point estimate.
- Source designs + measured MPRA: Gosai et al. / Tewhey (Zenodo 10698014). Scoring atlas:
  Castillo-Hair et al. 2025 (Zenodo 17410822). This benchmark packaging + the transparent
  gap/fail label: this repository (`github.com/belumume/cisfalcon`), MIT-licensed.
- If you use it, cite this repository and the two source datasets above.
