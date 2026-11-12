/* CisFalcon in-browser engine.
 *
 * Runs the same deterministic gate the server ran, in the visitor's own tab: the three
 * frozen fold models (converted to TensorFlow.js, float16 weights), the identical input
 * encoding, the identical specificity-gap arithmetic, and the identical isotonic failure
 * calibration exported from data/calibration.csv as its own interpolation knots.
 *
 * It exposes window.CF.api(path, body), which answers the same paths the FastAPI backend
 * answered, so the frontend is unchanged apart from pointing api() here. Nothing leaves
 * the browser: no server, no API key, no cost.
 *
 * THE PAID LAYER. /diagnose and /rescue called the paid Anthropic API from the server. A static
 * page has no server and no key, so they run on the visitor's own key through agents.js, and
 * fall back to the deterministic verdict when no key is given. Every published number in the
 * repository comes from the gate, which needs no key and runs here in full.
 */
(function () {
  "use strict";

  const MPRA_CELL_LINES = ["NT2_D1", "GM12878", "786_O", "SKNSH", "WERI_Rb1", "SJCRH30",
    "HepG2", "K562", "MCF7", "HeLaS3", "HEK293", "HMC3"];
  const TARGET_CELLS = MPRA_CELL_LINES.slice(0, 10);
  const CELL_IDX = {}; MPRA_CELL_LINES.forEach((c, i) => (CELL_IDX[c] = i));
  const INPUT_LEN = 500, ACTIVITY_FLOOR = 0.5, COMPLEXITY_FLOOR = 0.35;
  const FOLDS = [0, 1, 3];
  // Fold models are ensembled 64 sequences at a time by the frontend; the gate runs them in
  // smaller slices so a laptop GPU holds the activations of a 500x256 residual stack.
  const PREDICT_SLICE = 8;

  const HEADLINE = {
    crosslab_auroc: 0.8013,
    crosslab_n: 93435,
    base_fail_rate: 0.0629,
    safest_half_fail_rate: 0.0191,
    failure_reduction_pct: 70,
    failure_reduction_pct_basis: "pooled across cells and generators",
    failure_reduction_pct_conditioned: 41,
    failure_reduction_pct_conditioned_basis: "macro-average within (cell x generator), 14 strata",
    sequence_free_stratum_prior_null_pct: 90.5,
    sequence_free_stratum_prior_null_range_pct: [90.3, 90.7],
    sequence_free_stratum_prior_null_basis:
      "pooled; tie-break dependent, range over 12 seeds (triage_conditioning_check.py)",
    null_note:
      "A rule using the stratum prior and NO sequence scores about 90% pooled, which beats the " +
      "pooled 70%. The pooled figure therefore is not evidence of per-sequence skill; the " +
      "41% conditioned figure is. See triage_conditioning_check.py and PREREG-ERRATA.md.",
    riskiest10_ppv: 0.27,
    source: "93,435 independent designs (Gosai/Tewhey 2024; BODA/Malinois; zero sequence overlap)",
  };

  // lineage-driver TFs per cell line, and the clinical grounding, as the server had them
  const DRIVERS = {
    K562: ["GATA1", "TAL1", "KLF1", "GATA2", "NFE2"],
    HepG2: ["HNF4A", "CEBPA", "HNF1A", "FOXA2", "FOXA1"],
    SKNSH: ["GATA3", "PHOX2B", "HAND2", "ISL1", "TFAP2A"],
    SJCRH30: ["MYOD1", "MYOG", "PAX3", "MYF5"],
    MCF7: ["ESR1", "GATA3", "FOXA1", "SPDEF"],
    GM12878: ["SPI1", "EBF1", "PAX5", "IRF4"],
    NT2_D1: ["POU5F1", "SOX2", "NANOG"],
    WERI_Rb1: ["CRX", "OTX2", "NRL"],
    HEK293: ["SP1", "YY1"],
    HeLaS3: ["SP1", "AP1", "NFYA"],
    "786_O": ["HIF1A", "EPAS1", "SP1"],
    HMC3: ["SPI1", "IRF8", "CEBPB"],
  };
  const TF_DISEASE = {
    GATA1: { disease: "X-linked dyserythropoietic anemia / thrombocytopenia", omim: "300367" },
    TAL1: { disease: "T-cell acute lymphoblastic leukemia", omim: null },
    KLF1: { disease: "congenital dyserythropoietic anemia", omim: null },
    GATA2: { disease: "GATA2 deficiency (MonoMAC / Emberger syndrome)", omim: null },
    HNF4A: { disease: "MODY1 (maturity-onset diabetes of the young)", omim: "125850" },
    HNF1A: { disease: "MODY3 diabetes", omim: null },
    CEBPA: { disease: "familial acute myeloid leukemia", omim: null },
    FOXA2: { disease: "congenital hyperinsulinism / hypopituitarism", omim: null },
    GATA3: { disease: "HDR syndrome (hypoparathyroidism, deafness, renal dysplasia)", omim: null },
    PHOX2B: { disease: "congenital central hypoventilation; neuroblastoma predisposition", omim: null },
  };

  // Python's round() breaks a tie to the even digit; JavaScript's Math.round breaks it upward.
  // That is a one-in-a-thousand difference in a displayed number, and it showed up immediately:
  // an ACGT tandem repeat has complexity exactly 0.0625, which Python prints as 0.062 and a naive
  // port printed as 0.063. Round the way the server rounded.
  function roundTo(v, nd) {
    const f = Math.pow(10, nd);
    const x = v * f;
    if (Math.abs(x - Math.trunc(x)) === 0.5) return (2 * Math.round(x / 2)) / f;
    return Math.round(x) / f;
  }
  const r3 = (v) => roundTo(v, 3);
  const err = (status, detail) => { const e = new Error(detail); e.status = status; return e; };

  /* ------------------------------------------------------------------ input encoding */
  const NUC = { a: 0, c: 1, g: 2, t: 3 };

  function encodeInto(buf, offset, seq) {
    // atlas convention: channels A,C,G,T; padding='left' (sequence at index 0, zeros after);
    // anything that is not ACGT (N included) stays an all-zero column and carries no signal.
    const s = seq.length > INPUT_LEN ? seq.slice(0, INPUT_LEN) : seq;
    for (let i = 0; i < s.length; i++) {
      const j = NUC[s[i].toLowerCase()];
      if (j !== undefined) buf[offset + i * 4 + j] = 1;
    }
  }

  function sequenceComplexity(seq) {
    const s = String(seq).toUpperCase().replace(/[^ACGT]/g, "");
    const L = s.length;
    if (L < 6) return 0.0;
    let out = Infinity;
    for (const k of [2, 3]) {
      const set = new Set();
      for (let i = 0; i + k <= L; i++) set.add(s.slice(i, i + k));
      const maxk = Math.min(Math.pow(4, k), L - k + 1);
      out = Math.min(out, set.size / maxk);
    }
    return out;
  }

  /* -------------------------------------------------------------------- calibration */
  // Isotonic regression fit on held-out (predicted_gap, measured_fail) pairs, exported as the
  // fitted interpolation knots; linear interpolation between them with out-of-range clipping
  // reproduces scikit-learn's predict() exactly.
  let CALIB = null;
  function pFail(gap) {
    if (!CALIB) return 1.0 / (1.0 + Math.exp(3.0 * gap)); // documented fallback
    const { x, y } = CALIB;
    if (gap <= x[0]) return y[0];
    if (gap >= x[x.length - 1]) return y[y.length - 1];
    let lo = 0, hi = x.length - 1;
    while (hi - lo > 1) { const mid = (lo + hi) >> 1; if (x[mid] <= gap) lo = mid; else hi = mid; }
    const t = (gap - x[lo]) / (x[hi] - x[lo]);
    return y[lo] + t * (y[hi] - y[lo]);
  }

  /* -------------------------------------------------------------------- fold models */
  let models = null, loading = null;
  const progress = { done: 0, total: FOLDS.length, frac: 0 };
  const listeners = new Set();
  function emit() { listeners.forEach((f) => { try { f(progress); } catch (e) { /* listener's problem */ } }); }

  async function loadModels() {
    if (models) return models;
    if (loading) return loading;
    loading = (async () => {
      const per = new Array(FOLDS.length).fill(0);
      const loaded = [];
      for (let i = 0; i < FOLDS.length; i++) {
        loaded.push(await tf.loadLayersModel(`models/split${FOLDS[i]}/model.json`, {
          onProgress: (f) => {
            per[i] = f;
            progress.frac = per.reduce((a, b) => a + b, 0) / FOLDS.length;
            progress.done = i;
            emit();
          },
        }));
      }
      progress.done = FOLDS.length; progress.frac = 1; emit();
      models = loaded;
      return models;
    })();
    return loading;
  }

  // Ensemble = mean over the independent fold models, which is the correct deployment mode for a
  // sequence none of them trained on (gate.py: score_sequences).
  async function scoreSequences(seqs) {
    const ms = await loadModels();
    const out = [];
    for (let start = 0; start < seqs.length; start += PREDICT_SLICE) {
      const slice = seqs.slice(start, start + PREDICT_SLICE);
      const buf = new Float32Array(slice.length * INPUT_LEN * 4);
      slice.forEach((s, i) => encodeInto(buf, i * INPUT_LEN * 4, s));
      const x = tf.tensor3d(buf, [slice.length, INPUT_LEN, 4]);
      const acc = tf.tidy(() => {
        let sum = null;
        for (const m of ms) {
          const p = m.predict(x, { batchSize: slice.length });
          sum = sum === null ? p : tf.add(sum, p);
        }
        return tf.div(sum, ms.length);
      });
      const flat = await acc.data();
      acc.dispose(); x.dispose();
      for (let i = 0; i < slice.length; i++) out.push(Array.from(flat.slice(i * 12, i * 12 + 12)));
    }
    return out;
  }

  function specificityGap(pred, targetCell) {
    const sub = TARGET_CELLS.map((c) => pred[CELL_IDX[c]]);
    const ti = TARGET_CELLS.indexOf(targetCell);
    let off = -Infinity;
    sub.forEach((v, i) => { if (i !== ti && v > off) off = v; });
    return sub[ti] - off;
  }

  function gateReport(sequence, targetCell, pred) {
    const gap = specificityGap(pred, targetCell);
    const sub = TARGET_CELLS.map((c) => pred[CELL_IDX[c]]);
    const profile = {};
    MPRA_CELL_LINES.forEach((c) => (profile[c] = r3(pred[CELL_IDX[c]])));
    const mostActive = TARGET_CELLS[sub.indexOf(Math.max.apply(null, sub))];
    const peak = Math.max.apply(null, sub);
    const complexity = sequenceComplexity(sequence);
    const tv = pred[CELL_IDX[targetCell]];
    return {
      target_cell: targetCell,
      predicted_specificity_gap: r3(gap),
      predicted_most_active_cell: mostActive,
      predicted_fail: gap <= 0,
      calibrated_fail_probability: r3(pFail(gap)),
      peak_activity: r3(peak),
      low_activity: peak < ACTIVITY_FLOOR,
      activity_floor: ACTIVITY_FLOOR,
      complexity: r3(complexity),
      low_complexity: complexity < COMPLEXITY_FLOOR,
      complexity_floor: COMPLEXITY_FLOOR,
      predicted_profile_log2fc: profile,
      off_target_risk_cells: TARGET_CELLS
        .filter((c) => c !== targetCell && pred[CELL_IDX[c]] >= tv)
        .sort((a, b) => pred[CELL_IDX[b]] - pred[CELL_IDX[a]]),
    };
  }

  function ruleVerdict(report) {
    const p = report.calibrated_fail_probability;
    const v = report.predicted_fail ? "FAIL" : (p > 0.4 ? "BORDERLINE" : "PASS");
    const low = !!report.low_activity, lowc = !!report.low_complexity;
    let rec;
    if (lowc) {
      rec = `degenerate/repetitive sequence (complexity ${report.complexity}, a homopolymer or ` +
        "tandem repeat, not a diverse enhancer-like sequence); not a credible enhancer design, " +
        "so the specificity call is not meaningful";
    } else if (low) {
      rec = `predicted weakly active in every cell (peak ${report.peak_activity} log2FC, within ` +
        "the range of random sequences); may not be a functional enhancer, so treat the " +
        "specificity call as low-confidence";
    } else if (v === "FAIL") {
      rec = "do not synthesize; predicted to miss target cell";
    } else if (v === "PASS") {
      rec = "predicted specific; reasonable to synthesize";
    } else {
      rec = "borderline; consider redesign or add controls";
    }
    return {
      verdict: v,
      low_activity: low,
      low_complexity: lowc,
      confidence: roundTo(Math.abs(p - 0.5) * 2, 2),
      recommendation: rec,
      grounded_in: "gate calibration only (agents disabled)",
    };
  }

  /* ------------------------------------------------------------------- motif scanning */
  const pwmCache = new Map();
  async function resolvePwm(tf_) {
    if (pwmCache.has(tf_)) return pwmCache.get(tf_);
    const p = fetch(`jaspar/${tf_}.json`)
      .then((r) => (r.ok ? r.json() : null))
      .catch(() => null);
    pwmCache.set(tf_, p);
    return p;
  }

  const COMP = { A: "T", C: "G", G: "C", T: "A", N: "N" };
  const revcomp = (s) => s.split("").reverse().map((b) => COMP[b] || "N").join("");
  const BIDX = { A: 0, C: 1, G: 2, T: 3 };

  function scanOne(seq, pwm, relThresh) {
    relThresh = relThresh === undefined ? 0.85 : relThresh;
    const lo = pwm.logodds, L = pwm.length;
    const thr = pwm.minscore + relThresh * (pwm.maxscore - pwm.minscore);
    const hits = [];
    for (const [strand, s] of [["+", seq], ["-", revcomp(seq)]]) {
      const idx = new Array(s.length);
      for (let i = 0; i < s.length; i++) { const b = BIDX[s[i]]; idx[i] = b === undefined ? -1 : b; }
      for (let i = 0; i + L <= s.length; i++) {
        let score = 0, bad = false;
        for (let j = 0; j < L; j++) { const b = idx[i + j]; if (b < 0) { bad = true; break; } score += lo[b][j]; }
        if (bad || score < thr) continue;
        hits.push({
          pos: strand === "+" ? i : s.length - i - L,
          strand,
          score: roundTo(score, 2),
          rel: roundTo((score - pwm.minscore) / (pwm.maxscore - pwm.minscore), 3),
        });
      }
    }
    hits.sort((a, b) => b.score - a.score);
    return hits.slice(0, 8);
  }

  // The erythroid pentameric complex binds one bipartite element: an E-box (CANNTG) 6-12 bp
  // upstream of a WGATAR GATA site (Wadman 1997, EMBO J). The assembled composite is stronger
  // evidence of blood-cell grammar than two independent hits.
  function erythroidComposites(seq) {
    const s = seq.toUpperCase().replace(/U/g, "T");
    const out = [];
    for (const [strand, t] of [["+", s], ["-", revcomp(s)]]) {
      const eb = [], ga = [];
      for (const m of t.matchAll(/CA[ACGT][ACGT]TG/g)) eb.push([m.index, m.index + 6, m[0]]);
      for (const m of t.matchAll(/[AT]GATA[AG]/g)) ga.push([m.index, m.index + 6, m[0]]);
      for (const [es, ee, eg] of eb) {
        for (const [gs, ge, gg] of ga) {
          const gapN = gs - ee;
          if (gapN >= 6 && gapN <= 12) {
            out.push({ pos: strand === "+" ? es : t.length - ge, strand, ebox: eg, gata: gg, spacer: gapN });
          }
        }
      }
    }
    const seen = new Set(), uniq = [];
    out.sort((a, b) => a.pos - b.pos).forEach((h) => {
      const k = h.pos + h.strand;
      if (!seen.has(k)) { seen.add(k); uniq.push(h); }
    });
    return uniq.slice(0, 8);
  }

  async function scanSequence(seq, targetCell, offTargetCell) {
    seq = seq.toUpperCase().replace(/U/g, "T");
    let cells = [offTargetCell, targetCell].filter((c) => c && DRIVERS[c]);
    if (!cells.length) cells = DRIVERS[targetCell] ? [targetCell] : [];
    const result = {};
    for (const cell of [...new Set(cells)]) {
      const tfs = {};
      for (const name of DRIVERS[cell] || []) {
        const pwm = await resolvePwm(name);
        if (!pwm) continue;
        const hits = scanOne(seq, pwm);
        if (hits.length) {
          tfs[name] = {
            matrix_id: pwm.matrix_id,
            n_sites: hits.length,
            top: hits.slice(0, 3),
            disease: TF_DISEASE[name] || null,
          };
        }
      }
      result[cell] = {
        n_driver_tfs_present: Object.keys(tfs).length,
        total_sites: Object.values(tfs).reduce((a, v) => a + v.n_sites, 0),
        tfs,
      };
    }
    return {
      target_cell: targetCell,
      off_target_cell: offTargetCell || null,
      by_cell: result,
      erythroid_composite: erythroidComposites(seq),
      source: "JASPAR CORE vertebrates (log-odds PWM scan, both strands, rel>=0.85)",
    };
  }

  async function driverSites(seq, cell, top) {
    top = top || 3;
    seq = seq.toUpperCase().replace(/U/g, "T");
    const sites = [];
    for (const name of DRIVERS[cell] || []) {
      const pwm = await resolvePwm(name);
      if (!pwm) continue;
      for (const h of scanOne(seq, pwm)) {
        sites.push({ tf: name, matrix_id: pwm.matrix_id, pos: h.pos, strand: h.strand, length: pwm.length, score: h.score });
      }
    }
    sites.sort((a, b) => b.score - a.score);
    return sites.slice(0, top);
  }

  async function consensusSeq(name) {
    const pwm = await resolvePwm(name);
    if (!pwm) return null;
    const bases = "ACGT";
    let out = "";
    for (let j = 0; j < pwm.length; j++) {
      let best = 0;
      for (let b = 1; b < 4; b++) if (pwm.logodds[b][j] > pwm.logodds[best][j]) best = b;
      out += bases[best];
    }
    return out;
  }

  /* ------------------------------------------------------------------ input validation */
  const DNA = /^[ACGTUNacgtun]+$/;
  function stripFasta(seq) {
    return String(seq || "").split(/\r?\n/).filter((l) => !l.trimStart().startsWith(">")).join("\n").replace(/\s+/g, "");
  }
  function cleanSeq(seq) {
    const s = stripFasta(seq);
    if (!s) throw err(400, "empty sequence");
    if (s.length < 50) throw err(400, "sequence too short (need >= 50 bp)");
    if (s.length > 5000) throw err(400, "sequence too long (max 5000 bp)");
    if (!DNA.test(s)) throw err(400, "sequence must be DNA (A/C/G/T/N)");
    return s.toUpperCase().replace(/U/g, "T");
  }
  function checkTarget(cell) {
    if (!TARGET_CELLS.includes(cell)) throw err(400, `target_cell must be one of ${TARGET_CELLS}`);
    return cell;
  }

  const getJson = (p) => fetch(p).then((r) => (r.ok ? r.json() : null)).catch(() => null);

  /* ----------------------------------------------------------------------- endpoints */
  async function predict(body) {
    const seq = cleanSeq(body.sequence), cell = checkTarget(body.target_cell);
    const t0 = performance.now();
    const pred = (await scoreSequences([seq]))[0];
    const report = gateReport(seq, cell, pred);
    report.rule_verdict = ruleVerdict(report);
    report.ms = Math.round(performance.now() - t0);
    report.seq_len = seq.length;
    return report;
  }

  async function motifScan(body) {
    const seq = cleanSeq(body.sequence), cell = checkTarget(body.target_cell);
    const pred = (await scoreSequences([seq]))[0];
    const report = gateReport(seq, cell, pred);
    const scan = await scanSequence(seq, cell, report.predicted_most_active_cell);
    scan.predicted_most_active_cell = report.predicted_most_active_cell;
    scan.predicted_specificity_gap = report.predicted_specificity_gap;
    return scan;
  }

  const MAX_BATCH = 64;
  async function batch(body) {
    const cell = checkTarget(body.target_cell);
    if (body.sequences.length > MAX_BATCH) {
      throw err(400, `batch too large (${body.sequences.length} designs); max ${MAX_BATCH} per ` +
        "request so each check stays fast. Split into smaller batches.");
    }
    const seqs = [];
    for (const s of body.sequences) {
      const s2 = stripFasta(s);
      if (s2 && DNA.test(s2) && s2.length >= 50 && s2.length <= 5000) seqs.push(s2.toUpperCase().replace(/U/g, "T"));
    }
    if (!seqs.length) throw err(400, "no valid DNA sequences (need 50-5000 bp each)");
    const preds = await scoreSequences(seqs);
    const verdicts = preds.map((p, i) => {
      const gap = specificityGap(p, cell);
      const sub = TARGET_CELLS.map((c) => p[CELL_IDX[c]]);
      const peak = Math.max.apply(null, sub);
      const comp = sequenceComplexity(seqs[i]);
      return {
        predicted_gap: gap,
        most_active_cell: TARGET_CELLS[sub.indexOf(peak)],
        predicted_fail: gap <= 0,
        low_activity: peak < ACTIVITY_FLOOR,
        low_complexity: comp < COMPLEXITY_FLOOR,
      };
    });
    const ranked = verdicts.map((v, idx) => [idx, v]).sort((a, b) => b[1].predicted_gap - a[1].predicted_gap);
    const n = ranked.length;
    const order = ranked.map(([idx, v], i) => ({
      rank: i + 1,
      input_index: idx,
      predicted_gap: roundTo(v.predicted_gap, 3),
      predicted_most_active_cell: v.most_active_cell,
      predicted_fail: v.predicted_fail,
      low_activity: v.low_activity,
      low_complexity: v.low_complexity,
    }));
    const nFail = verdicts.filter((v) => v.predicted_fail).length;
    const half = ranked.slice(0, Math.max(1, Math.floor(n / 2)));
    const halfFail = half.filter(([, v]) => v.predicted_fail).length / half.length;
    const overall = nFail / n;
    return {
      n,
      target_cell: cell,
      predicted_fail_count: nFail,
      low_activity_count: verdicts.filter((v) => v.low_activity).length,
      low_complexity_count: verdicts.filter((v) => v.low_complexity).length,
      predicted_fail_rate: roundTo(overall, 4),
      safest_half_fail_rate: roundTo(halfFail, 4),
      failure_reduction_pct_safest_half: overall > 0 ? Math.round(100 * (1 - halfFail / overall)) : 0,
      ranking: order,
    };
  }

  // CLOSED LOOP, deterministic: apply the mechanistic motif edit the diagnosis prescribes and
  // re-score with the same gate. An in-silico self-consistency check on one design, not wet-lab
  // validation: the model that flagged the design re-scores its own proposed edit.
  async function redesign(body) {
    const seq = cleanSeq(body.sequence), cell = checkTarget(body.target_cell);
    const before = gateReport(seq, cell, (await scoreSequences([seq]))[0]);
    const off = before.predicted_most_active_cell;

    const edits = [];
    let chars = seq.split("");
    for (const site of await driverSites(seq, off, 5)) {
      const p = site.pos, L = site.length;
      if (p + L <= chars.length) {
        const filler = "GAATTC".repeat(Math.floor(L / 6) + 1).slice(0, L);
        chars.splice(p, L, ...filler.split(""));
        edits.push({ action: "disrupt", tf: site.tf, cell: off, pos: p });
      }
    }
    let edited = chars.join("");

    const scan = await scanSequence(seq, cell, off);
    const present = new Set(Object.keys(((scan.by_cell[cell] || {}).tfs) || {}));
    const offTfs = new Set(DRIVERS[off] || []);
    let nInj = 0;
    for (const name of DRIVERS[cell] || []) {
      if (present.has(name) || offTfs.has(name)) continue;
      const cons = await consensusSeq(name);
      if (!cons) continue;
      for (let copy = 0; copy < 2; copy++) {
        const at = Math.min(edited.length, 25 + nInj * (cons.length + 10));
        edited = edited.slice(0, at) + cons + edited.slice(at);
        edits.push({ action: "add", tf: name, cell, motif: cons, pos: at });
        nInj++;
      }
      if (nInj >= 6) break;
    }
    edited = edited.slice(0, 500);

    const after = gateReport(edited, cell, (await scoreSequences([edited]))[0]);
    const pick = (r) => ({
      predicted_most_active_cell: r.predicted_most_active_cell,
      predicted_specificity_gap: r.predicted_specificity_gap,
      predicted_fail: r.predicted_fail,
      calibrated_fail_probability: r.calibrated_fail_probability,
    });
    return {
      before: pick(before),
      after: pick(after),
      gap_delta: roundTo(after.predicted_specificity_gap - before.predicted_specificity_gap, 3),
      fixed: before.predicted_fail && !after.predicted_fail,
      edits,
      edited_sequence: edited,
    };
  }

  /* ------------------------------------------------- the Claude agent layer (agents.js) */
  const agentsReady = () => !!(window.CFAgents && window.CFAgents.hasKey());

  // The same text the server put in front of the redesign agent, so the prompt is grounded in
  // the PWM scan rather than in the model's memory of which TF drives which cell.
  function scanSummary(scan) {
    if (!scan) return "";
    const lines = [];
    for (const [cell, d] of Object.entries(scan.by_cell || {})) {
      const names = Object.keys(d.tfs || {});
      if (names.length) {
        const tfs = names.map((tf) => {
          const v = d.tfs[tf];
          return `${tf} (${v.n_sites} sites, JASPAR ${v.matrix_id})`;
        }).join(", ");
        lines.push(`${cell} driver motifs actually present in the sequence: ${tfs}`);
      } else {
        lines.push(`${cell} driver motifs present in the sequence: NONE`);
      }
    }
    return "GROUNDED MOTIF SCAN (JASPAR log-odds PWM scan of the actual sequence):\n" + lines.join("\n");
  }

  function ruleFallback(report, note) {
    const out = { gate: report, verdict: ruleVerdict(report), agents: false };
    if (note) out.agents_note = note;
    return out;
  }

  async function diagnose(body) {
    const seq = cleanSeq(body.sequence), cell = checkTarget(body.target_cell);
    const report = gateReport(seq, cell, (await scoreSequences([seq]))[0]);
    if (!window.CFAgents) {
      return ruleFallback(report,
        "The agent layer did not load, so this is the deterministic gate verdict, which needs no " +
        "API and is what every published number in this repository is computed from.");
    }
    if (!(await window.CFAgents.ensureKey())) {
      return ruleFallback(report,
        "No Anthropic key given, so this is the deterministic gate verdict, which needs no API " +
        "and is what every published number in this repository is computed from.");
    }
    const t0 = performance.now();
    let res;
    try {
      const scanNeeded = report.predicted_fail || report.predicted_specificity_gap < 0.5;
      const scan = scanNeeded ? await scanSequence(seq, cell, report.predicted_most_active_cell) : null;
      res = await window.CFAgents.diagnose(report, scan);
      if (scan) {
        res.motif_scan = scan;
        const rd = await window.CFAgents.motifRedesign(report, scan, scanSummary(scan));
        if (rd) res.redesign = rd;
      }
    } catch (e) {
      // Same contract the server kept: an upstream failure becomes the honest deterministic
      // verdict with the reason attached, never a bare error in place of an answer.
      return ruleFallback(report, "The agent layer could not run: " + e.message);
    }
    const out = {
      gate: report,
      reviews: res.reviews,
      verdict: res.verdict,
      motif_scan: res.motif_scan,
      redesign: res.redesign,
      agents: true,
      ms: Math.round(performance.now() - t0),
      cost_usd: window.CFAgents.costUsd(),
    };
    window.CFAgents.showCost();
    return out;
  }

  async function rescue(body) {
    const seq = cleanSeq(body.sequence), cell = checkTarget(body.target_cell);
    if (!window.CFAgents) throw err(503, "the agent layer did not load");
    if (!(await window.CFAgents.ensureKey())) {
      throw err(503, "Claude rescue runs on your own Anthropic key; none was given. The " +
        "deterministic fix and the gate verdict need no key and still stand.");
    }
    const score = async (s, t) => {
      const r = gateReport(s, t, (await scoreSequences([s]))[0]);
      return {
        gap: r3(r.predicted_specificity_gap),
        most_active: r.predicted_most_active_cell,
        fail: r.predicted_fail,
      };
    };
    const t0 = performance.now();
    let out;
    try {
      out = await window.CFAgents.rescue(seq, cell, { score, driverSites, consensusSeq, DRIVERS }, 4);
    } catch (e) {
      throw err(503, "Claude rescue is unavailable: " + e.message);
    }
    out.ms = Math.round(performance.now() - t0);
    out.cost_usd = window.CFAgents.costUsd();
    window.CFAgents.showCost();
    return out;
  }

  async function api(path, body) {
    switch (path) {
      case "/health":
        return {
          ok: true,
          models_warm: !!models,
          agents: agentsReady(),
          agents_configured: !!window.CFAgents,
          agents_degraded_reason: agentsReady()
            ? null
            : "the Claude agent layer runs on your own Anthropic key, entered in this tab when you ask for a diagnosis",
        };
      case "/meta":
        return {
          target_cells: TARGET_CELLS,
          all_cells: MPRA_CELL_LINES,
          headline: HEADLINE,
          screenaudit: await getJson("data/screenaudit_result.json"),
          agents_enabled: !!window.CFAgents,
        };
      case "/predict": return predict(body);
      case "/motifs": return motifScan(body);
      case "/batch": return batch(body);
      case "/redesign": return redesign(body);
      case "/example": return getJson("data/hero.json");
      case "/example-brain": return getJson("data/brain_hero.json");
      case "/example-batch": {
        const designs = (await getJson("data/batch_example.json")) || [];
        return { target_cell: "HepG2", sequences: designs.map((d) => d.seq) };
      }
      case "/diagnose": return diagnose(body);
      case "/rescue": return rescue(body);
      default:
        throw err(404, `no such API endpoint: ${path}`);
    }
  }

  window.CF = {
    api,
    loadModels,
    onProgress: (f) => { listeners.add(f); f(progress); return () => listeners.delete(f); },
    ready: (async () => { CALIB = await getJson("data/calibration_iso.json"); })(),
    // exposed for the browser-vs-Python accuracy check (webdemo/parity.test.mjs)
    _internals: { scoreSequences, gateReport, ruleVerdict, scanSequence, sequenceComplexity, specificityGap, pFail },
  };
})();
