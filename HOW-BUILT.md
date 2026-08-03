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

Both model names are frozen experimental parameters rather than a dependency nobody has updated.
`PREREG.md` section 12 names the Opus 4.8 adjudicator as the arm under test, and every committed
agent-layer result was produced by this exact pair: the blind-judged panel-vs-single ablation, the
raw four-agent sample in `samples/`, and the powered closed-loop null. Repointing them at a newer
model would make all three unreproducible and would contradict a hash-locked document that cannot be
reissued, so a model change is a re-run plus a dated entry in
[`PREREG-ERRATA.md`](PREREG-ERRATA.md), not an edit to a constant.

The shape is deliberate: a fan-out to three reviewers, then a fan-in to one adjudicator (the
orchestrator-workers pattern). The lenses run in parallel and never see each other's output, so each
reasons from a distinct stance (mechanism, precedent, adversary) rather than converging on one. They
share the same gate report as evidence, so this is perspective diversity, not statistically
independent sampling; the adversary is a distinct critical stance whose job is to argue the verdict is
wrong, and the adjudicator is the only place the three reviews combine. The diagnosis runs on the raw
Messages API rather than an agent framework because it is a single bounded round with no tool use (the
tool-using loop is the optimizer below); it right-sizes the models: three Sonnet 5 workers, one Opus
4.8 adjudicator. The verdict is a structured
tool call (verdict, reasoning, and a model-reported confidence that is the adjudicator's own, not the
gate's calibrated probability), and the adjudicator visibly holds that confidence below certainty when
the adversary raises a valid calibration caveat, which you can watch on a flagged design in the live
tool.

![The live four-agent Claude verifier on a flagged design: three Sonnet 5 lenses (mechanism, precedent, adversary) run in parallel, then an Opus 4.8 adjudicator synthesizes them and holds its self-rated confidence below certainty because the adversary raised a valid out-of-distribution calibration caveat](docs/claude_diagnosis_live.png)

A raw, unedited response from this live call is committed at `samples/diagnose_flagship_sample.json`
(the flagship design, all three lens outputs plus the adjudicated verdict) so anyone can diff the real
four-agent output without running it.

We ran the ablation and report it straight (`run_ablation.py`): the agent layer does not improve
classification accuracy over the deterministic gate, and that is the point. The gate decides pass
or fail; the agents produce the diagnosis (which motif in which cell will make the design misfire,
and the edit that fixes it) and drive the closed-loop redesign. A bare AUROC cannot tell a scientist
why a design failed or how to repair it. The agent layer can, and that is the part a competitor
running the same public CNN cannot copy from a number alone.

And Claude closes the loop, where it is genuinely tool-using and load-bearing. The frozen gate scores;
it cannot optimize. `closed_loop.py` gives Claude (Opus 4.8) the gate as a tool: Claude proposes a
grounded motif edit (disrupt the predicted off-target cell's driver TFs, install the target cell's
driver TFs, all real JASPAR motifs, no invented sequence), calls the gate to re-score, reads the new
specificity gap, and iterates until the design passes or it aborts. That is a capability the frozen
gate alone does not have. We then powered the honest question rather than trusting a small number: on
97 failing designs at an equal 4-round budget, Claude's adaptive motif search rescues 26.8% versus a
fixed greedy rule's 24.7% (delta +2.1 percentage points, 95% CI [-4.2, +8.3] points, which includes zero). So the
adaptive agent does not beat a fixed rule at equal budget, and we report that null instead of the
underpowered n=20 count it replaces. It is also an in-silico consistency loop, the same frozen gate
that flagged the design agrees the rescue passes, not wet-lab validation. So the honest answer to
whether Claude is load-bearing or decorative for the science is neither over-claim: on the ranking
metric the frozen gate carries it, and on rescue rate the adaptive agent ties a fixed rule. What Claude
genuinely adds is the live agentic tool-use itself, a scientist can watch it drive a grounded
optimization loop, and the diverse-lens interpretation a bare score cannot give. `python closed_loop.py
--demo` shows one rescue live (the flagship, gap -3.0 to +0.4 over adaptive rounds, watching the
winning cell shift each round); `closed_loop_powered.py` reproduces the powered, equal-budget comparison.

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
and independently re-derived every committed number in the **pre-conditioning** release to the
decimal. The captured table is in [`docs/SCIENCE-AUDIT.md`](docs/SCIENCE-AUDIT.md); anyone can diff
it against the repo. Every row matched, and its verdict on the flagship was "honest, presented more
conservatively than it needs to be, no overclaim."

Scope, because the headline moved afterwards: the conditioned figures the README now leads with
(41% macro reduction, 2.59x macro enrichment, the ~90% sequence-free stratum-prior null) post-date
that audit and are **not** covered by it. The audit table marks the 2.59x row "added post-audit" and
has no row for the other two. Those are reproduced by `triage_conditioning_check.py`, which asserts
the audited pooled figures as a positive control first.

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
