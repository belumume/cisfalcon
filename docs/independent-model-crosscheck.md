# Independent second-model cross-check: AlphaGenome vs CisFalcon

A fair question about CisFalcon: the ranking comes from one model family (the Castillo-Hair
DHS64-MPRA activity atlas). Does the specificity signal survive when a model of a completely
different lineage looks at the same designs?

To test this we cross-checked against **AlphaGenome** (Google DeepMind), a genomic
sequence-to-function model that was **never trained on any MPRA**, using its predicted
chromatin **accessibility** (DNASE) rather than MPRA activity. It is a different lab, a
different architecture, and a different objective (endogenous chromatin, not episomal MPRA
activity). It is not fully orthogonal evidence: both models learn regulatory grammar from
genomic data, so part of their agreement reflects shared biology (both recognize, for example,
that GATA1/TAL1 grammar drives K562). The honest claim is narrower and still useful: a model
built on different data, with a different objective, that never saw an MPRA, independently ranks
these designs' specificity in strong agreement with the MPRA-trained gate.

## Method

For each designed enhancer: embed the 200 bp sequence centered in a 16,384 bp N-padded
window (AlphaGenome's minimum input length), predict DNASE in K562 / HepG2 / SK-N-SH, take
the mean predicted signal over the central design region per cell, and define
`AlphaGenome gap = target-cell signal - max(off-target signal)`. A HepG2-target design that
truly fires in K562 gets a low or negative gap.

Reproduce with `python alphagenome_crosscheck.py` (needs a free AlphaGenome API key in
`ALPHA_GENOME_API_KEY`). Committed per-design scores: `data/gosai_designed/alphagenome_crosscheck.json`.

## Result (n = 240 designs, balanced across target cell and outcome)

| measure | value |
|---|---|
| AlphaGenome DNASE gap vs wet-lab `measured_fail`, AUROC | **0.688** (95% CI [0.620, 0.752], chance 0.50) |
| rank agreement with CisFalcon's independent predicted gap | **Spearman 0.80** (Pearson 0.82, n = 240) |
| sign check: fail designs vs pass designs (mean gap) | fail +0.006 vs pass +0.578 (pass > fail, correct direction) |

A different-architecture, never-saw-an-MPRA model agreeing at Spearman 0.80 is evidence that
CisFalcon's specificity signal is not an artifact of one model or one training objective. The
independent floor is the **0.69 AUROC** (not the 0.80 agreement): that is what a model built on
different data, used far outside its training distribution, achieves on its own against the
wet-lab labels, and it is well above chance (CI excludes 0.50).

## Honest boundaries

- This is a heavily **out-of-distribution** use of AlphaGenome: a bare designed episomal
  enhancer in a 16 kb N-padded window is unlike the genomic context it was trained on. The 0.69
  is a floor, not a ceiling; a purpose-built AlphaGenome setup would likely do better.
- AlphaGenome's 0.69 is lower than CisFalcon's cross-lab 0.80. The point of this cross-check is
  the **agreement** (0.80 Spearman) and the above-chance independent signal, not that
  AlphaGenome matches CisFalcon on this task.
- DNASE accessibility is a proxy for enhancer activity, not the MPRA readout itself.
- Reported on a stratified balanced subsample, not the full 93,435-design set.
