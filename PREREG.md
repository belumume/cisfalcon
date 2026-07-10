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

## 5. Circularity control + the split caveat
PRE-COMMITTED: the atlas models were fine-tuned on the atlas designs, so atlas designs are scored
OUT-OF-FOLD (each by a fold whose held-out test set contains it, via `mpra_data_splits.json`).
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
  base-rate separation across cells and generators (`cisfalcon/cell_prior_baseline.py`).

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
