# Data and models

The trained models and large benchmark tables are not committed to this repo (they are
hundreds of MB). They come from public sources and are downloaded separately.

## Models (frozen atlas DHS64-MPRA activity models)

Castillo-Hair et al. 2025 (bioRxiv 2025.09.30.679565). Six fold models
(`dhs64_mpra_split{0,1,3}.h5` for the MPRA activity head, `dhs64_split{0,1,3}.h5` for the
accessibility head) from Zenodo record **17410822**. Place them in `models/`.

The deployed web tool (`webapp/backend`) needs the three `dhs64_mpra_split*.h5` files in
`models/`. The `Dockerfile` copies `models/` into the image; download the models before building.

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
validation MPRA, BODA/Malinois designs. The built benchmark (`data/gosai_designed/*.csv`) is
reproduced by `build_benchmark.py` + `score_designed.py`. The full 93,435-design cross-lab GPU
scoring run is the Kaggle kernel `ubaidullahshuaib/cisfalcon-gosai-crosslab`, reading the Kaggle
dataset `ubaidullahshuaib/cisfalcon-designed-benchmark`. The per-design activity and accessibility
specificity gaps used by the two-head ensemble (`data/gosai_designed/design_gaps.csv`, keyed by design
id) come from the Kaggle kernel `ubaidullahshuaib/cisfalcon-ensemble-gaps`; once committed, `ensemble_ci.py`
reproduces the ensemble and its paired CI with no GPU.

## Motifs

Transcription-factor PWMs are from JASPAR CORE vertebrates. A pre-fetched cache of the driver-TF
PWMs used by the tool ships in `webapp/backend/jaspar_cache/`, so the deployed tool needs no
JASPAR access at runtime. `webapp/backend/motifs.py` re-fetches any missing PWM from the JASPAR API.

## CRISPR screens (ScreenAudit)

Live from the BioGRID ORCS REST API (`orcsws.thebiogrid.org`), needs a free ORCS access key.
`screenaudit/run_screenaudit.py` computes the cross-screen hit-call discordance; the committed
`screenaudit/screenaudit_result.json` is the result over four cell lines.
