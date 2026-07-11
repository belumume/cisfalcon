"""GPU variant scoring: ensemble mean of 3 frozen MPRA fold models.
Reads variant_windows.csv.gz (staged flat), writes out/variant_scored.csv.gz.
Self-contained — reimplements gate.one_hot_encode / score_sequences (verified identical).
"""
import time, os
os.environ["TF_XLA_FLAGS"] = "--tf_xla_auto_jit=0"
os.environ["TF_DISABLE_MLIR_BRIDGE"] = "1"
import numpy as np, pandas as pd
import tensorflow as tf
tf.config.optimizer.set_jit(False)

INPUT_LEN = 500
MPRA_CELL_LINES = ["NT2_D1","GM12878","786_O","SKNSH","WERI_Rb1","SJCRH30",
                   "HepG2","K562","MCF7","HeLaS3","HEK293","HMC3"]
CELL_IDX = {c: i for i, c in enumerate(MPRA_CELL_LINES)}
FOLDS = [0, 1, 3]
NUC = {"a":[1,0,0,0],"c":[0,1,0,0],"g":[0,0,1,0],"t":[0,0,0,1],"n":[0,0,0,0]}

def one_hot_encode(seqs, max_len=INPUT_LEN):
    out = np.zeros([len(seqs), max_len, 4], dtype=np.float32)
    for i, s in enumerate(seqs):
        s = str(s)[:max_len]
        oh = np.array([NUC.get(x,[0,0,0,0]) for x in s.lower()], dtype=np.float32)
        if len(oh): out[i, :len(s), :] = oh
    return out

print("GPUs:", tf.config.list_physical_devices("GPU"), flush=True)
models = [tf.keras.models.load_model(f"dhs64_mpra_split{k}.h5", compile=False) for k in FOLDS]
print("loaded", len(models), "models", flush=True)

df = pd.read_csv("variant_windows.csv.gz")
print("variants:", len(df), flush=True)

def ensemble(seqs, bs=1024):
    X = one_hot_encode(seqs)
    preds = [m.predict(X, batch_size=bs, verbose=0) for m in models]
    return np.mean(preds, axis=0)

t = time.time(); ref = ensemble(df.ref_seq.tolist()); print(f"ref {time.time()-t:.0f}s", flush=True)
t = time.time(); alt = ensemble(df.alt_seq.tolist()); print(f"alt {time.time()-t:.0f}s", flush=True)

HEP, K = CELL_IDX["HepG2"], CELL_IDX["K562"]
ci = df.cell.map({"HepG2":HEP,"K562":K}).values
r = np.arange(len(df))
df["pred_ref_activity"] = ref[r, ci]
df["pred_alt_activity"] = alt[r, ci]
df["pred_effect"] = df.pred_alt_activity - df.pred_ref_activity
df["pred_effect_HepG2"] = alt[:,HEP] - ref[:,HEP]
df["pred_effect_K562"]  = alt[:,K]   - ref[:,K]
os.makedirs("out", exist_ok=True)
df.drop(columns=["ref_seq","alt_seq"]).to_csv("out/variant_scored.csv.gz", index=False, compression="gzip")
print("saved out/variant_scored.csv.gz rows=%d" % len(df), flush=True)
