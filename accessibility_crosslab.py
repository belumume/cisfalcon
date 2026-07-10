import os, glob, shutil, sys, pathlib, csv, gc
import numpy as np, tensorflow as tf

for g in tf.config.list_physical_devices("GPU"):
    try:
        tf.config.experimental.set_memory_growth(g, True)
    except Exception:
        pass
gate_py = next(iter(glob.glob("/kaggle/input/**/gate.py", recursive=True)), None)
sys.path.insert(0, os.path.dirname(gate_py))
import gate

os.makedirs("/tmp/models", exist_ok=True)
for f in glob.glob("/kaggle/input/**/dhs64*split*.h5", recursive=True):
    shutil.copy(f, "/tmp/models/")
print("models:", sorted(os.listdir("/tmp/models")))
gate._MODELS_DIR = pathlib.Path("/tmp/models")
bench = next(iter(glob.glob("/kaggle/input/**/designed_benchmark.csv", recursive=True)))

SHARED = ["K562", "HepG2", "SKNSH"]
# activity head = 12 MPRA cells; accessibility head = 64 DHS biosamples (different order),
# and the accessibility model is MULTI-HEAD: score_sequences returns (2, N, 64) = [logsignal, binary].
MPRA_IDX = {"K562": 7, "HepG2": 6, "SKNSH": 3}
DHS64_IDX = {"K562": 57, "HepG2": 49, "SKNSH": 30}

targets, seqs, meas = [], [], []
with open(bench) as fh:
    for r in csv.DictReader(fh):
        targets.append(r["target_cell"])
        seqs.append(r["sequence"])
        meas.append({c: float(r[c]) for c in SHARED})
n = len(seqs)
print("n =", n)
labels = np.array([0 if max(m, key=m.get) == t else 1 for t, m in zip(targets, meas)])
print("fail rate:", round(float(labels.mean()), 4))


def gap_of(pred2d, idxmap):
    out = np.empty(len(pred2d))
    for i, t in enumerate(targets):
        sub = {c: float(pred2d[i, idxmap[c]]) for c in SHARED}
        out[i] = sub[t] - max(v for c, v in sub.items() if c != t)
    return out


def auroc(lab, scores):
    order = np.argsort(scores, kind="mergesort")
    s = np.asarray(scores)[order]
    rr = np.empty(len(s))
    i = 0
    while i < len(s):
        j = i
        while j < len(s) and s[j] == s[i]:
            j += 1
        rr[i:j] = (i + 1 + j) / 2.0
        i = j
    rank = np.empty(len(s))
    rank[order] = rr
    npos = lab.sum()
    nneg = len(lab) - npos
    return (rank[lab == 1].sum() - npos * (npos + 1) / 2) / (npos * nneg)


p_act = np.asarray(gate.score_sequences(seqs, kind="mpra", batch_size=512))
print("[mpra] shape", p_act.shape)
assert p_act.ndim == 2 and p_act.shape[1] == 12
act = gap_of(p_act, MPRA_IDX)
a_act = auroc(labels, -act)
gate._load_models.cache_clear()
gc.collect()

p_acc = np.asarray(gate.score_sequences(seqs, kind="acc", batch_size=512))
print("[acc] shape", p_acc.shape)
print("\n=== CROSS-LAB accessibility-vs-activity, n=%d ===" % n)
print("ACTIVITY gate AUROC:            %.4f" % a_act)
if (
    p_acc.ndim == 3
):  # (n_heads, N, 64): head 0 = logsignal (continuous), head 1 = binary
    names = {0: "logsignal", 1: "binary"}
    for h in range(p_acc.shape[0]):
        assert p_acc[h].shape[1] > max(DHS64_IDX.values())
        acc_h = gap_of(p_acc[h], DHS64_IDX)
        a_h = auroc(labels, -acc_h)
        print(
            "ACCESSIBILITY head %d (%s) AUROC: %.4f   activity adds %+.4f"
            % (h, names.get(h, "?"), a_h, a_act - a_h)
        )
else:
    assert p_acc.shape[1] > max(DHS64_IDX.values())
    acc = gap_of(p_acc, DHS64_IDX)
    a_acc = auroc(labels, -acc)
    print(
        "ACCESSIBILITY-only AUROC:       %.4f   activity adds %+.4f"
        % (a_acc, a_act - a_acc)
    )
