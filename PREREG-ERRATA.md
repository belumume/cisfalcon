# PREREG errata

`PREREG.md` is frozen and hash-locked (`PREREG.sha256`). Its value to a reviewer is that the
hash certifies the methodology was fixed before the numbers were read. Editing it in place to
correct a reporting error would destroy exactly that property, so corrections are recorded
here instead: dated, with the evidence, and reproducible from the committed data.

`PREREG.md`'s CONTENT is unchanged. Its recorded hash was corrected once, on 2026-08-03, because the original digest was computed over CRLF bytes and so reproduced only on Windows; the superseded digest is retained in `PREREG.sha256` so the change is traceable rather than silent. See the 2026-08-03 entry below.

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

---

## 2026-08-03 — Section 3 (triage value): the headline was never conditioned the way the AUROC was

`PREREG.md` section 3 reports:

> **Rank and make the safest first**: synthesizing the safest-ranked 50% cuts the specificity
> failure rate from 6.3% to 1.9% (70% fewer failures in what you make).
> **Flag the riskiest**: the flagged riskiest 2% are enriched 7.8x for real failures (PPV 0.49 vs
> 6.3% base); riskiest 10% captures 43% of all failures (4.3x).

Both figures are pooled. The pre-registration applies a careful conditioning discipline to the
AUROC (pooled 0.80, cell-prior-only 0.68, fully conditioned 0.66) and never applies it here.
Reproducible from the committed data with `triage_conditioning_check.py`, which re-derives the
published pooled figures to the digit as a positive control and refuses to print the conditioned
numbers if that assert fails.

| quantity | value |
|---|---|
| pooled safest-half reduction (as pre-registered) | 70% |
| **sequence-free stratum-prior null, pooled** | **91%** |
| within-(cell x generator) macro reduction | **41%** |
| pooled riskiest-2% enrichment (as pre-registered) | 7.74x |
| within-(cell x generator) macro enrichment | **2.59x** |

**The per-item signal is real**: 41% macro reduction and 2.59x macro enrichment with both priors
held constant, on the same 14 strata behind the pre-registered 0.66 joint AUROC.

**And the pooled headline does not measure it.** A rule with no access to sequence at all, ranking
only by each stratum's base rate, achieves a 91% pooled reduction, higher than the model's 70%. So
the pooled 70% and 7.74x cannot be cited as evidence of sequence-level discrimination in either
direction. A lab deploys one generator against one target cell, so 41% / 2.59x is the operating
point that describes deployment.

Per-stratum spread is wide and is reported rather than averaged away: reduction runs from 91%
(HepG2/hmc) down to 7% (SKNSH/sa_rep), and three strata fall below 1.0x enrichment (SKNSH/fsp 0.65x,
K562/sa_rep 0.60x, HepG2/sa_rep 0.90x), i.e. no better than random within those strata.

