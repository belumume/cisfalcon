# A reliability map of AI enhancer-design methods

A finding produced with CisFalcon from the committed data, no new model and no new wet-lab.

**What is ours and what is not.** The specificity-failure labels are Gosai/Tewhey 2024 wet-lab MPRA
measurements. The contribution here is two things a scattered dataset does not give you on its own:
a systematic per-method and per-target-cell reliability map, and a demonstration that a single
frozen cross-lab verifier predicts where those failures cluster (pooled cross-lab AUROC 0.80,
orientation-verified). Reproduce with `python findings_failure_modes.py`; figure in
`docs/failure_modes.png`.

## Finding 1: design methods vary about 30x in specificity-failure rate

| AI design method | specificity-failure rate | CisFalcon AUROC |
|---|---|---|
| Hamiltonian MC | 22.3% | 0.922 |
| Simulated Annealing (replicate) | 16.9% | 0.695 |
| Simulated Annealing | 2.5% | 0.776 |
| AdaLead | 2.3% | 0.613 |
| FastSeqProp | 0.7% | 0.625 |

Scope: these are the five main generator codes, covering 92,537 of the 93,435 designs. The benchmark
carries three more, the low-n unconstrained variants `al_uc`, `fsp_uc` and `sa_uc` (298 / 300 / 300
designs, measured failure 1.01% / 0.00% / 0.00%), excluded here as underpowered. The 30x is the
spread over the five main codes (22.28 / 0.68 = 32.7x); across all eight it is unbounded, since two
of the small codes record zero failures.

A design's odds of firing in the wrong cell depend heavily on how it was generated, from under 1%
to over 22%. A lab picking a generator is also picking a specificity-failure rate, and today that
choice is usually made blind.

## Finding 2: the disease-relevant targets are the hardest

| Target cell | specificity-failure rate |
|---|---|
| SK-N-SH (brain) | 10.1% |
| HepG2 (liver) | 8.2% |
| K562 (blood) | 0.6% |

Designs for brain and liver cells, the two most gene-therapy-relevant targets here, fail about 14 to
17 times more often than blood-cell designs (10.06 / 0.59 = 17.0x for brain, 8.20 / 0.59 = 13.9x for
liver, from `data/gosai_designed/designed_scored.csv`). The worst single combination is Hamiltonian-MC-designed
brain enhancers, where roughly **1 in 3 fails** (32.7%). This is exactly where a pre-synthesis
verifier earns its cost: the hardest, most clinically important designs are the ones most likely to
be quietly broken.

## Finding 3: the verifier is strongest where the failures are

CisFalcon's per-method discrimination is highest (AUROC 0.922) on Hamiltonian MC, the method that
fails most (22.3%), and it stays useful across every generator. A verifier that were only good on
the safe methods would not matter; this one is sharpest on the failure-prone one.

## Why it matters

The field has many enhancer generators and, before this, no systematic account of which ones fail,
on which targets, and by how much. This map lets a lab anticipate specificity risk from the design
method and the target cell before spending a dollar, and it is the reliability layer a
frozen-model verifier makes possible.
