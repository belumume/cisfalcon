# PREREG errata

`PREREG.md` is frozen and hash-locked (`PREREG.sha256`). Its value to a reviewer is that the
hash certifies the methodology was fixed before the numbers were read. Editing it in place to
correct a reporting error would destroy exactly that property, so corrections are recorded
here instead: dated, with the evidence, and reproducible from the committed data.

`PREREG.md` and its hash are unchanged.

---

## 2026-07-16 — Section 10 (within-tissue generalization): the baseline decomposition is not on the same subset

`PREREG.md` section 10 reports:

> RESULT: AUROC 0.706, 95% CI [0.631, 0.771] (n = 143 On, 68 Off; CI excludes 0.50). [...]
> HONEST DECOMPOSITION (same subset, so a reviewer sees exactly what a trivial feature buys):
> measured max-accessibility 0.698 [0.620, 0.777]; measured gini accessibility-specificity
> 0.746 [0.673, 0.815]; GC content 0.318 (does not explain it).

Two corrections. Both are verifiable from the committed per-enhancer data at
`within_neighbor/kaggle_brain/out/brain_gaps_with_baselines.csv`.

**1. The gap's n is 140 On / 64 Off (204), not 143 / 68 (211).**

The specificity gap is computable only where DeepBICCN2 has an output head for the enhancer's
target cortical subclass. Seven of the 211 hard-labelled rows have no such head and score NaN,
then drop (`within_neighbor/kaggle_brain/score_brain.py`: `gaps = np.full(len(df), np.nan)`,
later `m = ~np.isnan(vals)`). 143 / 68 is the label count, not the count the AUROC was computed
on. The artifact has always said so (`result_brain_invivo.json`, `on_vs_off.n_pos = 140`,
`n_neg = 64`); the prose did not.

**2. The decomposition is NOT on the same subset, and the parenthetical claiming it is is wrong.**

The measured baselines require no subclass mapping, so they were scored on all 211 rows while
the gap was scored on 204. Comparing them directly is not like-for-like. Matched to the gap's
204 rows and tested with a paired bootstrap (2000 resamples, seed 0), which is the same
instrument section 6 applies to the two-head ensemble lift:

| feature | as reported | matched to the gap's 204 | paired delta vs gap | 95% CI | verdict |
|---|---:|---:|---:|---|---|
| sequence gap (reference) | 0.7056 (n=204) | 0.7056 | — | — | — |
| gini accessibility-specificity | 0.7464 (n=211) | 0.7308 | +0.026 | [-0.066, +0.115] | **includes zero** |
| measured max-accessibility | 0.6983 (n=211) | 0.6872 | -0.018 | [-0.103, +0.067] | **includes zero** |
| GC content | 0.3183 (n=211) | 0.3130 | -0.390 | [-0.507, -0.270] | excludes zero |

**Consequence for section 10's interpretation.** It reads: "the paradigm predicts in-vivo
within-cortex On-vs-Off at a directional 0.70, comparable to measured accessibility and below
the best measured specificity feature." The first clause stands. The second does not: matched
and paired, the gini difference is +0.026 with a CI spanning zero, so the sequence gap and both
measured accessibility features are statistically indistinguishable on this set. They are not
ranked. The gap does decisively beat GC content (CI excludes zero).

This correction makes the result modestly stronger than pre-registered, which is precisely why
it is recorded here rather than quietly applied: the original was conceded against ourselves on
an unmatched comparison, and the correction has to be as auditable as the concession was.

**Unaffected.** The 5-fold CV incremental-value figures in the same section (gap-only 0.701,
accessibility-only 0.674, gap+accessibility 0.704) were already computed on the matched 204 and
stand exactly as reported. The headline AUROC 0.7056 and its CI [0.631, 0.771] are unchanged;
only the stated n and the baseline comparison are corrected.

**Reproduce:** `python within_neighbor/matched_paired.py`
