<!-- PITCH INTRO (voice this in your own words before publishing; the rest is factual/technical). -->

# CisFalcon

**Live tool: https://cisfalcon-lifesci.fly.dev/**

A pre-synthesis quality gate for AI-designed cell-type-specific enhancers. It reads a designed DNA
sequence and predicts, before any DNA is synthesized, whether the design will FAIL its intended
cell-type specificity in a wet-lab MPRA. Defensive use only: it ranks and flags designs so a lab can
deprioritize or redesign the riskiest before spending on synthesis. It does not design DNA.

Paste a designed enhancer, pick a target cell, and the tool returns the specificity verdict, a
per-cell activity chart, a JASPAR-grounded motif scan (which transcription-factor motifs are actually
present), a diagnosis from parallel Claude agents, and a closed loop: apply the prescribed motif edit
and re-score with the same external model to watch the predicted specificity gap move from failing to
passing. A batch mode ranks a whole set safest-first. No install, usable without the author present.

## What it does

Modern generative models design enhancers meant to be active in one target cell type and silent
elsewhere. Many still fire in the wrong cell. Synthesizing and validating one design costs roughly
$250-1000 and 2-4 weeks. CisFalcon scores the sequence first and predicts the failure, grounded in an
external measured-activity model rather than self-report.

Concretely, on a real design from an independent lab optimized to be HepG2-specific, CisFalcon reads
the sequence alone and predicts the most-active cell will be K562 (not the HepG2 target), a specificity
gap of -3.0 (predicted FAIL). The wet-lab measurement confirms it: that design barely touches HepG2 and
fires 6.5-fold in K562. See `demo.py`.

## Results (independently reproducible)

Cross-lab validation is the flagship: a frozen published activity model, scored on **93,435 designs from
a different lab, a different design model, and generators it never saw** (Gosai et al. 2024; BODA/Malinois
via AdaLead, Simulated Annealing, Hamiltonian MC, FastSeqProp), with zero sequence overlap with the
model's training data.

- **Cross-lab AUROC 0.8013, AUPRC 0.293** (n=93,435; base failure rate 6.29%). Beats trivial baselines
  decisively (GC-content 0.51, sequence-length 0.50, random 0.50).
- **Triage value (the operating point that matters):** rank designs by CisFalcon and synthesize the
  safest half first, and the specificity-failure rate in what you make drops from 6.29% to 1.91%, a
  **70% reduction in failures**. Flag the riskiest 10% for redesign and you capture 43% of all failures
  at 4.3x the base rate.
- Every headline number re-derives to 4 decimals directly from the committed per-design scores
  (`data/gosai_designed/designed_scored.csv`) with a plain rank-sum AUROC; it is not a pipeline artifact.

Honest boundaries, stated up front:

- CisFalcon is a **triage ranker**; it is not sold as a hard abort-gate. At the 6.29% base rate a hard
  gate has poor precision (PPV 0.24 at recall 0.5). Its value is prioritization, and every operating point
  is reported.
- It is a **heterogeneous ranker**: strong where failures are common (Hamiltonian MC AUROC 0.92), near
  coin-flip on the best-optimized generators (FastSeqProp 0.62, AdaLead 0.61). The honest within-generator
  macro-average is 0.73; the pooled 0.80 benefits from cross-generator separation. Lead with the range.
- The in-distribution number (matched, 3-cell, out-of-fold: AUROC 0.896) is a sanity check; the
  cross-lab result is the headline. The in-distribution number carries a residual train/test leakage
  caveat (the atlas CV split removes exact duplicates
  but not near-duplicate generative families). The cross-lab result is immune by construction.

Full methodology, every caveat, and the pre-committed vs post-hoc labels are in `PREREG.md`.

## How it works

1. **Gate (`gate.py`)** - the frozen atlas DHS64-MPRA activity models (Castillo-Hair et al. 2025), three
   shipped fold models, ensembled. Input is a 500 bp one-hot sequence; output is predicted log2FC across
   12 human cell lines. Nothing is trained or fine-tuned here.
2. **Transparent failure label** - a design FAILS specificity iff it is not most-active in its intended
   target: `gap = log2FC(target) - max(off-target log2FC); FAIL := gap <= 0`. Defined directly from the
   measured activity, independent of any opaque score.
3. **Agent layer (`verifier.py`)** - four Claude agents that turn a bare FAIL into a concrete mechanistic
   diagnosis: which off-target cell wins and which driver motifs to ablate or strengthen, grounded in the
   external wet-lab-trained predictions. A measured ablation (`run_ablation.py`) shows the agents do not
   improve classification accuracy over the deterministic gate; their value is the diagnosis a bare score
   and a generic AI reviewer cannot give. The ranking accuracy comes from the gate; the agents add the
   redesign guidance.

## Reproduce

```bash
# gate + demo (needs TensorFlow 2.14; models via the download script below)
python demo.py            # full run incl. the agent layer (needs an Anthropic API key)
python demo.py --no-agents # gate-only, no API
```

- The 12 fold models and the designed benchmark are large. The full cross-lab GPU run is the Kaggle
  kernel `ubaidullahshuaib/cisfalcon-gosai-crosslab`, reading the Kaggle dataset
  `ubaidullahshuaib/cisfalcon-designed-benchmark` (ships the benchmark CSV + the 3 MPRA fold models).
- Source data: atlas models (Zenodo 17410822), Gosai et al. cross-lab MPRA (Zenodo 10698014).
- Per-design scores used for every headline number: `data/gosai_designed/designed_scored.csv`.

## Generality

The same verifier pattern (a deterministic domain gate plus agent diagnosis, checked against external
measured ground truth) applies to a second, disjoint domain: `screenaudit/` re-derives and flags the
hit calls of published CRISPR screens (BioGRID ORCS). Run on live ORCS data across independent
essentiality (dropout) screens of the same cell line, published-hit agreement is heterogeneous and
often poor: mean Jaccard 0.39, from 0.69 (HEK293-A, reproducible) down to 0.14 (K-562, severely
discordant) over four cell lines. Independent labs share only about 39% of their combined hit calls,
and a matched-hit-count control confirms the worst cases are genuine gene-identity disagreement rather
than a threshold difference. The same harness produces a real external-ground-truth number in a second
domain, and flags which published hit lists are trustworthy.

## Safety

CisFalcon is a defensive falsifier. It predicts FAILURE to prevent wasted synthesis; it exposes no
generative optimization loop and creates no new design capability. The predictor is a public, already
released model.

## License

MIT. See `LICENSE`.
