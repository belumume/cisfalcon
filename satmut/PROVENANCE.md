# Provenance bundle — CisFalcon variant-effect test

Fully reproducible from public sources. No login required for any input.

## Data (ground truth)

- **Kircher et al. 2019**, *Saturation mutagenesis of twenty disease-associated
  regulatory elements at single base-pair resolution*, Nat Commun 10:3583.
  - GEO: **GSE126550** (PubMed 31395865)
  - Processed per-SNV effect table: `github.com/kircherlab/MPRA_SaturationMutagenesis`
    at commit `c5cadb46a3ec9bbeb8f678e8dc2b2335191f121b`, file `data/elements.tsv.gz`
    — sha256 `fec2eed91fe27af3aae07ebce2eca65e9bad4bb6abba5d8c27f478887dd7b134`.
    Column `Coefficient` = log₂ variant expression effect (linear-model fit).
  - Portal (interactive): `kircherlab.bihealth.org/satMutMPRA`
- **Elements used** (assigned to cell line per the repo's `mrkdown/about.md`):
  - HepG2: F9, LDLR, LDLR.2, SORT1, SORT1.2, SORT1-flip
  - K562: PKLR-24h, PKLR-48h
- **Reference sequence**: UCSC hg38 sequence API (`api.genome.ucsc.edu`), forward
  strand, 300 bp flanks. All ref alleles verified against genome.

## Model (under test)

Atlas DHS64-MPRA activity CNN (Castillo-Hair et al. 2025), 3-fold ensemble,
exactly as CisFalcon's `gate.py` uses it. Weights from **Zenodo record 17410822**:

| file (Zenodo) | renamed to | sha256 |
|---|---|---|
| `dhs64_mpra_data_split_0.h5` | `dhs64_mpra_split0.h5` | `09d85a34aa4fbfdd3e7f4d7e55cbe5938c4bad85a193203e73717fc4b800582a` |
| `dhs64_mpra_data_split_1.h5` | `dhs64_mpra_split1.h5` | `8c4649bb87b42c5f144bbea9784af98812aac10b8f70e1d3794b07dfb68c6fb4` |
| `dhs64_mpra_data_split_3.h5` | `dhs64_mpra_split3.h5` | `b31eed0df85495a5f1e4136e40af0c32ccaeed4563666f52aa07d9c2e9797f5e` |

Encoding/output convention (from `gate.py`): 500 bp left-padded one-hot (A,C,G,T),
output = mean over 3 folds, 12-cell vector, **HepG2 = index 6, K562 = index 7**.

## Method

1. `build_windows.py` — reconstruct 500 bp ref window centered on each SNV; make
   alt window by single-base substitution. Predicted effect = ensemble activity
   at the variant's own cell for alt − ref.
2. `score_variants_gpu.py` — 3-fold ensemble scoring (run on Modal A10G GPU;
   TF 2.14 on a CUDA 11.8 **-devel** image — the -runtime image lacks `ptxas`,
   causing a JIT-compilation failure).
3. `correlate.py` — Pearson, Spearman, large-effect AUROC (|log₂|≥1), per cell,
   pooled, and per element; 2,000-sample bootstrap 95% CIs.

**Correctness gate**: re-scoring the committed flagship Gosai/Tewhey designs with
this model loading reproduced the repo's `pred_gap` to max |Δ| = 1.2×10⁻⁵.

## Reproduce the K562 headline (r = 0.58, large-effect AUROC = 0.88)

One line, from `variant_scored.csv.gz` alone (pandas + scipy + scikit-learn):

```bash
python -c "import pandas as pd; from scipy.stats import pearsonr; from sklearn.metrics import roc_auc_score; d=pd.read_csv('data/variant_scored.csv.gz'); d=d[d.cell=='K562']; print('n=%d  Pearson r=%.4f  large-effect AUROC=%.4f' % (len(d), pearsonr(d.pred_effect,d.measured_effect)[0], roc_auc_score((d.measured_effect.abs()>=1).astype(int), d.pred_effect.abs())))"
# -> n=2814  Pearson r=0.5781  large-effect AUROC=0.8829
```

Inputs: `pred_effect` (CisFalcon ensemble alt−ref activity at the K562 index) and
`measured_effect` (Kircher satMut log₂ coefficient); large-effect label = measured
|log₂| ≥ 1; AUROC ranks large vs small effects by |predicted|.

## Files in this bundle

Paths are given as they exist in the repository. An earlier version of this list named six files
that are not at the paths it stated, so a reviewer opening `satmut/` to check the provenance behind
the variant-effect claim found most of it apparently absent. Three were merely elsewhere or renamed,
and three are regenerable outputs that are deliberately not committed.

Committed, in `satmut/`:
- `build_windows.py`, `score_variants_gpu.py`, `correlate.py` — the pipeline
- `PROVENANCE.md`, `FINDING.md` — this file and the written finding

Committed, elsewhere in the repo:
- `data/variant_scored.csv.gz` — windows plus predicted activities and effects. In `data/`, not
  `satmut/`; `correlate.py` resolves it against the repo root so it runs from any directory.
- `docs/variant_effect_scatter.png` and `docs/variant_effect_per_element.png` — the two figures,
  under those names rather than the `fig_` prefix this list used to give them.

Regenerable, NOT committed, with the command that produces each:
- `variant_windows.csv.gz` — the 11,005 ref/alt 500 bp windows plus measured effects.
  `python satmut/build_windows.py`
- `satmut/correlation_summary.csv` and `satmut/correlation_per_element.csv` — the results tables.
  `python satmut/correlate.py`, which writes them beside the script.

Note the row-count caveat in `FINDING.md`: those 11,005 rows cover 5,065 distinct SNVs, because the
same variant is assayed in more than one element.
