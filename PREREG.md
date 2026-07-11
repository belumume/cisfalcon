# CisFalcon methodology and frozen analysis record

**Honest scope note.** This is a transparent methodology and results record, committed with the
code and data pointers so any reviewer can reproduce and audit every number. It is NOT a
prospective pre-registration: the analyses below ran during the build. Where a choice was fixed
before a number was read it is marked PRE-COMMITTED; where a breakdown was produced after seeing
results it is marked EXPLORATORY/POST-HOC. Every known limitation is stated in line, not buried.

## 1. Object under test
A pre-synthesis quality signal that predicts, from sequence alone, whether an AI-designed
cell-type-specific enhancer will FAIL its intended cell-type specificity in a wet-lab MPRA.
Defensive use only: it ranks and flags designs so a lab can deprioritize or redesign the riskiest
before spending on synthesis. It does not design DNA.

## 2. Honest headline framing (corrected after an internal adversarial audit)
CisFalcon is a **cross-lab failure-risk RANKER (triage tool)**, not a uniform hard abort-gate.
At the real deployment base rate (6.3% of an independent lab's designs fail), a hard gate has poor
precision (PPV 0.24 at recall 0.5). Its genuine value is triage:
- **Rank and make the safest first**: synthesizing the safest-ranked 50% cuts the specificity
  failure rate from 6.3% to 1.9% (70% fewer failures in what you make).
- **Flag the riskiest**: the flagged riskiest 2% are enriched 7.8x for real failures (PPV 0.49 vs
  6.3% base); riskiest 10% captures 43% of all failures (4.3x).
Report the operating point and the triage value, never a base-rate-blind AUROC alone.

## 3. Predictor (PRE-COMMITTED, frozen)
Atlas DHS64-MPRA activity models (Castillo-Hair et al. 2025; bioRxiv 2025.09.30.679565; Zenodo
17410822), three shipped fold models (splits 0, 1, 3). Input: 500 bp, one-hot A/C/G/T, left-aligned
zero-padded (verbatim atlas `src/sequence.py`; see `cisfalcon/gate.py::one_hot_encode`). Output:
predicted log2FC across 12 human cell lines in fixed order. Ensemble = mean over folds for novel
designs. We train/fine-tune nothing.

## 4. Failure label (PRE-COMMITTED, transparent)
A design FAILS specificity iff it is NOT most-active in its intended target cell:
`gap = log2FC(target) - max_off-target log2FC ; FAIL := gap <= 0`, over the relevant cell panel.
Defined independently of the atlas's opaque `specificity_score_mingap` (our recompute matched it
only 63.7%); we report r=0.822 / 89% sign-agreement to the atlas score as corroboration, not as the
metric. EXPLORATORY caveat: both our label and the atlas score are functions of the same measured
activity, so this is internal consistency, not independent validation; ~11% sign-disagreement sits
near gap=0, an irreducible label-noise band at the decision boundary.
REPRODUCIBILITY NOTE (surfaced by an independent Claude Science re-derivation of this repo): in the
committed `designed_scored.csv`, `measured_fail` is the authoritative label computed from the UNROUNDED
gap per `gap <= 0`; the `measured_gap` column is rounded for display, so ~20 designs round to
`measured_gap == 0` yet are correctly labeled by their unrounded sign. Re-derive the label from
`measured_fail`, not from the rounded `measured_gap` (recomputing from the rounded column shifts the base
rate by 5e-5 and no reported metric by more than 1e-4).

