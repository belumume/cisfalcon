# Data and models

The trained models and large benchmark tables are not committed to this repo (they are
hundreds of MB). They come from public sources and are downloaded separately.

## Models (frozen atlas DHS64-MPRA activity models)

Castillo-Hair et al. 2025 (bioRxiv 2025.09.30.679565). Six fold models
(`dhs64_mpra_split{0,1,3}.h5` for the MPRA activity head, `dhs64_split{0,1,3}.h5` for the
accessibility head) from Zenodo record **17410822**. Place them in `models/`.

The deployed web tool (`webapp/backend`) needs the three `dhs64_mpra_split*.h5` files in
`models/`. The `Dockerfile` copies `models/` into the image; download the models before building.

## Cross-lab designs (Gosai et al. 2024)

Gosai et al. 2024 (Nature 10.1038/s41586-024-08070-z), Zenodo record **10698014**, OL46
validation MPRA, BODA/Malinois designs. The built benchmark (`data/gosai_designed/*.csv`) is
reproduced by `build_benchmark.py` + `score_designed.py`. The full 93,435-design cross-lab GPU
scoring run is the Kaggle kernel `ubaidullahshuaib/cisfalcon-gosai-crosslab`, reading the Kaggle
dataset `ubaidullahshuaib/cisfalcon-designed-benchmark`.

## Motifs

Transcription-factor PWMs are from JASPAR CORE vertebrates. A pre-fetched cache of the driver-TF
PWMs used by the tool ships in `webapp/backend/jaspar_cache/`, so the deployed tool needs no
JASPAR access at runtime. `webapp/backend/motifs.py` re-fetches any missing PWM from the JASPAR API.

## CRISPR screens (ScreenAudit)

Live from the BioGRID ORCS REST API (`orcsws.thebiogrid.org`), needs a free ORCS access key.
`screenaudit/run_screenaudit.py` computes the cross-screen hit-call discordance; the committed
`screenaudit/screenaudit_result.json` is the result over four cell lines.
