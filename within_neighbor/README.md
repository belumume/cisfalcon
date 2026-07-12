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

| Predictor | AUROC | 95% CI | type |
|---|---|---|---|
| **DeepBICCN2 specificity gap (sequence-only)** | **0.706** | [0.631, 0.771] | predicted |
| measured max-accessibility | 0.698 | [0.620, 0.777] | measured |
| measured gini (accessibility specificity) | 0.746 | [0.673, 0.815] | measured |
| GC content | 0.318 | [0.240, 0.401] | trivial |

Incremental value (5-fold CV logistic): gap-only 0.701, accessibility-only 0.674, **gap+accessibility
0.704**. Combining measured accessibility with the sequence gap adds almost nothing, i.e. the sequence
gap already captures the accessibility signal.

**Honest read.** From sequence alone, before synthesis or any assay, the specificity-gap paradigm
predicts in-vivo cortical On-vs-Off-target at about 0.70 (CI excludes chance), **comparable to** what
you get from having already measured the enhancer's accessibility, and **below** the best measured
cross-cell specificity feature (gini, 0.75). So it is a real, honest, *directional* generalization to
in-vivo within-cortex neighbor resolution. It is **not** a demonstration that the sequence model beats
measured assays. The value is that it needs only the sequence, pre-synthesis.

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
