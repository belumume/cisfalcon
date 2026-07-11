# CisFalcon Day-1 empirical results (Jul 8, during the event)

Analysis performed during the event on public data (atlas Supp Table 9 = `media-10.xlsx`, 9,061 rows). Compliant with "analysis happens during the event."

## Result 1 - measured designed-enhancer failure rate (PRELIMINARY, pending mingap-definition verification)

Metric: the atlas's OWN stored `specificity_score_mingap` (target log2FC minus best off-target). Subset: non-control designs, single target that IS one of the 13 measured cell types, AI-design sources only (`fsp`, `den`, `motif_embedding`); excluded `genome_dhs` natural baselines, multi-target designs, and out-of-panel targets.

- **AI-designed: fail(mingap<=0) = 37.0%, 95% CI [35.6, 38.5], n=4,362; fail(<=1) = 56.1%; median mingap +0.63.**
- Natural genome_dhs baseline: fail(<=0) = 72.7% (n=1,095) -> AI design beats random natural sequence, but ~1 in 3 designs still fail.
- By AI method: `den` 23.8% fail / `fsp` 41.2% / `motif_embedding` 84.4%. Failure is strongly method-dependent.

**Robust takeaway (does NOT depend on the exact threshold):** the measured specificity distribution has large spread and a substantial failure mass -> CisFalcon has a real, abundant, honest signal to detect. Viability confirmed.

## CAVEAT - verify before this is a pitch number

Independent recompute of mingap (target log2FC minus max non-target over the 13-cell panel) matches the atlas's stored `specificity_score_mingap` only **63.7%** of the time on the clean subset. So the atlas's exact specificity definition (cell subset used, formula, success threshold) differs from the naive one. **Do NOT quote ~37% as final until reconciled against the atlas methods (Castillo-Hair et al).** The stored metric is authoritative; the "<=0 = fail" interpretation is what needs confirming.

## Schema facts learned (media-10.xlsx)

- 62 cols: id, sequence, category (13 design/control categories), source (fsp/den/genome_dhs/motif_embedding/...), target, tunable_setpoint, motif fields, DNA+mRNA read counts, `log2FC_*` for 13 cell types (NT2_D1, GM12878, 786_O, SKNSH, WERI_Rb1, SJCRH30, HepG2, K562, MCF7, HeLaS3, HEK293, HMC3, Retina), and 3 stored specificity scores (avg / mingap / tau).
- `target` is heterogeneous: single in-panel (5,457), multi/tuple combinations (2,990), single out-of-panel e.g. HGF/HUVEC (539). The benchmark must handle all three, not assume single-in-panel.
- `genome_dhs` = natural genomic baselines, NOT AI designs -> exclude from the "designed failure rate."

## Next

1. Verify the atlas mingap definition + success threshold (atlas methods / Supp) to firm up the failure number and the benchmark's failure label.
2. B1 GO/NO-GO gate: predictor-vs-measured-mingap correlation - needs the atlas's DHS64-MPRA predictions (Supp Tables 5 & 12), not in media-10.
3. Then B2 (two-independent-model disagreement), PREREG hash, benchmark build.


## Result 1b - RESOLVED failure number (transparent, reproducible; supersedes the ~37% above)

The atlas mingap formula is NOT in their public repo (grep 'mingap' across all code = 0 hits; only the computed column ships in media-10.xlsx), which is why the naive recompute matched their stored score only 63.7%. Resolution: define CisFalcon's failure label TRANSPARENTLY from raw measured log2FC instead of inheriting their opaque score.

**Definition:** a design FAILS specificity if it is NOT the most-active in its own measured target cell, i.e. gap = target_log2FC - max(off-target log2FC) <= 0. Subset: non-control, single in-panel target, AI-design sources (fsp/den/motif_embedding).

- **FAIL (gap<=0) = 47.9%, 95% CI [46.5, 49.4], n=4,362.** FAIL(gap<=1) = 67.3%.
- By method: den 37.7% / fsp 50.9% / motif_embedding 88.3%.
- Transparent gap vs the atlas's stored specificity_score_mingap: **Pearson r=0.822, sign-agreement 89.1%** -> independent AND aligned. This is the number to use; it is fully reproducible and does not depend on their opaque metric.

