"""Fetch the six frozen fold models from Zenodo and verify them by hash.

WHY THIS EXISTS
---------------
`Dockerfile` does `COPY models/ ./models/`, and `models/` is not in git (the weights are 503MB
of third-party artifacts). So `docker build` succeeded only for someone who already had them
and failed at that line for everyone else, with no committed step that would produce them.

The weights are NOT ours and were never unpublished: they are Castillo-Hair et al. 2025
(bioRxiv 2025.09.30.679565), Zenodo record 17410822, CC-BY 4.0. What was missing was a
committed, runnable fetch step.

THE RENAME IS THE TRAP. Zenodo ships the activity head as `dhs64_mpra_data_split_{0,1,3}.h5`
and `gate.py` hard-requires `dhs64_mpra_split{0,1,3}.h5`. DATA.md gave the post-rename names as
if they were the Zenodo names, so a reader following the download instruction got a load failure
with no hint a rename was needed. This script encodes the mapping so nobody has to notice it.

Hashes are pinned from the local copies that produced every published number, so a corrupted or
substituted download fails loudly rather than silently changing results. The three activity-head
hashes match satmut/PROVENANCE.md independently.
"""

from __future__ import annotations

import hashlib
import sys
import urllib.request
from pathlib import Path

RECORD = "17410822"
BASE = f"https://zenodo.org/records/{RECORD}/files"
DEST = Path(__file__).resolve().parent / "models"

# (zenodo filename, local filename gate.py expects, sha256)
MODELS = [
    (
        "dhs64_mpra_data_split_0.h5",
        "dhs64_mpra_split0.h5",
        "09d85a34aa4fbfdd3e7f4d7e55cbe5938c4bad85a193203e73717fc4b800582a",
    ),
    (
        "dhs64_mpra_data_split_1.h5",
        "dhs64_mpra_split1.h5",
        "8c4649bb87b42c5f144bbea9784af98812aac10b8f70e1d3794b07dfb68c6fb4",
    ),
    (
        "dhs64_mpra_data_split_3.h5",
        "dhs64_mpra_split3.h5",
        "b31eed0df85495a5f1e4136e40af0c32ccaeed4563666f52aa07d9c2e9797f5e",
    ),
    (
        "dhs64_data_split_0.h5",
        "dhs64_split0.h5",
        "5116558c6afe878e89503b1ef5093db7123386d308ef7a414aa1ce1cd6c407cf",
    ),
    (
        "dhs64_data_split_1.h5",
        "dhs64_split1.h5",
        "e67603c583dc08d0606ae7a38df3c5d876b2899c9b69084df62786557896ccbe",
    ),
    (
        "dhs64_data_split_3.h5",
        "dhs64_split3.h5",
        "ea3ebbe6676a5c97c7e63a5f73ba032a32c58f1aacd1a25b3c5bf91492ccefe4",
    ),
]


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    DEST.mkdir(parents=True, exist_ok=True)
    failures = []
    for remote, local, want in MODELS:
        out = DEST / local
        if out.exists():
            got = sha256(out)
            if got == want:
                print(f"[ok]   {local} already present and verified")
                continue
            print(f"[warn] {local} present but hash differs; re-downloading")
        url = f"{BASE}/{remote}?download=1"
        print(f"[get]  {remote} -> {local}")
        try:
            urllib.request.urlretrieve(url, out)
        except Exception as e:
            print(f"[FAIL] {remote}: {e}", file=sys.stderr)
            failures.append(local)
            continue
        got = sha256(out)
        if got != want:
            print(
                f"[FAIL] {local} hash mismatch\n  want {want}\n  got  {got}",
                file=sys.stderr,
            )
            failures.append(local)
        else:
            print(f"[ok]   {local} verified")

    if failures:
        print(
            f"\n{len(failures)} of {len(MODELS)} model(s) failed: {failures}\n"
            f"If a filename 404s, the Zenodo record may have been revised. Open "
            f"https://zenodo.org/records/{RECORD} and check the current names against the "
            f"first column of MODELS in this file, then update it.",
            file=sys.stderr,
        )
        return 1
    print(f"\nall {len(MODELS)} models present and hash-verified in {DEST}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
