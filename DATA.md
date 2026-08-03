# Data and models

The trained models and large benchmark tables are not committed to this repo (they are
hundreds of MB). They come from public sources and are downloaded separately.

## Models (frozen atlas DHS64-MPRA activity models)

Castillo-Hair et al. 2025 (bioRxiv 2025.09.30.679565), Zenodo record **17410822**, CC-BY 4.0.
Six fold models, about 503MB total. They are third-party artifacts, not trained here.

**Run `python fetch_models.py`.** It downloads all six, applies the rename below, and verifies
each against a pinned sha256. Nothing else is needed.

**The rename is mandatory and is the reason a manual download fails.** Zenodo ships different
filenames from the ones `gate.py` requires, so downloading exactly what the record offers and
placing it in `models/` produces a load failure with no hint why. An earlier version of this
section listed the post-rename names as if they were the Zenodo names, which is precisely the
trap.

| on Zenodo | must be saved as | head |
|---|---|---|
| `dhs64_mpra_data_split_0.h5` | `dhs64_mpra_split0.h5` | MPRA activity |
| `dhs64_mpra_data_split_1.h5` | `dhs64_mpra_split1.h5` | MPRA activity |
| `dhs64_mpra_data_split_3.h5` | `dhs64_mpra_split3.h5` | MPRA activity |
| `dhs64_data_split_0.h5` | `dhs64_split0.h5` | accessibility |
| `dhs64_data_split_1.h5` | `dhs64_split1.h5` | accessibility |
| `dhs64_data_split_3.h5` | `dhs64_split3.h5` | accessibility |

Verified against the live record on 2026-08-03: all six names above exist on it. The record also
carries `dhs733_*`, `dhs64_nofilt_*` and a pretrained zip, which this project does not use.

The deployed web tool (`webapp/backend`) needs the three `dhs64_mpra_split*.h5` files. The
`Dockerfile` does `COPY models/`, so `fetch_models.py` must run before `docker build`; the
weights are not in git and the build fails at that line without them.

## Reproducing the numbers (what needs what)

The flagship cross-lab AUROC 0.80 reproduces with NO downloads and NO GPU, straight from the
committed `data/gosai_designed/designed_scored.csv`, via `python reproduce_flagship.py`. That is
the headline number and it is self-contained in this repo.

The secondary in-distribution sanity-check numbers (matched 3-cell AUROC 0.896, full-panel 0.911,
accessibility 0.789 / 0.768) are also fully reproducible, they just need two public atlas input
files that are too large to redistribute here. Both live in the SAME Zenodo record as the models
(**17410822**, CC-BY 4.0): `enhancer_mpra_processed.tsv` (23.5 MB, the processed MPRA activity
table) and `mpra_data_splits.json` (2.0 MB, the train/test fold definitions). Download both into
`data/`, place the six model `.h5` files in `models/`, then run `python matched_indist_3cell.py`
(or `python molab_verify_port.py` for the from-scratch re-implementation behind the 0.911 number).
Scoring new sequences uses TensorFlow and benefits from a GPU. Nothing is author-private; every
input is public.

## Cross-lab designs (Gosai et al. 2024)

Gosai et al. 2024 (Nature 10.1038/s41586-024-08070-z), Zenodo record **10698014**, OL46
validation MPRA, BODA/Malinois designs.

**The cross-lab benchmark table was assembled off-repo and no committed script rebuilds it from
Zenodo.** `data/gosai_designed/designed_benchmark.csv` (93,435 rows; methods `al`, `al_uc`, `fsp`,
`fsp_uc`, `hmc`, `sa`, `sa_rep`, `sa_uc`) was assembled off-repo from the OL46 release and uploaded
as the Kaggle dataset `ubaidullahshuaib/cisfalcon-designed-benchmark`, which the GPU scoring kernel
`ubaidullahshuaib/cisfalcon-gosai-crosslab` then reads. `score_designed.py` CONSUMES that table; it
does not produce it. The table itself is committed here, so every no-GPU number re-derives from this
repo, but no committed script and no named kernel rebuilds it from the raw Zenodo archive, so that
one step is currently not reproducible by a third party. Stated plainly rather than implied.

**`build_benchmark.py` is a different builder and does not touch this file.** It turns the atlas
supplementary `media-10.xlsx` (not committed) into `data/benchmark.csv`, a separate in-distribution
benchmark: it filters to sources `{fsp, den, motif_embedding}`, keys off `log2FC_` columns, and
writes the columns `[id, target_cell, source, gap, fail, split, split_lco]`. An earlier version of
this section named it as the builder for the cross-lab table, which it provably is not. The
cross-lab splits come from `make_splits.py` (see [`BENCHMARK.md`](BENCHMARK.md)).

The per-design activity and accessibility specificity gaps used by the two-head ensemble come from
the Kaggle kernel `ubaidullahshuaib/cisfalcon-ensemble-gaps` and are committed here as
`data/gosai_designed/design_gaps.csv` (keyed by design id), so `ensemble_ci.py` reproduces the
ensemble and its paired CI with no GPU and no download.

## Motifs

Transcription-factor PWMs are from JASPAR CORE vertebrates. A pre-fetched cache of the driver-TF
PWMs used by the tool ships in `webapp/backend/jaspar_cache/`, so the deployed tool needs no
JASPAR access at runtime. `webapp/backend/motifs.py` re-fetches any missing PWM from the JASPAR API.

## CRISPR screens (ScreenAudit)

Live from the BioGRID ORCS REST API (`orcsws.thebiogrid.org`), needs a free ORCS access key.
`screenaudit/run_screenaudit.py` computes the cross-screen hit-call discordance; the committed
`screenaudit/screenaudit_result.json` is the result over four cell lines.
