# CisFalcon: a pre-synthesis failure-risk triage for AI-designed regulatory DNA

**Built with Claude: Life Sciences (Builder track), solo, during the Jul 7 to 13 2026 window.**
**Live tool: https://cisfalcon-lifesci.fly.dev/**

Corrections and added analyses dated after that window, including the within-tissue matched/paired
retraction (2026-07-16) and the triage conditioning that produced the 41% / 2.59x / 91% figures this
document now leads with (2026-08-03), are recorded in
[`PREREG-ERRATA.md`](../PREREG-ERRATA.md). They post-date the build window and are labelled there
rather than folded silently into it, so a reader can tell which results were produced inside the
declared window and which are later corrections.

## What it does

**In one line:** rank your AI-designed enhancers safest-first and cut specificity failures by about 41% within one target cell and one generator, which is the deployment case (about 70% pooled across a mixed batch, but a sequence-free stratum-prior rule beats that pooled figure at 91%, so 41% is the honest one),
before any DNA is synthesized, validated on 93,435 designs from a different lab (leakage-immune cross-lab
AUROC 0.80). It flags the risky designs so a lab spends its bench budget on the ones most likely to hold up.

AI models now design synthetic enhancers, short pieces of DNA meant to switch a gene
on in one cell type and stay silent everywhere else. The design step is cheap; finding
out whether a design holds up is not. You synthesize the sequence, put it in cells, and
weeks later learn whether it was cell-type specific. A real fraction of designs fail that
test, and the failures cluster where the model is extrapolating past its training data.

CisFalcon reads an AI-designed enhancer and returns a calibrated failure-risk score
before synthesis. It is a triage ranker: it tells you which designs in a batch are risky,
so you spend a cheap orthogonal check on those before committing synthesis dollars to the
whole set. The deployed web tool takes a pasted design (or a whole batch), scores it, and
returns the verdict, a per-cell activity chart, and a motif scan, in one click, with no
install. Upload a whole CSV library of any size and it hands back a ranked CSV. A scientist
uses it without the author in the room.

Who it is for: labs that design cell-type-specific enhancers and currently have no pre-synthesis
QC step. That is the documented workflow of, for example, Sebastian Castillo-Hair's group at the
University of Washington, which built the atlas of AI-designed enhancers CisFalcon scores against,
and Sager Gosai and Ryan Tewhey's at the Jackson Laboratory, whose 93,435 published designs are
the validation set below. CisFalcon is built for that need and validated on their real published
data. It does not claim any of them has endorsed it; the endorsement is a conversation, the need
is already on the record.

## The number (leakage-immune, cross-lab)

The flagship result is measured on 93,435 independent designs from a different lab
(Gosai/Tewhey), a different activity model (Malinois), and generators the model was never
trained on. Overlap with CisFalcon's training data is zero, so the number cannot be
inflated by memorized sequences.

- Cross-lab AUROC 0.80 at predicting which designs fail wet-lab specificity. Trivial
  baselines on the same task: GC-content 0.51, sequence-length 0.50, random 0.50. Two
  intervals, both reported: the design-level 95% CI is [0.796, 0.807], and the honest
  cluster bootstrap over the 24 cell x generator strata is **[0.614, 0.895]**, wide by
  construction because the ranker is strong on failure-prone generators and near chance on
  the best-optimized ones (`bootstrap_ci.py`).
