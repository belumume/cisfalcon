"""Local verification of the low-activity caveat before deploy.
random -> should be low_activity; demo hero -> must NOT be (protects the demo);
demo batch -> hero triage flow must stay clean."""

import os, sys, json, random

os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "3")
os.environ.setdefault("CUDA_VISIBLE_DEVICES", "-1")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import verifier
import gate

random.seed(7)
rnd = "".join(random.choice("ACGT") for _ in range(200))

hero = json.load(open("data/gosai_designed/hero.json"))
hero_seq, hero_target = hero["sequence"], hero.get("target_cell", "HepG2")
batch = json.load(open("data/gosai_designed/batch_example.json"))
batch_seqs = [d["seq"] for d in batch]


def check(name, seq, target):
    rep = verifier.gate_report(seq, target)
    rv = verifier._rule_verdict(rep)
    print(
        f"{name:24s} target={target:6s} peak={rep['peak_activity']:6.2f} "
        f"low_activity={str(rep['low_activity']):5s} verdict={rv['verdict']:10s}"
    )
    print(f"   rec: {rv['recommendation']}")


print("=== single-sequence checks ===")
check("RANDOM (paste-garbage)", rnd, "K562")
check("DEMO HERO", hero_seq, hero_target)

print("\n=== demo batch (hero triage flow must stay clean) ===")
verds = gate.verdict(batch_seqs, "HepG2")
n_low = sum(1 for v in verds if v["low_activity"])
peaks = sorted(v["peak_activity"] for v in verds)
print(
    f"batch n={len(verds)}  low_activity_count={n_low}  "
    f"peak min/med/max = {peaks[0]:.2f}/{peaks[len(peaks) // 2]:.2f}/{peaks[-1]:.2f}"
)
