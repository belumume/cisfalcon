# Within-neighbor generalization: does the specificity-gap paradigm extend past cross-lineage?

CisFalcon's flagship validates the specificity-gap idea at **cross-lineage** resolution (0.80 AUROC
on 93,435 Gosai/Tewhey designs across blood, liver, and neural, the maximally distant cell types).
The harder, more clinically relevant question for enhancer-AAV gene therapy is **within-tissue**:
does the same paradigm flag a design that misfires into a *neighboring* cell type in the same tissue?

This directory answers that with an **in-vivo** test, using a model **independent** of CisFalcon's gate.

## The test

- **Data (in-vivo ground truth):** Allen/BICCN EnhancerBenchmark (Ben-Simon et al., *Cell* 2025,
  github.com/AllenInstitute/EnhancerBenchmark). 532 mouse-cortex enhancers screened in vivo by
  enhancer-AAV, each labeled On-Target / Off-Target / Mixed / No-Labeling for a specific cortical
  subclass (Allen taxonomy: Sst, Vip, Pvalb, Lamp5, L2 to L6, **Astro, Oligo, OPC, Micro**), with the
  enhancer sequence. `kaggle_brain/enhancer_genomic_data.csv` (committed for provenance).
- **Scorer (independent):** DeepBICCN2 (CREsted, aertslab), a mouse-cortex snATAC *accessibility*
  CNN with per-cortical-subclass outputs (19 classes). Predicts from **sequence alone**. Independent
  of CisFalcon's DHS64-MPRA activity gate (different species, assay, lab) and of AlphaGenome.
- **Metric:** specificity gap = `pred[target_subclass] - max(pred[off_subclasses])`; AUROC of the gap
  separating in-vivo On-Target from Off-Target, with a 1000x paired bootstrap 95% CI.
- **Pre-registered** before the number was seen (see `../PREREG.md`): CI-excludes-0.50 means report as
  a generalization; CI-includes-0.50 means report the null. No tuning.

## Result (reproducible)

All four are now reported on the SAME 204 rows. The first version of this table scored the gap on
204 and the baselines on 211, because seven enhancers have no DeepBICCN2 head for their target
subclass and drop out of the gap. Comparing across different subsets is not like for like, and
`PREREG-ERRATA.md` retracted it on 2026-07-16.

| Predictor | AUROC (matched, n=204) | paired delta vs gap | 95% CI | type |
|---|---|---|---|---|
| **DeepBICCN2 specificity gap (sequence-only)** | **0.7056** | reference | | predicted |
| measured gini (accessibility specificity) | 0.7308 | +0.026 | [-0.066, +0.115] | measured |
| measured max-accessibility | 0.6872 | -0.018 | [-0.103, +0.067] | measured |
| GC content | 0.3130 | -0.390 | [-0.507, -0.270] | trivial |

Paired bootstrap, 2000 resamples, seed 0. Reproduce with `python within_neighbor/matched_paired.py`.

Incremental value (5-fold CV logistic): gap-only 0.701, accessibility-only 0.674, **gap+accessibility
0.704**. Combining measured accessibility with the sequence gap adds almost nothing, i.e. the sequence
gap already captures the accessibility signal.

**Honest read.** From sequence alone, before synthesis or any assay, the specificity-gap paradigm
predicts in-vivo cortical On-vs-Off-target at about 0.70, with a CI excluding chance. Matched and
paired against both measured accessibility features, the deltas span zero, so the sequence gap and
the measured features are **statistically indistinguishable** on this set rather than ranked. The
gap does decisively beat GC content, whose CI excludes zero.

An earlier version of this section said the gap fell **below** the best measured feature. That
claim came from the unmatched comparison and does not survive matching; it is retracted here and in
`PREREG-ERRATA.md`. Correcting it makes the result modestly stronger than pre-registered, which is
exactly why it is recorded rather than quietly applied.

This is a real, directional generalization to in-vivo within-cortex neighbor resolution. It is
**not** a demonstration that the sequence model beats measured assays. The value is that it needs
only the sequence, pre-synthesis.

**Caveats (stated, not hidden):**
- DeepBICCN2 predicts *accessibility*, a proxy for the in-vivo functional readout.
- The benchmark enhancers were selected from the BICCN cortex atlas that DeepBICCN2 trained on, so
  model and enhancer-selection share an accessibility basis. The **label** (in-vivo AAV On/Off) is an
  independent functional phenotype, which is what makes the test meaningful.
- Mouse cortex (the actual gene-therapy screen), not human.
- The finest resolution still ahead: a *functional* (not accessibility) within-cortex model would
  likely lift this above the measured-accessibility ceiling.

## Reproduce

```
# off-machine (Kaggle, internet on): fetches CREsted + DeepBICCN2 + the benchmark, scores, bootstraps
kaggle kernels push -p kaggle_brain/     # kernel: score_brain.py
kaggle kernels output <user>/cisfalcon-brain-within-neighbor -p kaggle_brain/out
# local: the trivial-baseline decomposition (pure pandas, no model)
python -c "import json;print(open('decomposition_baselines.json').read())"
```

Files: `gap_auroc.py` (route-agnostic harness, self-tested), `kaggle_brain/score_brain.py` (the run),
`result_brain_invivo.json` (full result), `decomposition_baselines.json` (local baseline check).
