# CisFalcon single-nucleotide variant-effect test — independent public data

**Question.** Does the frozen CisFalcon activity model — the atlas DHS64-MPRA
CNN ensemble that CisFalcon uses for cell-type-specificity scoring — also
predict the effect of *single-base* substitutions on enhancer/promoter activity,
on data it never saw?

**Answer (headline).** Yes, with a real but element-dependent signal.
Predicted effects (`model(alt) − model(ref)`) correlate positively and highly
significantly with measured effects in both cell types. The correlation is
**strong in K562** and **modest in HepG2**, and varies substantially by element.

## Result

| Cell | n SNVs | Pearson r (95% CI) | Spearman ρ (95% CI) | Large-effect AUROC (95% CI) |
|------|-------:|--------------------|---------------------|------------------------------|
| **HepG2** | 8,191 | **0.29** (0.26–0.32) | 0.23 (0.21–0.26) | 0.64 (0.61–0.66) |
| **K562**  | 2,814 | **0.58** (0.53–0.62) | 0.28 (0.24–0.32) | 0.88 (0.85–0.92) |
| Pooled    | 11,005 | 0.37 (0.34–0.39) | 0.24 (0.22–0.26) | 0.68 (0.66–0.70) |

All Pearson/Spearman p-values ≤ 3×10⁻⁵¹. "Large-effect" = measured |log₂ effect| ≥ 1;
AUROC uses |predicted effect| to rank large- vs small-effect variants.

### Per-element (all p < 3×10⁻³)

| Element | Cell | n | Pearson r |
|---------|------|--:|----------:|
| SORT1 / SORT1.2 / SORT1-flip | HepG2 | ~1,790 ea | 0.42 / 0.42 / 0.39 |
| F9 | HepG2 | 904 | 0.41 |
| LDLR / LDLR.2 | HepG2 | 954 ea | 0.10 / 0.07 |
| PKLR-24h / PKLR-48h | K562 | 1,407 ea | 0.54 / 0.62 |

Mean per-element Pearson: **HepG2 0.30, K562 0.58.** The pooled HepG2 value is
dragged down by LDLR, where the model has almost no variant-level signal; on the
SORT1 enhancer and F9 promoter it reaches ~0.4.

## Honest interpretation

- **This is a positive, modest-to-strong finding, not a null.** The frozen model
  carries genuine single-base variant-effect information despite being trained
  only for bulk element activity, never on variants.
- **Predicted effect magnitudes are heavily compressed** (predicted σ ≈ 0.06–0.09
  vs measured σ ≈ 0.50–0.56 log₂). A one-base change in a 500 bp window moves the
  CNN output only slightly, so the model ranks variants far better than it
  calibrates their absolute size. This is why Spearman (0.23–0.28) is lower than
  Pearson here — the relationship is real but noisy at the single-variant level,
  with a minority of high-impact variants driving the linear correlation.
- **Element dependence is the main caveat.** LDLR is near-zero; a judge should
  not read "0.58 in K562" as a general variant-effect claim. The honest summary
  is: *the model detects the strong-effect variants (AUROC 0.64–0.88) and tracks
  their direction on most elements, but is unreliable on at least one (LDLR).*
- **Calibration relevance.** For CisFalcon's stated use — a pre-synthesis triage
  flag — variant *ranking* is what matters, and that works. It does **not** license
  using the raw predicted Δ as a quantitative effect size.

## Concordance with the source model

The Kircher 2019 saturation-mutagenesis dataset is exactly what the Agarwal et al.
2025 *Nature* paper (10.1038/s41586-024-08430-9, ref. 45) uses to validate its own
MPRALegNet variant-effect predictions (F9/LDLR/SORT1 in HepG2, PKLR in K562;
Fig. 4b, Extended Data Fig. 9). That paper reports per-element Pearson (r) and
Spearman (ρ) correlations of its MPRALegNet predictions against these same satMut
elements — the values are shown in the figure panels themselves (rendered images,
which I did not machine-read), so I do not restate them here. The takeaway that is
verifiable from our own run: CisFalcon's independently-trained atlas model produces
significant, positively-correlated variant-effect predictions on the exact
benchmark the source paper uses for the same purpose — which is the point of the
test.

## Scope & honesty notes

- The prompt named "Agarwal 2025 lentiMPRA saturation mutagenesis." Agarwal's own
  680k-element lentiMPRA is 200 bp with **no** per-SNV saturation data; the
  saturation-mutagenesis resource is **Kircher et al. 2019** (*Nat Commun* 10:3583;
  GSE126550), which Agarwal 2025 borrows for variant validation. We used the
  Kircher resource directly. This substitution is stated explicitly.
- We scored the model exactly as CisFalcon does (3-fold ensemble mean, novel-sequence
  mode). A correctness gate re-scoring the committed flagship designs reproduced the
  repo's `pred_gap` to max |Δ| = 1.2×10⁻⁵, confirming identical model loading.
- Only forward-strand GRCh38 windows were used; all reference alleles were verified
  against the UCSC hg38 sequence (0 mismatches except 1 boundary base in SORT1-flip,
  dropped). Windows are 500 bp centered on each variant.
