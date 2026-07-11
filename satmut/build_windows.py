"""Reproducibly build ref/alt 500bp variant windows for the CisFalcon satMut test.
Inputs : Kircher 2019 satMut effect table (elements.tsv.gz), UCSC hg38 sequence API.
Output : variant_windows.csv.gz  (element, cell, chrom, pos, ref, alt, measured_effect,
         pvalue, ref_seq, alt_seq)
"""
import urllib.request, json, time
import pandas as pd, numpy as np

# element -> cell line, from Kircher 2019 (github.com/kircherlab/MPRA_SaturationMutagenesis about.md)
TARGETS = {"F9":"HepG2","LDLR":"HepG2","LDLR.2":"HepG2","SORT1":"HepG2","SORT1.2":"HepG2",
           "SORT1-flip":"HepG2","PKLR-24h":"K562","PKLR-48h":"K562"}
W, HALF, FLANK = 500, 250, 300

el = pd.read_csv("MPRA_SaturationMutagenesis/data/elements.tsv.gz", sep="\t", low_memory=False)
g38 = el[(el.Release == "GRCh38") & (el.Element.isin(TARGETS))].dropna(subset=["Pos"]).copy()
g38["Pos"] = g38["Pos"].astype(int)

def ucsc(chrom, start0, end):
    url = f"https://api.genome.ucsc.edu/getData/sequence?genome=hg38;chrom=chr{chrom};start={start0};end={end}"
    with urllib.request.urlopen(url, timeout=60) as r:
        return json.load(r)["dna"].upper()

rec = []
for e, cell in TARGETS.items():
    sub = g38[g38.Element == e]
    ch, lo, hi = str(sub.Chrom.iloc[0]), int(sub.Pos.min()), int(sub.Pos.max())
    ws, we = lo - FLANK, hi + FLANK
    seq = ucsc(ch, ws - 1, we)            # UCSC 0-based; Pos is 1-based
    snv = sub[sub.Alt.isin(list("ACGT")) & sub.Ref.isin(list("ACGT"))]
    for _, r in snv.iterrows():
        gi = int(r.Pos) - ws
        if seq[gi] != r.Ref:              # skip rare genome/ref mismatch
            continue
        s0 = gi - HALF
        if s0 < 0 or gi + HALF > len(seq):
            continue
        refw = seq[s0:gi + HALF]; vi = gi - s0
        altw = refw[:vi] + r.Alt + refw[vi + 1:]
        rec.append(dict(element=e, cell=cell, chrom=ch, pos=int(r.Pos), ref=r.Ref, alt=r.Alt,
                        measured_effect=float(r.Coefficient), pvalue=float(r.pValue),
                        ref_seq=refw, alt_seq=altw))
    time.sleep(0.3)
pd.DataFrame(rec).to_csv("variant_windows.csv.gz", index=False, compression="gzip")
print("built", len(rec), "windows")
