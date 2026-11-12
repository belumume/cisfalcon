"""Generate webdemo/parity_reference.json: what the Python gate says, for the browser to match.

The browser build runs float16 weights, so `webdemo/parity.test.mjs` has to compare its answers
against something authoritative. This script is that something: it runs the real Python gate
(`verifier.gate_report`, `verifier._rule_verdict`) and the real motif scan over a fixed design
set and writes the result.

The set is chosen to cover the cases where a port goes wrong rather than the cases where it
looks fine: the two committed heroes, the mixed measured batch, a homopolymer and a tandem
repeat (the complexity floor), a sequence with Ns (the all-zero encoding column), one longer
than the 500 bp input window (truncation), one under the input length (left padding), and six
random sequences spread across the target cells (the activity floor and the off-target list).

    python tools/build_parity_reference.py

Needs TensorFlow and the three activity models (python fetch_models.py), so it is a developer
step, not part of the reviewer path. Re-run it only when the gate itself changes, and commit
the result: the point of the file is that it is the frozen expectation.
"""

from __future__ import annotations

import json
import pathlib
import random
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "webdemo" / "parity_reference.json"
SEED = 7


def main() -> int:
    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(ROOT / "webapp" / "backend"))
    import gate
    import motifs
    import verifier

    data = ROOT / "data" / "gosai_designed"
    hero = json.loads((data / "hero.json").read_text())
    brain = json.loads((data / "brain_hero.json").read_text())
    batch = json.loads((data / "batch_example.json").read_text())

    cases = [("hero", hero["sequence"], "HepG2"), ("brain", brain["sequence"], "SKNSH")]
    cases += [(f"batch{i}", d["seq"], "HepG2") for i, d in enumerate(batch)]
    cases += [
        ("polyA", "A" * 200, "K562"),
        ("acgt", "ACGT" * 50, "K562"),
        ("withN", "ACGTN" * 40, "MCF7"),
        ("long", (hero["sequence"] * 3)[:900], "K562"),
        ("short", hero["sequence"][:60], "GM12878"),
    ]
    rng = random.Random(SEED)
    for i in range(6):
        n = rng.choice([120, 200, 350, 500])
        seq = "".join(rng.choice("ACGT") for _ in range(n))
        cases.append((f"rand{i}", seq, gate.TARGET_CELLS[i]))

    calib = verifier.Calibration()
    out = []
    for name, seq, cell in cases:
        report = verifier.gate_report(seq, cell, calib)
        out.append(
            {
                "name": name,
                "sequence": seq,
                "target_cell": cell,
                "report": report,
                "rule_verdict": verifier._rule_verdict(report),
                "motifs": motifs.scan_sequence(
                    seq, cell, report["predicted_most_active_cell"]
                ),
            }
        )
    OUT.write_text(json.dumps(out))
    print(f"wrote {len(out)} reference designs to {OUT.relative_to(ROOT)}")

    # the same isotonic calibration the page interpolates, exported as its fitted knots
    iso = ROOT / "webdemo" / "data" / "calibration_iso.json"
    if calib.iso is not None:
        iso.write_text(
            json.dumps(
                {
                    "x": [float(v) for v in calib.iso.f_.x],
                    "y": [float(v) for v in calib.iso.f_.y],
                    "base": calib.base,
                }
            )
        )
        print(f"wrote {iso.relative_to(ROOT)} ({len(calib.iso.f_.x)} knots)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