## Strategic note (from Live Session One / Claude Science demo, Jul 8)

Anthropic built a GENERIC reviewer/verifier INTO Claude Science itself (forks a reviewing agent that checks factual accuracy + artifact quality against a customizable rubric). Implication: "an AI that checks AI's work" is table-stakes to these judges. CisFalcon must NOT be pitched as "a verifier agent" - the defensible framing is the PRE-SYNTHESIS, WET-LAB-GROUND-TRUTH failure predictor (measured MPRA as truth; abort-before-you-synthesize), which their generic reviewer does not do.
Also: Claude Science ships the exact bio skills/connectors (ENCODE-adjacent, AlphaFold, ChEMBL, bioRxiv, etc.) + Modal GPU + parallel sub-agents + provenance, and both tools are encouraged - a potential build accelerator worth evaluating.


## Build-execution state (Jul 9) - gates UNBLOCKED on-machine

- **On-machine TF env WORKS** (no molab needed for the gates; molab only for bulk-680k + cortex scoring later): uv venv Python 3.11.9 + `tensorflow==2.14.0`, at `.venv-tf/` (gitignored). Atlas models are on Zenodo record 17410822 (.h5 Keras).
- **DHS64-MPRA model loads clean** (full Keras, no custom deps): input `(None,500,4)` one-hot; output `(None,12)` = predicted log2FC for the 12 human cell lines in `MPRA_CELL_LINES` order = [NT2_D1, GM12878, 786_O, SKNSH, WERI_Rb1, SJCRH30, HepG2, K562, MCF7, HeLaS3, HEK293, HMC3]. Encoder = atlas `src/sequence.py::one_hot_encode(seqs, max_seq_len=500, padding='left')`.
- **Benchmark reproducible**: `cisfalcon/build_benchmark.py` -> `cisfalcon/data/benchmark.csv` (4,362 AI-designed single-in-panel designs; transparent fail label gap<=0; stratified 70/30 split matched at 47.9%; leave-cell-out split as secondary generalization test).
- **FINDING: failure is strongly cell-type-dependent** (786_O 99.8%, HeLaS3 72.2%, WERI_Rb1 62.9%, SKNSH 52.5%, MCF7 50.6% ... GM12878 43.8%, NT2_D1 38.3%, SJCRH30 28.7%, K562 16.3%, HepG2 12.4%). Implication: CisFalcon must calibrate PER-CELL, not globally; and this heterogeneity is itself a headline insight (which cell types the AI design method can/can't hit).

## B1 methodology (circularity-safe)

DHS64-MPRA was finetuned on ~9k enhancers that LIKELY are these designs -> scoring them naively is circular. Fix: **out-of-fold** scoring - each design scored by a model split (0/1/3) that did NOT train on it, using `data/mpra/mpra_data_splits.json` + the 3 model splits. Downloading (background): dhs64_mpra splits 1&3, dhs64 (accessibility) splits 0/1/3, and `download_data.py` (for the mpra split-map + processed-tsv URLs).

## NEXT (immediate)
1. B1 gate: out-of-fold DHS64-MPRA predicted-vs-measured specificity - Spearman + AUPRC (does the activity model predict which designs fail?).
2. B2 gate: DHS64 (accessibility, NOT MPRA-finetuned -> non-circular) vs DHS64-MPRA (activity) DIVERGENCE tracks failure = the CisFalcon mechanism (atlas Fig 3G-H). Both models out-of-fold where relevant.
3. PREREG.md hash -> verifier harness -> cortex-MPRA cross-lab validation -> 3-min demo + 100-200w summary + OSS repo -> submit Jul 13 9PM ET.


## RESULT 2 - CORE SIGNAL VALIDATED: sequence-only pre-synthesis gate predicts measured failure (Jul 9)

The load-bearing question ("can a model predict, from sequence, which AI-designed enhancers will fail specificity in the wet lab?") is answered YES, with a concrete number, non-circular.

Signal: DHS64 chromatin-ACCESSIBILITY predictions (shipped in enhancer_mpra_processed.tsv as `dhs_pred_*`, sequence-only; the accessibility model never trained on these designs' MEASURED activity -> non-circular). predicted-accessibility specificity gap = target dhs_pred - max off-target dhs_pred, over the 10 MPRA cells that have both measured + predicted (786_O, GM12878, HepG2, HeLaS3, K562, MCF7, NT2_D1, SJCRH30, SKNSH, WERI_Rb1). n=4,362 AI-designed single-in-panel designs.

- **AUROC = 0.793** (predicted-accessibility specificity discriminating measured specificity FAIL).
- **Spearman(pred_access_gap, measured_gap) = 0.587.**
- **Flag lowest-25% predicted-gap -> 71.7% genuinely failed** vs 37.0% base rate (~1.9x precision lift), from sequence alone, pre-synthesis.

Caveats / next rigor: (a) AUROC is model-non-circular but the DEPLOYED threshold must be set on the calibration split and evaluated on the held-out test split (PREREG). (b) This is the single-model (accessibility) signal; next: add the ACTIVITY model (DHS64-MPRA) OUT-OF-FOLD (3,836 designs with clean OOF coverage from folds 0/1/3) and test whether the accessibility-vs-activity DIVERGENCE (the atlas Fig 3G-H mechanism) BEATS 0.793. (c) This is on the atlas designs; the Pollard/Ahituv cortex MPRA is the separate cross-lab generalization test. (d) Per-cell calibration (failure is 12-99.8% by cell) likely lifts performance further.

Data + models all on disk (cisfalcon/data, cisfalcon/models); env `.venv-tf`. Reproducible.


## RESULT 3 - OUT-OF-FOLD ACTIVITY MODEL: the pre-synthesis gate hits AUROC ~0.92 (Jul 9)

B1 (out-of-fold activity) + B2 (combine) run. The atlas DHS64-MPRA activity models scored the benchmark OUT-OF-FOLD: each design scored by the split whose held-out TEST fold contains it, so the scoring model never trained on that design. Out-of-fold is MANDATORY here because the finetuning set IS these designs (8,948/8,948 sequence overlap confirmed) - naive scoring would be circular. OOF coverage = 1,876 / 4,362 designs (test sets of folds 0/1/3). Encoding + output order verified verbatim from atlas src (src/sequence.py one_hot_encode 500bp left-aligned ACGT; output = predicted log2FC in MPRA_CELL_LINES order; load_model compile=False).

Fail-discrimination (n=1,876 OOF subset; 36.1% measured fail rate):
- B0 accessibility gap (non-circular, shipped dhs_pred, covers ALL 4,362): AUROC 0.792, AUPRC 0.684
- B1 activity gap (out-of-fold): AUROC 0.911, AUPRC 0.878, Spearman(pred,measured)=0.846
- Held-out TEST split (n=567, combiner calibrated on calibration split): activity AUROC 0.921 / AUPRC 0.890; accessibility 0.783; combined 0.918
- Flag lowest-25% activity gap -> 89.8% genuinely fail (vs 36.1% base) ~= 2.5x precision, from sequence alone, pre-synthesis.

Honest reads:
- The out-of-fold ACTIVITY model is the gate (AUROC ~0.92 held-out, non-circular). Accessibility alone is 0.79 (weaker, but covers all designs and is fully independent of activity training).
- Combining accessibility + activity does NOT beat activity alone (0.918 vs 0.921). The two are correlated (Spearman 0.717) because the activity model was FINETUNED FROM the accessibility model (same lineage). So the "accessibility-vs-activity divergence" hypothesized as the CisFalcon mechanism is NOT the win; the activity model's direct predicted specificity is. Honest negative on the divergence; cleaner headline.
- 0.92 is on held-out ATLAS designs = in-distribution for the activity model's finetuning. Cross-lab / cross-design-method generalization is NOT tested by this number -> that is exactly what the Pollard/Ahituv cortex-MPRA cross-lab validation addresses next (the moat).
- In DEPLOYMENT (a brand-new design never in any training set), every model split is out-of-fold for it, so the full activity model is usable at the ~0.92 operating point.

Reproducible: cisfalcon/score_oof.py (embeds atlas encoder verbatim), cisfalcon/atlas_ref/ (fetched atlas src for provenance), models + data on disk, .venv-tf. Raw output: cisfalcon/data/oof_results.txt.

HEADLINE MOVED: the honest pitch number is now "an out-of-fold sequence model predicts which AI-designed enhancers fail cell-type specificity at AUROC ~0.92, catching ~90% of failures in its flagged riskiest quartile, before synthesis" - superseding the accessibility-only 0.79 and the fly 27/40.

## RESULT 4 - PORT VERIFIED; CROSS-LAB WEAKNESS IS REAL OOD, NOT A BUG (Jul 10)

Independent re-implementation on molab (own encoder + OOF logic) reproduces the in-distribution headline to 3 decimals:
[PORT-CHECK] n=1876 OOF atlas designs, fail=36.1% | Spearman(pred,measured gap)=0.846 | AUROC(specificity)=0.911
Matches score_oof.py (laptop, gate.py). -> molab scoring is correct (encoding, cell-index map, out-of-fold all sound).

So the weak Gosai cross-lab is REAL out-of-distribution behavior, root-caused (not a port bug):
[Gosai CRE natural enhancers] n=14086 | per-cell Spearman ~0.25-0.30 | argmax-agree 42% (active 49%) | specGap-rho 0.18 | AUROC-specific 0.61
The atlas DHS64-MPRA model was FINETUNED on AI-DESIGNED enhancers -> design-specific; transfers weakly to independent NATURAL sequences (Gosai GTEx/UKBB/CRE). This is an honest property, NOT a failure of CisFalcon's claim (AI-designed enhancers, where it is 0.92 in-distribution). Non-circular confirmed (0 sequence overlap Gosai<->atlas).

RIGHT cross-lab test = independent AI-DESIGNED enhancers (Gosai's machine-designed CREs, a separate heavier dataset) -> named future work, not a rushed fetch.
Ops: molab CPU too slow for full 798K (14K=391s); all TF compute offloaded to molab (laptop untouched); molab driven via HTTP transport from browser-extracted token; port + cross-lab reproducible from cisfalcon/molab_*.py.

## Result 5: cross-lab DESIGNED enhancers (Gosai/Malinois) = AUROC 0.785 (n=3000 signal)
The make-or-break generalization test. CisFalcon's atlas-trained gate, applied to an
INDEPENDENT lab's AI designs (Gosai/Tewhey OL46 validation MPRA, Zenodo 10698014,
extracted via HTTP range from the 7.9GB zip), predicts measured specificity failure at
**AUROC 0.785** (n=3000 stratified, measured FAIL 6.5%; Spearman(pred gap, meas gap)=0.523).
Non-circular on every axis: different lab, different model (Malinois vs atlas DHS64),
different generators (AdaLead/SimulatedAnnealing/HamiltonianMC never in the atlas training).
Specificity computed over the 3 shared cells (K562/HepG2/SKNSH). Per generator:
hmc 0.906 (23% fail), sa 0.742, fsp 0.663, sa_rep 0.640, al 0.609 (low AUROC tracks low
positive count, not model weakness). Per target: HepG2 0.826, SKNSH 0.715.
Interpretation: 0.79 cross-lab vs 0.92 in-distribution is honest OOD degradation; the moat
("a gate that works on designs from a generator it never saw") HOLDS. Full 93,435-design
precision run pending on GPU (laptop CPU = 4.8 seq/s; the benchmark + score_designed.py are
ready). Reproducible: cisfalcon/score_designed.py + data/gosai_designed/designed_benchmark.csv.

### Result 5 CONFIRMED at full scale (Kaggle P100, n=93,435)
The full 93,435-design run (Kaggle kernel, models + benchmark from a Kaggle dataset, GPU)
CONFIRMS and slightly tightens the n=3000 signal: **AUROC 0.8013**, Spearman(pred_gap, meas_gap)
0.5114, measured FAIL 6.29%. By generator: hmc 0.9216 (22.3% fail), sa 0.7757, sa_rep 0.6953,
fsp 0.6247, al 0.6128. By target: HepG2 0.8332, SKNSH 0.7308, K562 0.6778 (K562 only 0.59% fail
= few positives, hardest to rank). Headline: a gate trained ONLY on the atlas's designs predicts
wet-lab specificity failure in 93k independent designs (Gosai/Tewhey lab, Malinois model,
AdaLead/SimulatedAnnealing/HamiltonianMC generators the atlas never saw) at AUROC 0.80, vs 0.92
in-distribution. Honest OOD degradation; the cross-lab/cross-generator moat HOLDS at scale.
Per-design scores: cisfalcon/data/gosai_designed/designed_scored.csv. Kernel:
kaggle.com/code/ubaidullahshuaib/cisfalcon-gosai-crosslab.

### Result 5b: HONEST operating point (audit fix, the numbers that decide usefulness)
AUROC hides the abort-gate reality at the 6.29% cross-lab base rate. Computed from
data/gosai_designed/designed_scored.csv (cisfalcon/operating_point.py):
- **AUPRC = 0.293** (random = base rate 0.063, so ~4.6x lift) - modest but real.
- As a HARD abort-gate it is poor: recall 0.50 -> PPV 0.24 (9,375 good designs killed per 2,937
  real failures caught); recall 0.70 -> PPV 0.16. Do NOT pitch "abort doomed synthesis" as the primary mode.
- As a TRIAGE / prioritization tool it is genuinely good: flag the riskiest 2% -> PPV 0.49 (8x
  enrichment over the 6% base rate, captures 15.5% of failures); riskiest 5% -> PPV 0.36; riskiest
  10% -> PPV 0.27. Honest value prop = "rank by failure risk; scrutinize/deprioritize the flagged
  riskiest," not a uniform gate.
- BASELINES (the missing anchor): gate AUROC 0.801 vs GC-content 0.511, seq-length 0.502, random 0.500.
  The gate CRUSHES trivial predictors -> the 0.80 is real signal, not an artifact. Strong non-circular anchor.
- Pooling: macro-avg within-generator AUROC 0.726 vs pooled 0.801 (pooled is inflated by cross-generator
  separation). Per generator AUPRC: hmc 0.807 (strong), sa_rep 0.280, sa 0.082, al 0.030, fsp 0.010
  (near base rate = weak on the best-optimized generators). LEAD with the range 0.61-0.92 + the triage
  operating point, not the pooled 0.80.
HONEST HEADLINE (reframed): a cross-lab failure-risk RANKER, grounded in external wet-lab measurement,
that beats trivial baselines and delivers ~8x enrichment on the flagged riskiest designs; strongest where
failures are common, weak on already-well-optimized designs. Not a uniform abort-gate.

### Result 5c: MATCHED in-dist-vs-cross-lab + split-leakage verification (audit fixes #4, #5)
FIX #4 (apples-to-apples): the misleading "0.92 -> 0.80" mixed a 10-cell task (48% fail) with a
3-cell task (6% fail). Matched on the SAME 3 cells (K562/HepG2/SKNSH), same 3-cell fail label,
same OOF scoring (cisfalcon/matched_indist_3cell.py, n=587 atlas designs targeting the 3 cells):
- in-dist 3-cell OOF: **AUROC 0.896, AUPRC 0.688** (fail 16.7%)
- cross-lab 3-cell:   **AUROC 0.801, AUPRC 0.293** (fail 6.3%)
=> REAL generalization loss is ~0.10 AUROC (0.896 -> 0.801), NOT the 0.12 the mismatched comparison
implied. Base-rate-corrected precision lift is comparable: in-dist 0.688/0.167 = 4.1x random,
cross-lab 0.293/0.063 = 4.6x random. The gate genuinely generalizes cross-lab; report the MATCHED
0.896 vs 0.801, never 0.921 vs 0.801.

FIX #5 (leakage): verified the atlas CV split from the authors' own make_data_splits.ipynb
(github.com/castillohair/enhancer-design): `drop_duplicates(subset='sequence')` then
`numpy.array_split(sample(frac=1, random_state=0), 7)` = a RANDOM per-sequence split with
EXACT-dedup only, NO sequence-similarity / design-family clustering. So near-identical designs
(generative variants) CAN split across train/test -> the in-dist 0.896/0.921 may be somewhat
leakage-inflated. State this in PREREG. The CROSS-LAB 0.80 is LEAKAGE-IMMUNE (Gosai is a separate
dataset, 0 atlas overlap) -> this is the decisive reason to LEAD with the cross-lab number as
flagship and treat in-dist as a caveated sanity check.

### Result 5d: the money number (audit fix #9) - honest triage value
Cost model: individual synth+validation ~$250-1000/design, 2-4 weeks (80-PITCH-ANGLES).
- SAFEST-FIRST (strongest honest frame): rank by the gate, synthesize the safest 50% -> specificity
  failure rate **1.91% vs 6.29% random = 70% fewer failures in what you make**. Safest 70% -> 2.54% (60% fewer).
- TRIAGE (redesign the flagged riskiest before synthesis): flag riskiest 10% -> PPV 0.27, catches 42.6%
  of failures, avoids ~$670-2681 per 100 designs; riskiest 5% -> PPV 0.36, ~$447-1786 per 100.
HEADLINE money line for the pitch: "rank your AI designs by CisFalcon and make the safest half first:
70% fewer cell-type-specificity failures in what you synthesize, grounded in an independent lab's wet-lab
measurements." Malinois self-prediction "killer comparator" (does the gate beat Malinois's own confidence)
= STRETCH, not on disk, needs a separate Malinois inference run; gate already beats GC/length/random (all ~0.50).

### Result 6: DEMO built + runs (audit fix #7) + agent-layer value shown (audit fix #8)
`cisfalcon/demo.py` runs end-to-end on a REAL cross-lab caught failure
(20211213_141901__715602__47::hmc__hepg2__0, a Gosai/Malinois design optimized for HepG2):
- Gate predicts most-active = K562 (not HepG2), specificity gap -3.02 -> FAIL, before synthesis.
- AGENT LAYER value (the differentiator a generic reviewer lacks): the synthesizer does not just say
  FAIL, it DIAGNOSES the mechanism and gives an actionable redesign: "a K562-active element mis-
  targeted to HepG2; ablate the erythroid/myeloid GATA1/TAL1/KLF1 grammar, strengthen hepatocyte
  HNF4A/FOXA2/CEBPA motifs, then re-gate." Named driver motifs + winning off-target + a concrete fix.
- Wet-lab reveal confirms: measured HepG2 -0.1, K562 +6.5 (fires 6.5-fold in the wrong cell). CisFalcon
  called the K562 off-target from sequence alone.
- Closes with the honest scale line: 93,435 independent designs, safest-half-first = 70% fewer failures,
  cross-lab AUROC 0.80, grounded in external wet-lab measurement.
This is the demo spine (show, not narrate). Recording is the user's action; the runnable artifact is done.
The agent layer's demonstrated value is ACTIONABLE MECHANISTIC DIAGNOSIS (which cell, which motifs, the fix),
not accuracy over the gate - report it that way per the ablation.

### Result 7: agent-layer ablation (audit fix #8, MEASURED not asserted)
`cisfalcon/run_ablation.py` -> `cisfalcon/data/gosai_designed/ablation.csv`. Question: does the 4-agent
layer improve the FAIL/PASS decision over the deterministic gate? Sample: 30 designs, stratified to
emphasize the decision boundary (|predicted gap| near zero, where the gate is least certain) plus clear
fails and passes, balanced on measured truth (12 fails / 18 passes).
- gate-only accuracy = 0.467; agent-flag accuracy (FAIL|BORDERLINE = flag) = 0.333.
- Agents differ from the gate on only 4/30 cases; ALL 4 flips WORSENED the call (cautious BORDERLINE
  flags on designs that actually passed). 0/4 improved it.
- Honest conclusion: the agent layer does NOT add classification accuracy over the gate (on the hardest
  slice it is slightly worse via over-flagging). The ranking signal is the model's. The agents' real,
  demonstrated value is the actionable mechanistic diagnosis in Result 6 (which off-target cell + which
  driver motifs + the redesign), grounded in external wet-lab-trained predictions - a thing a bare score
  and a generic AI reviewer cannot produce. We report agents as DIAGNOSIS, not accuracy.
- Framing caveat (no-slop): 0.467 is accuracy on a deliberately boundary-hard n=30 slice, NOT CisFalcon's
  operating performance. The headline remains the pooled ranking AUROC 0.80 over all 93,435 designs and the
  safest-half-first = 70%-fewer-failures triage number. This ablation only tests the marginal agent contribution.

### Result 8: independent re-derivation of the headline numbers (multi-corroborative check, 2026-07-10)
Re-computed the flagship numbers straight from the raw per-design scores (`designed_scored.csv`, n=93,435)
with a fresh Mann-Whitney rank-sum AUROC (no sklearn, not trusting the prior scoring script). Every number
matched to 4 decimals:
- cross-lab AUROC = **0.8013** (claim 0.8013) - exact.
- base fail rate = **6.2867%** (claim 6.29%); measured fails 5,874 / 93,435.
- safest-50%-first fail rate = **1.9072%** (claim 1.91%) = **69.7% fewer failures** (claim 70%).
- safest-70% fail rate = **2.5350%** (claim 2.54%); riskiest-10% PPV = **0.2681** (claim 0.27), 4.3x base.
The headline is reproducible by anyone from the committed scored CSV in one pass; the AUROC is not a
script artifact. This is the "independently re-derive any headline number from primary data" gate.

### Result 9: ScreenAudit REAL number on live BioGRID ORCS (generality, second domain; replaces the 55%)
ORCS key registered at orcsws.thebiogrid.org (a SEPARATE service from webservice.thebiogrid.org).
`cisfalcon/screenaudit/run_screenaudit.py` groups human screens by (CELL_LINE, PHENOTYPE, SCREEN_TYPE),
restricts to clean essentiality (cell-proliferation + pure Negative-Selection dropout) so the cross-screen
discordance measures lab/library/method reproducibility rather than biology, and for genes screened in
independent same-context screens measures published-hit agreement. Result over 4 cell lines (28 screens,
106 screen-pairs):
- **Published-hit agreement (primary): mean Jaccard 0.39, range 0.14 to 0.69.** HEK293-A 0.69 (reproducible),
  HT-29 0.57, T-47D 0.18, K-562 0.14 (severely discordant). Independent labs share only ~39% of their
  combined published hit calls for the same cell line's essential genes.
- Raw hit non-replication (asymmetric, hit-count-sensitive) = 47%, highly heterogeneous (18-76%).
- **Matched-hit-count control** (top-N by score, N = min hit count): confirms the discordant groups
  (K-562 matched-Jaccard 0.14, T-47D 0.21) are GENUINE gene-identity disagreement, not a threshold artifact.
  Honest caveat: the matched control ranks by SCORE.1, which is not always the screen's exact hit statistic,
  so it slightly overstates discord for the well-reproducing groups; the DIRECT published-hit Jaccard is the
  primary number. Do NOT headline the "62% matched" figure.
- Honest story: published CRISPR essentiality hit calls are method/lab-dependent and the fragility is HIGHLY
  VARIABLE; ScreenAudit's value is flagging WHICH published hit lists are trustworthy, computed on live ORCS,
  not cited. This is a real external-ground-truth number in a second, disjoint domain (the generality proof).
  Per-group JSON: `cisfalcon/screenaudit/screenaudit_result.json`.