Repository sources (README, `verifier.py`, `docs/`, and the web app's `index.html`) were corrected
to lead with the conditioned figures and to disclose the 91% null. **The DEPLOYED tool at
cisfalcon-lifesci.fly.dev still serves the pre-correction numbers until the next deploy, and the
hero image in this repo is a screenshot of that pre-correction page.** Stating otherwise would
claim a correction that has not shipped. `PREREG.md` itself is untouched by this correction.

> **Status update, 2026-08-03 (later the same day).** The two sentences in bold above are no longer
> true and are kept as written rather than edited, because the point of this file is that its record
> is auditable. The deploy shipped: the live page now returns the conditioned figures (5 occurrences
> of "41%", 2 of "2.59", 3 of "sequence-free", 0 of "70% FEWER" and 0 of "7.8x"; fetched HTTP 200,
> 44,756 bytes), and the live batch calculator serves the corrected `const PPV = 0.198`. The hero
> image was re-captured from the corrected page by `docs/recapture_hero.py`, which asserts the
> corrected figures are present and the disowned ones absent before it writes the file.

---

## 2026-08-03 — Section 11 (closed-loop): the delta and its interval are on different scales

`PREREG.md` section 11 reports the powered equal-budget comparison as:

> Claude 26.8% vs fixed-rule 24.7%, delta +2.1 points, 95% CI [-0.04, +0.08], which INCLUDES ZERO.

The point estimate is in **percentage points** and the interval is in **proportions**. Read
literally the estimate sits about 26x outside its own interval, which is a contradiction a reader
derives from two numbers inside one parenthesis. Nothing about the analysis is wrong; only the
reporting units are mixed.

The committed artifact `data/gosai_designed/closed_loop_powered.json` records
`delta = 0.0206`, `delta_ci95 = [-0.0415, 0.0825]`, `n = 97`. On one scale that is:

| form | delta | 95% CI |
|---|---:|---|
| percentage points | +2.1 | [-4.2, +8.3] |
| proportions | +0.021 | [-0.042, +0.083] |

The conclusion is unchanged and was already stated correctly: the interval includes zero, so the
adaptive agent does not beat the fixed rule at equal budget. `README.md` and `HOW-BUILT.md` now
report percentage points on both halves; `PREREG.md` is frozen, so the correction lives here.

**Reproduce:** `python closed_loop_powered.py`, or read the committed JSON directly.

---

## 2026-08-03 — Section 12 (calibration): the reliability quote selects four of ten bins

`PREREG.md` reports the held-out reliability as "near-diagonal across bins" and quotes four of the
ten. The three bins with the largest gaps are not among the four. ECE 0.0031 is an n-weighted
marginal average and the lowest bin holds 36,912 of the 46,718 held-out designs (79%), so a very
small ECE is fully compatible with a large gap in the sparsely populated high-risk tail. All ten
bins, printed by `fit_calibration.py` (fit A, eval B):

| bin | n | predicted | observed |
|---|---:|---:|---:|
| [0.0, 0.1) | 36,912 | 0.029 | 0.029 |
| [0.1, 0.2) | 7,114 | 0.138 | 0.130 |
| [0.2, 0.3) | 983 | 0.238 | 0.228 |
| [0.3, 0.4) | 950 | 0.318 | 0.281 |
| [0.4, 0.5) | 355 | 0.420 | 0.420 |
| [0.5, 0.6) | 259 | 0.574 | 0.517 |
| [0.6, 0.7) | 42 | 0.696 | 0.619 |
| [0.7, 0.8) | 18 | 0.760 | 0.500 |
| [0.8, 0.9) | 42 | 0.854 | 0.690 |
| [0.9, 1.0) | 43 | 0.949 | 0.930 |

**Consequence.** The repeated illustration "a design labelled 70% risk fails close to 70% of the
time" is not supported at the region it names: the 0.6-0.7 bin is 0.696 predicted against 0.619
observed, and 0.7-0.8 is 0.760 against 0.500. Those bins hold 42 and 18 designs, so the observed
values are themselves noisy, which is the honest reading rather than a claim that the model is
badly miscalibrated up there. The 0.4-0.5 bin is exactly diagonal (0.420 / 0.420, n=355) and is now
the illustration used in `README.md`, `verifier.py`, `index.html` and `docs/SUBMISSION-SUMMARY.md`,
each stating that an absolute risk above about 0.6 is thinly measured. The ECE itself is unchanged.

Separately, `docs/cisfalcon_calibration.png` was titled with the fit-A/eval-B value 0.0029 while
every prose surface quoted 0.0031, the mean of the two directions, so a reader opening the cited
figure to check 0.0031 found the more favourable single direction. The figure now states both.

**Reproduce:** `python fit_calibration.py` (prints all ten bins and both ECE directions).

---

## 2026-08-03 — the integrity hash reproduced only on Windows

`PREREG.sha256` recorded `98b7cce2...ea2f`. That digest is over CRLF bytes. Git stores `PREREG.md`
with LF, so a Linux or macOS clone computed `ad77f065...e69d` and saw a mismatch against the
published value. Only a Windows checkout, where git converts to CRLF, could reproduce the recorded
hash.

This is the worst possible failure mode for a pre-registration, because a hash mismatch on a frozen
document reads as evidence that the document was edited after the fact, which is precisely the
accusation the freeze exists to pre-empt. Most reviewers would have hit it.

**The document was never edited.** The two byte streams are identical after normalising line
endings; converting either way and re-hashing reproduces the other digest exactly. Only the
representation differed, and with it the digest.

Fixed by pinning `PREREG.md` to LF in `.gitattributes`, so every platform checks out the same bytes,
and recording the LF digest `ad77f065...e69d`. The superseded CRLF digest is kept in the header of
`PREREG.sha256` so a reviewer who saw the old value can confirm what changed and why.

Verify: `sha256sum PREREG.md` should now print `ad77f065...e69d` on any platform.

Found by an independent blind re-audit of the repository, not by the authors.
