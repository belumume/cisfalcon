# CisFalcon: a pre-synthesis failure-risk triage for AI-designed regulatory DNA

**Built with Claude: Life Sciences (Builder track), solo, Jul 7 to 13 2026.**
**Live tool: https://cisfalcon-lifesci.fly.dev/**

## What it does

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
install. A scientist uses it without the author in the room.

## The number (leakage-immune, cross-lab)

The flagship result is measured on 93,435 independent designs from a different lab
(Gosai/Tewhey), a different activity model (Malinois), and generators the model was never
trained on. Overlap with CisFalcon's training data is zero, so the number cannot be
inflated by memorized sequences.

- Cross-lab AUROC 0.80 at predicting which designs fail wet-lab specificity. Trivial
  baselines on the same task: GC-content 0.51, sequence-length 0.50, random 0.50.
- Matched apples-to-apples (both 3-cell, both out-of-fold), the in-distribution gate
  scores 0.896 and the cross-lab gate 0.801, about a 0.10 generalization gap, reported
  honestly.
- The operating point that matters is triage, not a hard gate. As a uniform abort-gate it
  is weak (PPV 0.24 at recall 0.5). As triage it is strong: flag the riskiest 2% of a
  batch and 49% of those truly fail, a 7.8x enrichment over the 6.29% base rate. On a
  200-design batch that averts an estimated $1,700 to $6,400 in synthesis and validation
  spend, net of a cheap orthogonal recheck.

## Grounded diagnosis, and a closed loop

Every label is measured wet-lab activity from public MPRA assays, never a model's opinion.
A design fails when it is not most-active in its own intended target cell. That transparent
label agrees with the atlas's own published specificity score at r=0.82.

The tool goes past a score. It scans the sequence against real JASPAR transcription-factor
motifs, so the diagnosis names the driver motifs that are actually present. On the real
failing example, it shows the sequence carries the K562 erythroid motifs (GATA1, TAL1,
KLF1, GATA2) and none of the HepG2 hepatocyte motifs. Then it closes the loop: it applies
the prescribed motif edit (remove the off-target grammar, install the target grammar) and
re-scores with the same external model, moving the predicted specificity gap from failing
(K562, -3.0) to passing (HepG2, +1.0). That is AI grounded in measured biology fixing the
design, not a model narrating a score.

## Generality

The same verifier pattern (a deterministic domain gate checked against external measured
ground truth, plus a self-correcting agent layer) transfers to a second, disjoint domain.
ScreenAudit re-derives the hit calls of published CRISPR screens on live BioGRID ORCS data:
independent same-context essentiality screens agree on only a fraction of their hit calls
(mean Jaccard 0.39, range 0.14 to 0.69), and it flags which published hit lists are fragile.
One architecture, two independent biological domains, both with a real computed number.

## What it is not, and how Claude built it

It flags risk and abstains. It does not design the enhancer, and a flag is not a guarantee.
In-distribution design already works well, so the value concentrates out-of-distribution,
where current models quietly break; it honestly loses power on the best-optimized generators
(per-generator AUROC 0.92 where failures are common, near 0.61 on the most heavily optimized),
and that boundary is reported.

Built with the full Claude stack. Claude Code built and deployed the tool: the gate, the
JASPAR motif grounding, the parallel-agent verifier (independent mechanism, precedent, and
adversary lenses plus a synthesizer), and the closed loop. Claude Science built the analysis
deliverables (this summary, the economics figure, the demo, the prepared Q&A) with a full
provenance chain, and its reviewer independently audited the claims.

On reproducibility, the two verification claims are kept distinct. The in-distribution pipeline
was independently reimplemented from scratch on separate infrastructure and reproduced its
out-of-fold number (AUROC 0.911) exactly, so that result is a property of the model and data,
not of one implementation. The flagship cross-lab 0.80 is a single held-out scoring run on the
93,435 independent designs; its credibility rests on being leakage-immune (zero training
overlap, a different lab's model, unseen generators), not on a second reimplementation.
