# How CisFalcon was built with Claude

CisFalcon was built end to end with Claude Code and independently audited with Claude Science.
Two Claude agents working against each other, one building and one checking, is the part worth
reading.

## The verifier is a real multi-agent system, and it is honest about what the agents do

The core gate is a frozen published activity CNN: deterministic, fast, and the thing that carries
the cross-lab AUROC. On top of it, `verifier.py` runs a real Claude multi-agent layer on a flagged
design:

- Three **Claude Sonnet 5** reasoning lenses run in parallel: a **mechanism** lens (which
  transcription-factor motifs and which cell the design drives), a **precedent** lens (grounding the
  risk in the measured benchmark), and an **adversary** lens (arguing the gate's verdict could be
  wrong).
- A **Claude Opus 4.8** adjudicator synthesizes the gate report and the three independent reviews
  into one calibrated verdict.

We ran the ablation and report it straight (`run_ablation.py`): the agent layer does not improve
classification accuracy over the deterministic gate, and that is the point. The gate decides pass
or fail; the agents produce the diagnosis (which motif in which cell will make the design misfire,
and the edit that fixes it) and drive the closed-loop redesign. A bare AUROC cannot tell a scientist
why a design failed or how to repair it. The agent layer can, and that is the part a competitor
running the same public CNN cannot copy from a number alone.

## The builder ran under epistemic hooks it wrote for itself

The discipline on the agent doing the building is the most unusual part of the Claude Code use.
Three custom Claude Code hooks ran on the build session throughout:

- **anti-cope** (Stop hook): blocks the session from ending a turn on an effort-avoidance
  rationalization ("diminishing returns", "not viable", "future work") unless it names a real
  physical constraint.
- **compute-guard** (PreToolUse hook): denies heavy ML inference on the laptop and redirects it
  off-machine, so a CNN scoring pass cannot quietly thrash the local machine for an hour and a half.
- **anti-drop** (Stop hook): captures every deferred commitment into a durable ledger that survives
  context compaction, so nothing promised is lost across a long multi-session build.

These are epistemic scaffolding on the agent itself. They are a large part of why the science got
over-solved instead of settled at the first passing number.

## Claude Science was the independent auditor and a second researcher

A separate Claude Science session, on separate infrastructure, cloned the public repo from scratch
and independently re-derived every committed number to the decimal. The captured table is in
[`docs/SCIENCE-AUDIT.md`](docs/SCIENCE-AUDIT.md); a judge can diff it against the repo. Every row
matched, and its verdict on the flagship was "honest, presented more conservatively than it needs
to be, no overclaim."

Two things it did that a linter cannot:

1. It **caught a real reproduction-claim conflation** that Claude Code's own self-review had missed
   (an in-distribution reimplementation was being described as a cross-lab independent reproduction),
   and made us correct the claim in the repo.
2. It **autonomously ran a research extension** we had not asked it to finish: it scored the frozen
   model against an independent saturation-mutagenesis benchmark (Kircher 2019) to test single-base
   variant-effect prediction (K562 large-effect AUROC 0.88), and it **recovered from its own GPU
   environment failure** to get there (a CUDA runtime image missing `ptxas`, which it diagnosed and
   fixed by rebuilding on the devel base). Claude Code then re-verified that headline four independent
   ways before it entered the submission. See [`docs/variant-effect-extension.md`](docs/variant-effect-extension.md).

## Off-machine, so the laptop stayed a control plane

Every heavy GPU pass (scoring 93,435 designs, the variant-effect run) ran off-machine on Kaggle and
molab. The laptop orchestrated and never did the heavy compute; the compute-guard hook enforced it.

## Where they mattered most

Claude Code built and deployed the live tool and runs the multi-agent diagnosis layer inside it.
Claude Science checked the science from the outside and pushed it further than the build session
did alone. Two Claude agents cross-examining each other's work, each catching what the other missed,
is the honest answer to how we used Claude.
