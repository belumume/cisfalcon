# Claude Science independent audit: re-derivation table

A separate Claude Science session, on separate infrastructure, cloned this public repository from
scratch, read the scoring / baseline / operating-point / verifier scripts plus
`data/gosai_designed/designed_scored.csv`, and independently re-derived every committed number. This
is the artifact behind the README's "independently reproduced by a separate Claude Science session"
line. Every captured row matched to the decimal.

| Claim | Repo value | Science re-derivation | Match |
|---|---|---|---|
| Pooled cross-lab AUROC | 0.8013 | 0.8013 | yes |
| Cross-lab AUPRC | 0.293 | 0.2929 (random 0.0629, 4.66x) | yes |
| Base failure rate | 6.29% | 6.2867% (5,874 / 93,435) | yes |
| Cell-prior-only AUROC | 0.678 | 0.6784 | yes |
| Within-cell macro AUROC | 0.747 | 0.7473 (HepG2 .833 / SKNSH .731 / K562 .678) | yes |
| Joint (cell x method) macro | 0.662 | 0.6624 (14 strata) | yes |
| Per-generator macro | 0.726 | 0.726 (hmc .922, sa .776, sa_rep .695, fsp .625, al .613) | yes |
| GC / length baselines | 0.51 / 0.50 | 0.5113 / 0.5000 | yes |
| Riskiest-2% PPV / enrichment | 0.49 / 7.8x | 0.4872 / 7.75x | yes |
| Riskiest-10% capture / lift | 43% / 4.3x | 42.6% / 4.26x | yes |
| Safest-50% failure rate | 1.91% | 1.9072% (69.7% reduction) | yes |

Science's verdict on the flagship: honest, presented more conservatively than it needs to be, no
overclaim. In the same audit it independently reproduced the variant-effect extension headline (see
`docs/variant-effect-extension.md`) and caught a reproduction-claim conflation that an earlier
self-review had missed. The full account of the Claude Code and Claude Science collaboration is in
[`HOW-BUILT.md`](../HOW-BUILT.md).
