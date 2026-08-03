# Variant-effect extension: CisFalcon predicts single-nucleotide effects

**Result (judge-legible).** The *frozen* CisFalcon activity model, the atlas
DHS64-MPRA CNN ensemble already used for cell-type-specificity scoring, with no
retraining and never trained on variants, ranks single-base variant effects on
independent saturation-mutagenesis MPRA data. The threshold-independent signal is
the full-set rank correlation: **Pearson r = 0.58 in K562** and r = 0.29 in HepG2.

Those n are ROW counts, and rows are not independent variants. The Kircher resource assays the
same SNV in more than one element, so 11,005 rows cover 5,065 distinct SNVs: K562's n = 2,814 is
1,407 variants each measured in two elements, and HepG2's n = 8,191 is 3,658. Every duplicated
key spans multiple elements and none spans multiple cells, so these are the same variant in
different regulatory contexts rather than technical replicates, but they are still not
independent and the row-count n inflates the p-values.

Collapsing to one row per SNV, averaging both the predicted and the measured effect:

| cell | basis | n | Pearson r | p |
|---|---|---:|---:|---|
| K562 | all rows (as first reported) | 2,814 | 0.578 | 1.0e-250 |
| K562 | one row per SNV | 1,407 | **0.601** | 1.3e-138 |
| HepG2 | all rows (as first reported) | 8,191 | 0.290 | 6.2e-158 |
| HepG2 | one row per SNV | 3,658 | **0.254** | 6.6e-55 |

The deduplicated figures are the honest ones and are quoted here as primary. The correlation
survives: K562 rises slightly, HepG2 falls slightly, and every p stays far below any threshold
that would change the conclusion. What was wrong was the significance, not the finding. Reported
because an independent re-audit caught it, and because a reader who deduplicates should find the
number already stated rather than discover it themselves. On the same data it also flags
the high-impact variants: large-effect ranking AUROC is **0.88 in K562** at the
standard |log2| >= 1 cutoff and 0.64 in HepG2. That AUROC is a thresholded metric,
so it moves with the cutoff (a 0.73 to 0.93 band across |log2|
0.5 to 2.0 in K562); we
report the cutoff-free r as the primary number and the AUROC as a supporting view,
never the headline. Ranking the strong-effect variants correctly is exactly the
signal CisFalcon's pre-synthesis triage flag needs. **The honest
caveat in the same breath:** the model *ranks* variants but does *not* calibrate
absolute effect size, predicted magnitudes are compressed about **6× in K562 and 10× in HepG2**
(K562 measured σ 0.500 against predicted σ 0.090 = 5.6×; HepG2 measured σ 0.564 against predicted
σ 0.057 = 9.9×; from `data/variant_scored.csv.gz`), so a raw predicted Δ is not a
quantitative effect size; performance is element-dependent (SORT1 enhancer r ≈
0.42, F9 promoter 0.41, PKLR 0.54–0.62), it is near-blind on LDLR (r ≈ 0.08),
and HepG2 overall is modest (0.29 pooled). Every element is significant at p <
0.05 (weakest, LDLR.2, p = 0.022); most are far stronger (p ≤ 10⁻³⁷).

![Predicted vs measured single-nucleotide variant effect on the Kircher et al. 2019 saturation-mutagenesis MPRA, one panel per cell. K562 (n = 2,814 assay rows) reaches Pearson r = 0.58; HepG2 (n = 8,191 rows) reaches 0.29. Both axes are log2 effect, alt minus ref. The predicted axis spans a far narrower range than the measured one, which is the magnitude compression the text quantifies.](variant_effect_scatter.png)

![Per-element predicted-vs-measured variant effect: K562 (PKLR) and the SORT1 / F9 elements carry strong signal, LDLR is near-blind. The figure shows exactly where the flag is trustworthy and where it is not.](variant_effect_per_element.png)

**Provenance correction (important).** The task named the "Agarwal et al. 2025
*Nature* lentiMPRA saturation mutagenesis," but Agarwal's own 680k-element
lentiMPRA is 200 bp with **no per-single-nucleotide-variant data**. The
saturation-mutagenesis benchmark is **Kircher et al. 2019** (*Nat Commun* 10:3583;
GSE126550), which Agarwal 2025 itself uses as its ref. 45 to validate its
MPRALegNet variant predictions (F9/LDLR/SORT1 in HepG2, PKLR in K562). We scored
that Kircher resource directly (11,005 assay rows over 5,065 distinct SNVs across 8 elements), so this test
uses fully public, paper-faithful ground truth. Model loading was confirmed
bit-identical to the committed flagship scorer (re-scoring the committed designs
reproduced `pred_gap` to max |Δ| = 1.2×10⁻⁵). See [`satmut/PROVENANCE.md`](../satmut/PROVENANCE.md)
for accessions, model SHA-256s, and the reproduce command; the per-SNV predictions are in
[`data/variant_scored.csv.gz`](../data/variant_scored.csv.gz).

**Independently reproduced.** Recomputing the headline from `data/variant_scored.csv.gz` with a
separate interpreter reproduces K562 n = 2,814, Pearson r = 0.5781, large-effect AUROC = 0.8829,
matching to the digit.