## 5. Circularity control + the split caveat
PRE-COMMITTED: the atlas models were fine-tuned on the atlas designs, so atlas designs are scored
OUT-OF-FOLD (each by a fold whose held-out test set contains it, via the atlas's `mpra_data_splits.json`).
That split map and the atlas `src/sequence.py` encoder are atlas-provided artifacts (atlas Zenodo 17410822),
referenced not redistributed to respect the source's rights; they are needed only for the in-distribution
sanity check (Section 7). The FLAGSHIP cross-lab result (Section 6) needs neither and re-derives fully from
the committed `data/gosai_designed/designed_scored.csv`.
HONEST CAVEAT (verified post-hoc from the atlas `make_data_splits.ipynb`): the atlas CV split is a
random per-sequence split with EXACT-duplicate removal only, with NO sequence-similarity / design-
family clustering. Generative optimizers emit families of near-identical sequences, so near-
duplicates can split across train/test and the in-distribution numbers (Section 7) may be somewhat
leakage-inflated. The CROSS-LAB result (Section 6) is immune: Gosai is a separate dataset with zero
sequence overlap with atlas training, which is the decisive reason it is the flagship.

## 6. Cross-lab result (FLAGSHIP, non-circular, leakage-immune)
Frozen atlas ensemble scored on an INDEPENDENT lab, model, and generators: Gosai et al. 2024
(Nature 10.1038/s41586-024-08070-z; Zenodo 10698014), OL46 validation MPRA, 93,435 BODA/Malinois
designs (AdaLead / Simulated Annealing / Hamiltonian MC / FastSeqProp) measured in K562/HepG2/SKNSH.
No sequence overlap with atlas training: an exact-sequence match against the atlas design set finds
none, and the two design sets come from independent labs, activity models, and generators, so any
overlap could only be coincidental (near-duplicate collision across independent processes is
implausible, though not exhaustively excluded by alignment). Specificity computed over the 3 shared cells.
- **AUROC 0.801, AUPRC 0.293** (n=93,435; base fail 6.29%; random AUPRC = 0.063, so 4.6x lift).
- Beats trivial baselines decisively: GC-content 0.51, sequence-length 0.50, random 0.50.
- EXPLORATORY/POST-HOC, bootstrap 95% CIs (`cisfalcon/bootstrap_ci.py`, 2000 resamples, seed 0):
  the design-level 95% CI on the pooled AUROC is **[0.796, 0.807]** (tight, as expected at n=93,435);
  the honest **cluster** bootstrap that resamples the 24 cell x generator strata as blocks (respecting
  effective sample size, not raw N) is **[0.614, 0.895]**, wide precisely because of the per-generator
  heterogeneity above (near-chance on the best-optimized generators, strong on failure-prone ones).
  Triage enrichment 7.74x [7.39x, 8.14x]; safest-half reduction 70% [67.9%, 71.5%]. The paired
  difference of the pooled AUROC over each best-oriented trivial baseline (random / GC / length) is
  +0.29 to +0.30, every 95% CI excluding zero, so the separation from a trivial predictor is
  statistically real, not a large-n artifact.
- EXPLORATORY/POST-HOC per generator: strong where failures are common (hmc AUROC 0.92, 22% fail),
  near coin-flip on the best-optimized generators (FastSeqProp 0.62, AdaLead 0.61, both <1-2% fail).
  Macro-average within-generator AUROC 0.726; the pooled 0.801 benefits from cross-generator
  separation, so the honest summary is a heterogeneous ranker, strong on failure-prone designs and
  weak on already-well-optimized ones, not a uniform gate. Subgroup AUROCs at low positive counts
  (fsp n_pos=183, al n_pos=340) are noisy; do not rank generators whose CIs overlap.
- EXPLORATORY/POST-HOC, cell-prior control: the pooled 0.801 is per-SEQUENCE signal, not just a
  shared cell-line prior. A cell-prior-only baseline (score = the target cell's base fail-rate, no
  sequence at all) reaches AUROC 0.678; WITHIN each target cell (cell prior removed) the gate still
  separates failures at macro-AUROC 0.747 (HepG2 0.833, SKNSH 0.731, K562 0.678). So per-sequence
  discrimination survives removing the cell prior; the pooled 0.801 additionally benefits from
  base-rate separation across cells and generators. Removing BOTH base-rate axes at once (the joint
  within-(target-cell x generator)-stratum macro-AUROC, 14 strata with >=10 pos and >=10 neg) gives the
  genuine per-sequence discrimination = 0.662: heterogeneous (0.955 on failure-prone HepG2-hmc designs,
  0.850 SKNSH-hmc, down to ~0.53-0.57 on the best-optimized al/sa_rep). So a substantial part of the
  pooled 0.801 is base-rate separation across cells and generators; the honest per-sequence signal is
  0.66 (well above 0.50 and every trivial baseline, but not 0.80). Report the pooled 0.801 as the
  deployment number for a mixed batch (where knowing a design's target cell and generator IS usable
  information) and the 0.66 as the fully-conditioned per-sequence discrimination
  (`cisfalcon/cell_prior_baseline.py`, stratified over `data/gosai_designed/designed_scored.csv`).
- EXPLORATORY/POST-HOC, failure-threshold robustness: the 0.801 is stable across the fail-label
  binarization, not an artifact of the pre-committed gap<=0 cutoff. AUROC ranges 0.85 (fail := gap<=-0.5,
  the decisive failures) to 0.73 (fail := gap<=1.0, including marginal near-boundary calls), with 0.801 at
  gap<=0; far above the 0.50 baselines at every threshold (`cisfalcon/threshold_robustness.py`).
- EXPLORATORY/POST-HOC, emitted-probability calibration: the tool's `calibrated_fail_probability` is fit by
  isotonic regression on the 93,435 cross-lab (pred_gap, measured_fail) pairs. Held-out calibration error
  (fit on a random half, evaluate the ECE on the other half, both directions averaged) is 0.0031, versus
  0.1671 for the documented sigmoid the tool shipped before this fix, a 54x reduction in probability error.
  Isotonic is monotonic, so the ranking AUROC 0.801 is unchanged; only the emitted probability becomes
  trustworthy. Held-out reliability is near-diagonal across bins (predicted 0.03/0.14/0.42/0.95 vs observed
  0.03/0.13/0.42/0.93). Fit + honesty check: `cisfalcon/fit_calibration.py`; the map ships as
  `data/calibration.csv` and the live tool is confirmed serving it (gap -1.19 -> P 0.70, not the sigmoid 0.97).
- Accessibility-only cross-lab baseline (COMPUTED, strong-baseline check): the same 93,435 designs scored with
  the cheaper DHS64 chromatin-accessibility model (`cisfalcon/accessibility_baseline.py`; Kaggle GPU kernel
  `ubaidullahshuaib/cisfalcon-accessibility-crosslab`), specificity gap over the SAME 3 cells. The accessibility
  head is 64 DHS biosamples in a different order than the 12 MPRA cells, so K562/HepG2/SKNSH are read at atlas
  biosample indices 57/49/30 (NOT the MPRA indices 7/6/3, a cell-index bug we found and fixed), and the model is
  multi-head (logsignal + binary). Result on the full 93,435: activity gate **0.8016** (independently re-confirms
  the flagship 0.8013 on a fresh run and fresh code path) vs accessibility **0.789** (binary head) / **0.768**
  (logsignal head). So cross-lab, the MPRA-activity model is the best single predictor but adds only **+0.01 to
  +0.03** over the cheaper accessibility model, far smaller than the ~0.11 activity advantage in-distribution
  (activity 0.90 vs accessibility 0.79). This is consistent with part of the in-dist activity edge being the
  near-duplicate leakage of Section 5, which the leakage-immune cross-lab test removes; both models are far above
  the 0.50 trivial baselines. Honest read: chromatin accessibility already captures most of the cross-lab
  specificity-failure signal, and the activity model is the deployed best by a modest, real margin.

## 7. In-distribution (SANITY CHECK, not the flagship, carries the leakage caveat)
Matched apples-to-apples to the cross-lab number (same 3 cells, same fail label, OOF), n=587 atlas
designs targeting the 3 shared cells: **AUROC 0.896, AUPRC 0.688** (base fail 16.7%). Real
generalization loss in-dist -> cross-lab is ~0.10 AUROC (0.896 -> 0.801); base-rate-corrected
precision lift is comparable (4.1x vs 4.6x). The often-cited 0.921 is over the 10-cell panel at 48%
base rate and is NOT comparable to the cross-lab number; do not present 0.921 vs 0.801 as a drop.
Accessibility-only baseline over the 10-cell panel = 0.79. A from-scratch second implementation
(`cisfalcon/molab_verify_port.py`, separate infrastructure) reproduced the full-panel OOF number
exactly (AUROC 0.911, n=1876), a third in-distribution configuration, distinct from both the 0.896
matched-3-cell number and the 0.921 10-cell number; it confirms the pipeline is deterministic and
reproducible, and is separate from the flagship cross-lab 0.801 (a single run, not reimplemented).

## 8. What would have falsified the claim (and did not)
- Cross-lab AUROC near 0.5, or not beating trivial baselines: NOT observed (0.80 vs ~0.50 baselines).
- Cross-lab performance being purely a task/base-rate artifact: addressed by the matched Section 7
  comparison and the baseline anchor.
Residual honest weaknesses that remain (not falsifications, but stated): weak within-generator
discrimination on the best-optimized designs; in-dist leakage risk; the operating-point PPV ceiling
inherent to a 6% base rate.

## 9. Reproducibility
Code: `cisfalcon/gate.py` (frozen encoder + ensemble), `build_benchmark.py`, `score_oof.py`,
`score_designed.py`, `matched_indist_3cell.py`, `operating_point.py`, `dollar_table.py`,
`verifier.py` (agent harness). Cross-lab GPU run: Kaggle kernel
`ubaidullahshuaib/cisfalcon-gosai-crosslab` (P100), which reads its inputs from the Kaggle dataset
`ubaidullahshuaib/cisfalcon-designed-benchmark`; that dataset ships BOTH `designed_benchmark.csv` AND the
three MPRA fold models in-dataset (models bundled there rather than fetched from Zenodo mid-kernel because
Zenodo 504s flakily on Kaggle). Per-design scores in
`cisfalcon/data/gosai_designed/designed_scored.csv`. All numbers and exact commands:
`build-readiness/DAY1-RESULTS.md` (Results 3, 4, 5, 5b, 5c, 5d).

INDEPENDENT REPRODUCTION (fresh harness): a separate Claude Science session cloned this public repo from
scratch and re-derived every headline number to the decimal from the committed data alone: pooled cross-lab
AUROC 0.8013, AUPRC 0.2929, the joint within-(cell x generator) per-sequence macro 0.662, cell-prior 0.678,
within-cell 0.747, triage 7.75x / PPV 0.487, safest-first 1.91% (70% fewer failures), per-generator hmc
0.922 / macro 0.726, trivial baselines GC 0.51 / length 0.50, calibration ECE 0.0031 vs sigmoid 0.1671
(54x), and ScreenAudit mean Jaccard 0.394. This is a fresh-context reproduction on separate infrastructure
(a determinism/reproducibility property of the builder's own Claude stack, NOT third-party validation), and
it is what surfaced the two fixes above: the `measured_gap` rounding note, and the previously-git-ignored
`designed_scored.csv` / `designed_benchmark.csv` (now committed so any judge can re-derive the numbers).