- The 0.80 is per-sequence signal, not just a shared cell-line prior. Within each target
  cell (the cell prior removed) the gate still separates failures at macro-AUROC 0.75; a
  cell-prior-only baseline (the target cell's base fail-rate, no sequence at all) reaches
  0.68. Removing both the cell and generator base-rates at once (the joint within-stratum
  AUROC) leaves genuine per-sequence discrimination of 0.66, still well above 0.50. So the
  pooled 0.80 is the deployment number for a mixed batch and 0.66 is the fully-conditioned
  per-sequence signal, both reported honestly (cell_prior_baseline.py).
- Matched apples-to-apples (both 3-cell, both out-of-fold), the in-distribution gate
  scores 0.896 and the cross-lab gate 0.801, about a 0.10 generalization gap, reported
  honestly.
- The operating point that matters is triage, not a hard gate. As a uniform abort-gate it
  is weak (PPV 0.24 at recall 0.5). As triage it is strong: flag the riskiest 2% of a
  batch and 49% of those truly fail, a 7.74x enrichment over the 6.29% base rate POOLED. Conditioned within (cell x generator), which is how a lab deploys it, that is 2.59x; a sequence-free stratum-prior rule beats the pooled safest-half headline (91% vs 70%), so the conditioned figures are the honest ones. On a
  200-design batch, under a full-committed-spend assumption of roughly $950 to $3,500 per
  pursued design (assumptions and both bases in docs/cisfalcon_triage_economics.csv,
  regenerated by `python economics_table.py`), the CONDITIONED 2.59x operating point averts
  an estimated **$458 to $1,796** net of a cheap orthogonal recheck on the flags. The pooled
  7.74x point gives $1,690 to $6,336, but that is an upper bound on the same disowned basis
  as the pooled 70%, so the conditioned range is the one to quote.
- The failure-risk probability the tool emits is genuinely calibrated, not asserted: it is fit by isotonic
  regression on the cross-lab (predicted-gap, measured-failure) pairs, with held-out calibration error
  (ECE) 0.0031 (mean of both split directions). Near the middle of the range it is close to exact (the 0.4-0.5 bin: 0.420 predicted, 0.420 observed, n=355); the high-risk tail is thinly measured, with the 0.6-0.7 bin at 0.696 predicted against 0.619 observed on n=42, so trust the ranking rather than an absolute number above ~0.6. The live tool is serving this
  map (`fit_calibration.py`; held-out reliability diagram in `docs/cisfalcon_calibration.png`).
- The signal does not rest on one model. A zero-parameter rank-average of the frozen activity head and a
  cheaper chromatin-accessibility head lifts the cross-lab AUROC to 0.806, with the paired 95% CI on the
  lift excluding zero (`ensemble_ci.py`). And a model of a completely different lineage agrees: DeepMind's
  AlphaGenome, never trained on any MPRA, ranks the same designs' specificity in agreement with CisFalcon
  at Spearman 0.80 and separates the wet-lab failures at AUROC 0.688 [95% CI 0.620, 0.752], even used far
  outside its training distribution (`docs/independent-model-crosscheck.md`). Two independent-lineage models
  agreeing is evidence the signal is not an artifact of one model family.
- The 93,435-design set is released as a public, leakage-immune benchmark for the pre-synthesis
  specificity-QC task the field has no shared test for (`BENCHMARK.md`): a transparent gap and fail label
  reconstructable from the measured activities, with reproducible stratified and leave-cell-out splits.
  CisFalcon's 0.80 is the reference baseline for other models to beat.

## Grounded diagnosis, and a closed loop

Every label is measured wet-lab activity from public MPRA assays, never a model's opinion.
A design fails when it is not most-active in its own intended target cell. That transparent
label is internally consistent with the atlas's own specificity score at r=0.82; both derive
from the same measured activity, so this is a consistency check, not independent validation.

The tool goes past a score. It scans the sequence against real JASPAR transcription-factor
motifs, so the diagnosis names the driver motifs that are actually present. On the real
failing example, it shows the sequence carries the K562 erythroid motifs (GATA1, TAL1,
KLF1, GATA2) and none of the HepG2 hepatocyte motifs. Then it closes the loop: it applies
the prescribed motif edit (remove the off-target grammar, install the target grammar) and
re-scores, moving the model's predicted specificity gap from failing (K562 -3.0) to passing
(HepG2 +1.0). This is a proposed fix, not wet-lab validation: the same model that flagged the
design re-scores the edit, so it is an in-silico consistency check that the diagnosis is
specific and the model responds sensibly, shown on one example, not proof the redesign works
in cells. What it demonstrates is that the diagnosis names a concrete, mechanistically grounded
edit, which a bare risk score cannot.

## Generality

The same verifier pattern (a deterministic domain gate checked against external measured
ground truth, plus a self-correcting agent layer) transfers to a second, disjoint domain.
ScreenAudit re-derives the hit calls of published CRISPR screens on live BioGRID ORCS data:
independent same-context essentiality screens agree on only a fraction of their hit calls
(mean Jaccard 0.39, range 0.14 to 0.69), and it flags which published hit lists are fragile.
The claim here is narrow and honest: the same audit pattern (a domain gate checked against
external measured ground truth, plus agent diagnosis) applies in a second, disjoint domain.
The Jaccard 0.39 is a measured concordance of published hit lists, not a second predictive
model; it shows the architecture generalizes, not that a second predictor was validated.

## Why it matters for disease

Cell-type-specific enhancers are the targeting element of enhancer-AAV gene therapy, one of the most
active routes to reach a single cell type in the brain, heart, and immune system without disturbing the
rest (2024-2025 toolkits target cortical interneurons, midbrain dopaminergic neurons, striatal cholinergic
neurons, and brain endothelial cells). The field's own bottleneck, stated plainly in those papers, is that
every novel enhancer-AAV combination needs detailed wet-lab validation and many designs fail specificity
(off-target expression, cell- and species-specific silencing). The size of that gap is on the record: in a
2025 enhancer-AAV screen only about half of candidate brain-cell enhancers (astrocyte 25 of 50, oligodendrocyte
21 of 43) showed their intended specificity in vivo, and the authors note current predictors have limited power
to forecast which will fail (Mich et al. 2025, eLife). That is exactly the spend CisFalcon triages
away: it flags the risky designs from sequence alone, before synthesis, so a lab commits its assay budget to
the designs most likely to hold up. It is a concrete instance of the compute-plus-wet-lab integration that
shortens the distance from a design to a defensible answer, on the disease areas Gladstone works in. This is
already validated on a brain cell, not promised: one of the three cross-lab target cells is the brain-derived
SKNSH neuroblastoma line, and on it CisFalcon flags specificity failures at leakage-immune AUROC 0.73 across
the 93,435 independent designs (K562 0.68, HepG2 0.83 are the other two). SKNSH is a neuroblastoma line,
the nearest brain-derived cell in the external panel rather than a primary neuron, so triage on a
neural-lineage design runs today and a primary-neuron MPRA is the honest next step.

## What it is not, and how Claude built it

It flags risk and abstains. It does not design enhancers de novo and runs no generative search; the
closed-loop fix is a bounded, deterministic, rule-based motif edit (ablate the named off-target motifs,
insert the target cell's canonical motifs from a fixed lookup) used as an in-silico consistency check on
the diagnosis, not a synthesis recommendation. A flag is not a guarantee.
In-distribution design already works well, so the value concentrates out-of-distribution,
where current models quietly break; it honestly loses power on the best-optimized generators
(per-generator AUROC 0.92 where failures are common, near 0.61 on the most heavily optimized),
and that boundary is reported.

Built with the full Claude stack. Claude Code built and deployed the tool: the gate, the
JASPAR motif grounding, the parallel-agent verifier (independent mechanism, precedent, and
adversary lenses plus a synthesizer), and the closed loop. Claude Science built the analysis
deliverables (this summary, the economics figure, the demo, the prepared Q&A) with a full
provenance chain, and then, in a fresh session, cloned this public repo from scratch and
re-derived every headline number to the decimal from the committed data alone (AUROC 0.8013,
joint per-sequence 0.662, calibration ECE 0.0031, triage 7.74x, ScreenAudit 0.394), which is
what surfaced the final reproducibility fixes. Both are the builder's own Claude stack, not a
third party; the value is a fresh-context, separate-harness reproduction, not external
independence.

On reproducibility, the two verification claims are kept distinct. The in-distribution pipeline
was reimplemented from scratch by a separate implementation on separate infrastructure and
reproduced its full-panel out-of-fold number (AUROC 0.911, n=1876, a different configuration
from the 0.896 matched-3-cell comparison) exactly, so the pipeline is deterministic and
reproducible, not an artifact of one codebase. The flagship cross-lab 0.80 is a single held-out
scoring run on the 93,435 independent designs; it was NOT reimplemented, and its credibility
rests on being leakage-immune (no sequence overlap with training, a different lab's model, unseen
generators), not on a second reimplementation.
