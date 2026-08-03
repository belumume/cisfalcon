/* CisFalcon frontend. Real API wiring, no mocks.
   Same-origin /api. Overview proof card is a scripted animation of the REAL
   hero's numbers; every other dynamic value comes from a live API call. */

const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];

const api = (p, body) =>
  fetch("/api" + p, body
    ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }
    : undefined)
    .then(async (r) => { const j = await r.json().catch(() => ({})); if (!r.ok) throw new Error(j.detail || r.statusText); return j; });

const esc = (s) => String(s == null ? "" : s).replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));
const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
const fmtGap = (g) => (g >= 0 ? "+" : "−") + Math.abs(g).toFixed(2);
const gapPos = (g) => clamp(50 + g * 10, 6, 94) + "%";

const RED = "#FF5B4F", GREEN = "#35D48A", AMBER = "#E7B24A", CYAN = "#38C6D6";
const GLOW = { RED: "rgba(255,91,79,.5)", GREEN: "rgba(53,212,138,.5)", CYAN: "rgba(56,198,214,.35)" };
const TARGET_CELLS_FALLBACK = ["NT2_D1", "GM12878", "786_O", "SKNSH", "WERI_Rb1", "SJCRH30", "HepG2", "K562", "MCF7", "HeLaS3"];
const VALIDATED_CELLS = ["K562", "HepG2", "SKNSH"]; // the 3 cross-lab cells the calibration is fit on; others are extrapolated

let META = null;
const inspCache = new Map(); // id -> { rep, scan, item }
const diagCache = new Map(); // id -> /diagnose response (cache the real Claude call per design)
const rescueCache = new Map(); // id -> /rescue response (Claude's closed-loop rescue per design)

/* ---------------- nav ---------------- */
let verifyLoaded = false;
function switchView(name) {
  $$(".nav-btn").forEach((b) => b.classList.toggle("on", b.dataset.view === name));
  $$(".view").forEach((v) => v.classList.toggle("on", v.id === "view-" + name));
  const host = $(".views"); if (host) host.scrollTop = 0;
  if (name === "verify" && !verifyLoaded) { verifyLoaded = true; loadVerify(); }
}
$$("[data-view]").forEach((el) => el.addEventListener("click", () => switchView(el.dataset.view)));

/* ---------------- overview proof card (scripted, real hero numbers) ---------------- */
const OV_PHASES = [
  { name: "FLAG", color: RED, hep: "18%", off: "90%", fill: RED, op: 1, glow: GLOW.RED,
    winner: "K562", winnerColor: RED, gap: "−3.0", gapColor: RED, pos: "20%",
    status: "Predicted to fail. Most-active cell is K562, not the HepG2 target. Specificity gap −3.0 (fail when gap ≤ 0). Wet-lab measured K562 +6.5, HepG2 −0.1 confirms it." },
  { name: "FIX", color: AMBER, hep: "18%", off: "90%", fill: RED, op: 0.3, glow: "rgba(255,91,79,.25)",
    winner: "K562", winnerColor: "rgba(255,91,79,.55)", gap: "−3.0", gapColor: "rgba(255,91,79,.5)", pos: "20%",
    status: "Prescribed edit: disrupt K562 drivers GATA1, TAL1, GATA2; install HepG2 grammar HNF4A, HNF1A, CEBPA. Old scores are now stale." },
  { name: "RE-SCORE", color: CYAN, hep: "18%", off: "90%", fill: CYAN, op: 0.18, glow: GLOW.CYAN,
    winner: "···", winnerColor: CYAN, gap: "···", gapColor: CYAN, pos: "50%",
    status: "Re-scoring with the same frozen external model. No fine-tuning, no self-report." },
  { name: "PASS", color: GREEN, hep: "80%", off: "46%", fill: GREEN, op: 1, glow: GLOW.GREEN,
    winner: "HepG2", winnerColor: GREEN, gap: "+1.0", gapColor: GREEN, pos: "60%",
    status: "Passes. Most-active cell is now HepG2. Specificity gap +1.0. In-silico consistency check, ahead of wet-lab validation." },
];
const OV_DUR = [3600, 2400, 2200, 4200];
let ovStep = 0, ovTimer = null;
function ovRender(i) {
  const p = OV_PHASES[i];
  const set = (id, fn) => { const el = $("#" + id); if (el) fn(el); };
  set("ov-dot", (e) => { e.style.background = p.color; e.style.boxShadow = "0 0 8px " + p.color; });
  set("ov-pname", (e) => { e.textContent = p.name; e.style.color = p.color; });
  set("ov-hep", (e) => { e.style.width = p.hep; e.style.background = p.fill; e.style.opacity = p.op; e.style.boxShadow = "0 0 16px " + p.glow; });
  set("ov-off", (e) => { e.style.width = p.off; e.style.background = p.fill; e.style.opacity = p.op; e.style.boxShadow = "0 0 16px " + p.glow; });
  set("ov-winner", (e) => { e.textContent = p.winner; e.style.color = p.winnerColor; });
  set("ov-gapval", (e) => { e.textContent = p.gap; e.style.color = p.gapColor; });
  set("ov-needle", (e) => { e.style.left = p.pos; e.style.background = p.gapColor; e.style.boxShadow = "0 0 10px " + p.gapColor; });
  set("ov-status", (e) => { e.textContent = p.status; });
  set("ov-statusbox", (e) => { e.style.borderLeftColor = p.color; });
}
function ovArm() {
  clearTimeout(ovTimer);
  ovTimer = setTimeout(() => { ovStep = (ovStep + 1) % 4; ovRender(ovStep); ovArm(); }, OV_DUR[ovStep]);
}
function ovStart() {
  ovStep = 0; ovRender(0);
  const rm = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  if (!rm) ovArm();
  const pc = document.querySelector(".proof");
  if (pc) {
    pc.addEventListener("mouseenter", () => clearTimeout(ovTimer));
    pc.addEventListener("mouseleave", () => { if (!rm) ovArm(); });
  }
}

/* ---------------- verify: batch table (real /example-batch + /batch) ---------------- */
async function loadVerify() {
  const R = $("#vf-rows");
  try {
    const [hero, batch] = await Promise.all([
      api("/example").catch(() => null),
      api("/example-batch"),
    ]);
    const batchSeqs = batch.sequences || [];
    const target = batch.target_cell || "HepG2";
    const scored = await api("/batch", { sequences: batchSeqs, target_cell: target });
    const items = [];
    for (const r of (scored.ranking || [])) {
      const idx = r.input_index;
      items.push({
        id: "AF-" + String(idx + 1).padStart(2, "0"),
        seq: batchSeqs[idx], target,
        gap: r.predicted_gap, cell: r.predicted_most_active_cell, fail: r.predicted_fail,
      });
    }
    // add the real flagship hero (from /example) so the clean flip is demoable here too
    if (hero && hero.sequence) {
      try {
        const hp = await api("/predict", { sequence: hero.sequence, target_cell: hero.target_cell || "HepG2" });
        items.push({
          id: "H2-0417", hero: true, seq: hero.sequence, target: hero.target_cell || "HepG2",
          gap: hp.predicted_specificity_gap, cell: hp.predicted_most_active_cell, fail: hp.predicted_fail,
        });
      } catch (_) { /* hero optional */ }
    }
    items.sort((a, b) => b.gap - a.gap); // safest-first
    renderVerifyRows(items);
    const flagged = items.filter((x) => x.fail);
    const pick = (items.find((x) => x.hero) && flagged.find((x) => x.hero)) || flagged[flagged.length - 1] || items[0];
    if (pick) selectDesign(pick);
    else $("#insp-content").innerHTML = `<div class="insp-empty"><div>no designs returned</div></div>`;
  } catch (e) {
    R.innerHTML = `<div class="empty" style="padding:24px 10px">could not reach the scoring API<br><span class="dim">${esc(e.message)}</span></div>`;
    $("#insp-content").innerHTML = `<div class="insp-empty"><div>the verifier needs the live backend</div><div class="dim">${esc(e.message)}</div></div>`;
  }
}

function renderVerifyRows(items) {
  const flagged = items.filter((x) => x.fail).length;
  $("#vf-all").textContent = items.length;
  $("#vf-flagged").textContent = flagged;
  $("#vf-clear").textContent = items.length - flagged;
  const R = $("#vf-rows");
  R.innerHTML = "";
  for (const it of items) {
    const row = document.createElement("button");
    row.className = "vf-row" + (it.fail ? "" : " pass");
    row.dataset.id = it.id;
    const gapColor = it.fail ? "#C13B37" : "#227A4E";
    const off = it.fail ? esc(it.cell) : "–";
    row.innerHTML =
      `<span class="id">${esc(it.id)}</span>` +
      `<span class="gap" style="color:${gapColor}">${fmtGap(it.gap)}</span>` +
      `<span class="off">${off}</span>` +
      `<span class="status ${it.fail ? "status-flag" : "status-clear"}">${it.fail ? "FLAGGED" : "CLEAR"}</span>`;
    row.addEventListener("click", () => selectDesign(it));
    R.appendChild(row);
  }
  VERIFY_ITEMS = items;
}
let VERIFY_ITEMS = [];

/* ---------------- inspector (real /predict + /motifs) ---------------- */
const ROC_SVG = `<svg width="164" height="132" viewBox="0 0 190 158" style="display:block">
  <line x1="32" y1="140" x2="32" y2="12" stroke="rgba(150,190,210,.3)" stroke-width="1"></line>
  <line x1="32" y1="140" x2="178" y2="140" stroke="rgba(150,190,210,.3)" stroke-width="1"></line>
  <line x1="32" y1="140" x2="178" y2="12" stroke="#E7B24A" stroke-width="1.2" stroke-dasharray="4 4" opacity=".8"></line>
  <path d="M32,140 C60,72 100,32 178,12 L178,140 Z" fill="rgba(53,212,138,.12)"></path>
  <path d="M32,140 C60,72 100,32 178,12" fill="none" stroke="#35D48A" stroke-width="2.2" stroke-dasharray="300" style="animation:cf-draw 1.6s ease-out"></path>
  <text x="100" y="52" font-family="Space Grotesk" font-weight="700" font-size="22" fill="#C6D0D8">0.80</text>
  <text x="101" y="66" font-family="IBM Plex Mono, monospace" font-size="8" letter-spacing="1.5" fill="#8996A0">AUROC</text>
  <text x="119" y="108" font-family="IBM Plex Mono, monospace" font-size="7.5" fill="#C79A3A" transform="rotate(-31 119 108)">chance 0.50</text>
  <text x="90" y="154" text-anchor="middle" font-family="IBM Plex Mono, monospace" font-size="7.5" fill="#5C6771">false positive rate</text>
</svg>`;

const MOTIF_FOOT = 6; // indicative footprint (px); /motifs returns start position only

// collect hits from the motif scan; classify off-target (red) vs target (green)
function collectHits(scan) {
  const hits = [];
  if (!scan || !scan.by_cell) return hits;
  const offCell = scan.off_target_cell || scan.predicted_most_active_cell;
  for (const [cell, d] of Object.entries(scan.by_cell)) {
    const isOff = cell === offCell;
    for (const [tf, v] of Object.entries(d.tfs || {})) {
      for (const t of (v.top || [])) {
        if (typeof t.pos === "number") hits.push({ pos: t.pos, tf, cell, isOff, score: t.score || 0 });
      }
    }
  }
  return hits;
}

function selectDesign(item) {
  $$(".vf-row").forEach((r) => r.classList.toggle("sel", r.dataset.id === item.id));
  const scan = $("#insp-scan"); if (scan) scan.style.opacity = "1";
  $("#insp-id").textContent = "/ " + item.id;
  $("#insp-dot").style.background = "#5C6771";
  $("#insp-content").innerHTML = `<div class="insp-empty"><span class="spin"></span><div>scoring ${esc(item.id)} against the frozen external model…</div></div>`;

  const cached = inspCache.get(item.id);
  const work = cached
    ? Promise.resolve([cached.rep, cached.scan])
    : Promise.all([
        api("/predict", { sequence: item.seq, target_cell: item.target }),
        api("/motifs", { sequence: item.seq, target_cell: item.target }).catch(() => null),
      ]);
  work.then(([rep, scanD]) => {
    inspCache.set(item.id, { rep, scan: scanD, item });
    buildInspector(item, rep, scanD);
    if (scan) setTimeout(() => (scan.style.opacity = "0"), 350);
  }).catch((e) => {
    if (scan) scan.style.opacity = "0";
    $("#insp-content").innerHTML = `<div class="insp-empty"><div>could not score this design</div><div class="dim">${esc(e.message)}</div></div>`;
  });
}

function barHeights(rep) {
  const t = rep.predicted_profile_log2fc[rep.target_cell] ?? 0;
  const w = rep.predicted_profile_log2fc[rep.predicted_most_active_cell] ?? 0;
  const lo = Math.min(0, t, w), hi = Math.max(0.5, t, w), span = (hi - lo) || 1;
  const h = (v) => clamp(((v - lo) / span) * 100, 4, 100) + "%";
  return { hep: h(t), off: h(w), tVal: t, wVal: w };
}

function seqMapHTML(seq, hits) {
  const n = seq.length;
  const color = new Array(n).fill(null);
  for (const hh of hits) { for (let k = hh.pos; k < Math.min(n, hh.pos + MOTIF_FOOT); k++) color[k] = hh.isOff ? RED : GREEN; }
  let ticks = "";
  for (let i = 0; i < n; i++) {
    const c = color[i];
    ticks += `<div class="tick${c ? " hit" : ""}"${c ? ` style="background:${c}"` : ""}></div>`;
  }
  // one label per TF at its top hit
  const seen = {}, labels = [];
  for (const hh of hits.slice().sort((a, b) => b.score - a.score)) {
    if (seen[hh.tf]) continue; seen[hh.tf] = 1;
    if (labels.length >= 6) break;
    labels.push(`<span class="lab" style="left:${(hh.pos / n) * 100}%;color:${hh.isOff ? RED : GREEN}">${esc(hh.tf)}</span>`);
  }
  return { ticks, labels: labels.join("") };
}

function seqZoomHTML(seq, hits) {
  const n = seq.length, W = Math.min(44, n);
  const primary = hits.slice().sort((a, b) => b.score - a.score)[0];
  const center = primary ? primary.pos + Math.floor(MOTIF_FOOT / 2) : Math.floor(n / 2);
  let start = clamp(center - Math.floor(W / 2), 0, Math.max(0, n - W));
  const end = start + W;
  const hitAt = new Array(n).fill(null);
  for (const hh of hits) { for (let k = hh.pos; k < Math.min(n, hh.pos + MOTIF_FOOT); k++) hitAt[k] = hh.isOff ? RED : GREEN; }
  let bases = "";
  for (let i = start; i < end; i++) {
    const c = hitAt[i];
    bases += `<span class="base${c ? " mo" : ""}"${c ? ` style="color:${c};background:${c === RED ? "rgba(255,91,79,.14)" : "rgba(53,212,138,.14)"}"` : ""}>${esc(seq[i] || "")}</span>`;
  }
  let bracket = "", zlbl = `zoom · bp ${start + 1}–${end}`;
  if (primary) {
    const bs = clamp(primary.pos, start, end), be = clamp(primary.pos + MOTIF_FOOT, start, end);
    const left = ((bs - start) / W) * 100, width = Math.max(4, ((be - bs) / W) * 100);
    const col = primary.isOff ? RED : GREEN;
    bracket = `<div class="arc" style="left:${left}%;width:${width}%;border-color:${col}"></div>` +
      `<div class="txt" style="left:${left + width / 2}%;color:${col}">${esc(primary.tf)} · bp ${primary.pos + 1}</div>`;
    zlbl = `zoom · bp ${start + 1}–${end} · ${primary.isOff ? "off-target" : "target"} driver`;
  }
  return { bases, bracket, zlbl };
}

function profileHTML(rep) {
  const cells = (META && META.target_cells) || TARGET_CELLS_FALLBACK;
  const prof = rep.predicted_profile_log2fc || {};
  const vals = cells.map((c) => prof[c] ?? 0);
  const lo = Math.min(0, ...vals), hi = Math.max(0.001, ...vals), span = (hi - lo) || 1;
  const zero = ((0 - lo) / span) * 100;
  return cells.map((c) => {
    const v = prof[c] ?? 0, w = ((v - lo) / span) * 100;
    const left = Math.min(zero, w), width = Math.abs(w - zero);
    const cls = c === rep.target_cell ? "tgt" : c === rep.predicted_most_active_cell ? "win" : "";
    return `<div class="profile-row ${cls}"><div class="cn">${esc(c)}</div>` +
      `<div class="track"><div class="zero" style="left:${zero}%"></div><div class="fill" style="left:${left}%;width:${width}%"></div></div>` +
      `<div class="val">${v >= 0 ? "+" : "−"}${Math.abs(v).toFixed(2)}</div></div>`;
  }).join("");
}

function buildInspector(item, rep, scan) {
  const fail = rep.predicted_fail;
  const col = fail ? RED : GREEN, glow = fail ? GLOW.RED : GLOW.GREEN;
  const b = barHeights(rep);
  const hits = collectHits(scan);
  const offCell = rep.predicted_most_active_cell;
  const motifCol = fail ? RED : GREEN;
  const driverList = (() => {
    if (!scan || !scan.by_cell) return "motif scan unavailable";
    const cell = fail ? (scan.off_target_cell || offCell) : rep.target_cell;
    const d = scan.by_cell[cell];
    const tfs = d && d.tfs ? Object.keys(d.tfs) : [];
    return tfs.length ? tfs.join(" · ") : "no driver motifs";
  })();
  const map = seqMapHTML(item.seq, hits);
  const zoom = seqZoomHTML(item.seq, hits);
  const winnerLabel = fail ? offCell : rep.target_cell;

  const validated = VALIDATED_CELLS.includes(rep.target_cell);
  const probPct = (rep.calibrated_fail_probability * 100).toFixed(0);
  // Above ~0.6 the reliability curve is thinly measured: held out, the 0.6-0.7 bin runs 0.696
  // predicted against 0.619 observed on 42 designs and 0.7-0.8 runs 0.760 against 0.500 on 18.
  // The low ECE is driven by the lowest bin, which holds 36,912 of 46,718 designs. That caveat
  // was already carried on four surfaces; this is the one where the user actually decides
  // whether to synthesize, and it was the only one printing the number unhedged.
  const thinlyMeasured = rep.calibrated_fail_probability > 0.6;
  const calibNote = validated
    ? thinlyMeasured
      ? `Calibrated failure probability ${probPct}% (above ~60% the calibration is thinly measured, so trust the ranking rather than the absolute number).`
      : `Calibrated failure probability ${probPct}%.`
    : `Failure probability ${probPct}% (calibration fit on the 3 cross-lab cells K562, HepG2, SKNSH; extrapolated to ${esc(rep.target_cell)}).`;
  const statusLine = rep.low_complexity
    ? `Degenerate or repetitive sequence (k-mer complexity ${rep.complexity}, a homopolymer or tandem repeat rather than a diverse enhancer-like sequence). This is not a credible enhancer design, so the specificity call is not meaningful — real designs use over 80% of their k-mer vocabulary; this one is far below that.`
    : rep.low_activity
    ? `Predicted weakly active in every cell (peak activity ${rep.peak_activity} log2FC, within the range of random sequences). This may not be a functional enhancer, so the specificity call is low-confidence — a relative specificity score is only meaningful once a sequence is actually active somewhere.`
    : fail
    ? `Predicted to fail. Most-active cell is ${esc(offCell)}, not the ${esc(rep.target_cell)} target. Specificity gap ${fmtGap(rep.predicted_specificity_gap)} (fail when gap ≤ 0). ${calibNote}`
    : `Predicted specific. Most-active cell is its ${esc(rep.target_cell)} target. Specificity gap ${fmtGap(rep.predicted_specificity_gap)}. Cleared for synthesis.`;

  const seqN = item.seq.length;
  const nBases = (item.seq.match(/[^ACGTacgt]/g) || []).length;
  const seqWarns = [];
  if (rep.low_complexity) seqWarns.push(`Degenerate/repetitive: k-mer complexity ${rep.complexity} (a homopolymer or tandem repeat, not enhancer-like), so the specificity call is not meaningful.`);
  if (rep.low_activity) seqWarns.push(`Not enhancer-like: predicted weakly active in every cell (peak ${rep.peak_activity} log2FC), so its specificity call is low-confidence.`);
  if ((rep.seq_len || seqN) > 500) seqWarns.push(`Only the first 500 bp are scored (the model's input window); this design is ${rep.seq_len || seqN} bp.`);
  if (seqN && nBases / seqN > 0.1) seqWarns.push(`${Math.round((nBases / seqN) * 100)}% of the bases are non-ACGT and read as blanks by the model.`);
  const seqWarnHTML = seqWarns.length ? `<div class="insp-warn">${esc(seqWarns.join(" "))}</div>` : "";

  const amber = rep.low_complexity || rep.low_activity;
  $("#insp-dot").style.background = col; $("#insp-dot").style.boxShadow = "0 0 8px " + col;
  const stamp = $("#insp-stamp");
  stamp.textContent = rep.low_complexity ? "LOW COMPLEXITY" : (rep.low_activity ? "LOW ACTIVITY" : (fail ? "FLAGGED" : "CLEAR"));
  stamp.style.opacity = "1"; stamp.style.color = amber ? AMBER : col;
  stamp.style.background = amber ? "rgba(231,178,74,.1)" : (fail ? "rgba(255,91,79,.1)" : "rgba(53,212,138,.1)");
  stamp.style.borderColor = amber ? "rgba(231,178,74,.55)" : (fail ? "rgba(255,91,79,.55)" : "rgba(53,212,138,.55)");

  $("#insp-content").innerHTML =
  `<div class="insp-grid">
    <div class="insp-left">
      <span class="cap">PREDICTED ACTIVITY · relative</span>
      <div class="vbars">
        <div class="vbar"><div class="hd"><div class="cell">${esc(rep.target_cell)}</div><div class="rl">TARGET</div></div>
          <div class="col"><div class="fill" id="ins-hep" style="height:${b.hep};background:${col};opacity:1;box-shadow:0 0 22px ${glow}"></div></div></div>
        <div class="vbar"><div class="hd"><div class="cell">${esc(offCell)}</div><div class="rl">${fail ? "OFF-TARGET" : "NEXT CELL"}</div></div>
          <div class="col"><div class="fill" id="ins-off" style="height:${b.off};background:${col};opacity:1;box-shadow:0 0 22px ${glow}"></div></div></div>
      </div>
      <div class="insp-winner">most-active: <b id="ins-winner" style="color:${col}">${esc(winnerLabel)}</b></div>
      <div class="insp-gapbox">
        <div class="top"><span class="glbl">SPECIFICITY GAP</span><span class="gval" id="ins-gap" style="color:${col}">${fmtGap(rep.predicted_specificity_gap)}</span></div>
        <div class="gapscale"><div class="mid"></div><div class="needle" id="ins-needle" style="left:${gapPos(rep.predicted_specificity_gap)};background:${col};box-shadow:0 0 10px ${col}"></div></div>
        <div class="note">fail when gap ≤ 0</div>
      </div>
    </div>

    <div class="insp-right">
      <div class="d-panel">
        <div class="hd"><span class="cap" id="ins-seqcap">DESIGNED ENHANCER · ${rep.seq_len || item.seq.length} bp</span><span class="motifset" id="ins-motifset" style="color:${motifCol}">${esc(driverList)}</span></div>
        <div class="seqmap-ruler" id="ins-ruler"><span>0</span><span>${Math.round((rep.seq_len || item.seq.length) / 4)}</span><span>${Math.round((rep.seq_len || item.seq.length) / 2)}</span><span>${Math.round(3 * (rep.seq_len || item.seq.length) / 4)}</span><span>${rep.seq_len || item.seq.length}</span></div>
        <div class="seqmap" id="ins-seqmap">${map.ticks}</div>
        <div class="seqmap-labels" id="ins-seqlabels">${map.labels}</div>
        <div class="seqzoom">
          <div class="zlbl" id="ins-zlbl">${zoom.zlbl}</div>
          <div class="bases" id="ins-zbases">${zoom.bases}</div>
          <div class="bracket" id="ins-zbracket">${zoom.bracket}</div>
        </div>
      </div>

      <div class="d-panel">
        <div class="hd"><span class="cap">PREDICTED ACTIVITY ACROSS CELL TYPES · external model</span></div>
        <div class="profile" id="ins-profile">${profileHTML(rep)}</div>
      </div>

      <div class="insp-bottom">
        <div class="roc-card">
          <div class="cap">CROSS-LAB ROC</div>
          ${ROC_SVG}
          <div class="note">n=93,435 · held-out lab (Gosai/Tewhey)</div>
        </div>
        <div class="legend-card">
          <div class="cap">LEGEND</div>
          <div class="legend-row"><span class="sw" style="background:${RED}"></span>predicted fail (gap ≤ 0)</div>
          <div class="legend-row"><span class="sw" style="background:${GREEN}"></span>predicted pass (gap &gt; 0)</div>
          <div class="legend-row"><span class="sw" style="background:${RED}"></span>off-target driver motif</div>
          <div class="legend-row"><span class="sw" style="background:${GREEN}"></span>target driver motif</div>
          <div class="fine">JASPAR-grounded motif scan on the frozen external model. No self-report.</div>
        </div>
      </div>
    </div>
  </div>

  <div class="insp-actions">
    <button class="btn-diagnose" id="ins-diagnose">Run Claude diagnosis
      <svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M8 1.5l1.6 3.4 3.7.5-2.7 2.6.7 3.7L8 13.4 4.7 15l.7-3.7L2.7 8.7l3.7-.5z"></path></svg>
    </button>
    <button class="btn-fix" id="ins-fix"${fail ? "" : " hidden"}>Apply ${esc(rep.target_cell)}-grammar fix
      <svg width="13" height="13" viewBox="0 0 14 14" fill="none" stroke="#14171B" stroke-width="1.6"><path d="M2 7h9M7 3l4 4-4 4"></path></svg>
    </button>
    <button class="btn-rescue" id="ins-rescue"${fail ? "" : " hidden"}>Let Claude rescue it
      <svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M13.5 8a5.5 5.5 0 1 1-1.6-3.9M13.5 2v3h-3"></path></svg>
    </button>
    <span class="badge-clear" id="ins-clear"${fail ? " hidden" : ""}>cleared for synthesis</span>
    <span class="insp-hint" id="ins-hint">in-silico consistency check, ahead of wet-lab</span>
  </div>

  <div class="diag-wrap" id="ins-diagnosis"></div>

  <div class="rescue-wrap" id="ins-rescue-out"></div>

  ${seqWarnHTML}

  <div class="insp-statusbar" id="ins-statusbar" style="border-left-color:${col}">
    <span class="pn" id="ins-pn" style="color:${col}">${fail ? "FLAG" : "CLEAR"}</span>
    <span class="st" id="ins-st">${statusLine}</span>
    <span class="rt">frozen external model</span>
  </div>`;

  const fixBtn = $("#ins-fix");
  if (fixBtn) fixBtn.addEventListener("click", () => applyFix(item));
  const dxBtn = $("#ins-diagnose");
  if (dxBtn) dxBtn.addEventListener("click", () => runDiagnosis(item));
  const rxBtn = $("#ins-rescue");
  if (rxBtn) rxBtn.addEventListener("click", () => runRescue(item));
  const prevRx = rescueCache.get(item.id);
  const rxHost = $("#ins-rescue-out");
  if (prevRx && rxHost) renderRescue(rxHost, prevRx);
  const prevDiag = diagCache.get(item.id);
  const diagHost = $("#ins-diagnosis");
  if (prevDiag && diagHost) renderDiagnosis(diagHost, prevDiag);
}

/* ---------------- live Claude diagnosis (real /diagnose: 3 Sonnet-5 lenses -> Opus-4.8 adjudicator) ---------------- */
function diagLoadingHTML() {
  const ag = (name) => `<span class="ag"><span class="spin"></span>${name}</span>`;
  return `<div class="diag-panel loading">
    <div class="diag-hd"><span class="cap">CLAUDE VERIFIER · first-party Anthropic API</span><span class="diag-live"><span class="ld"></span>agents reasoning</span></div>
    <div class="diag-arch">${ag("mechanism · Sonnet 5")}${ag("precedent · Sonnet 5")}${ag("adversary · Sonnet 5")}<span class="darrow">&rarr;</span><span class="ag op"><span class="spin"></span>adjudicator · Opus 4.8</span></div>
    <div class="diag-note">Three independent reasoning lenses run in parallel on the frozen gate report, then Opus synthesizes one pre-synthesis verdict grounded in the measured benchmark. Live multi-agent call, ~20 to 30s.</div>
  </div>`;
}

function lensText(t) {
  if (t && typeof t === "object") return t.refused ? "Declined by the safety classifier; the other lenses proceeded." : JSON.stringify(t);
  return (t == null ? "" : String(t)).trim();
}

// minimal, XSS-safe markdown: escape first, then render on the escaped text (safety net for any md a model emits)
function mdLite(s) {
  let t = esc((s == null ? "" : String(s)).trim());
  t = t.replace(/^\s*#{1,6}\s*(.+)$/gm, '<b class="mdh">$1</b>');
  t = t.replace(/\*\*([^*]+)\*\*/g, "<b>$1</b>");
  t = t.replace(/^\s*[-*]\s+(.+)$/gm, '<span class="mdb">• $1</span>');
  return t.replace(/\n{2,}/g, "<br><br>").replace(/\n/g, "<br>");
}

function renderDiagnosis(host, out) {
  const v = (out.verdict && typeof out.verdict === "object") ? out.verdict : {};
  const refusedSynth = out.verdict && out.verdict.refused;
  const reviews = out.reviews || null;
  const verdict = String(v.verdict || (refusedSynth ? "DECLINED" : "—")).toUpperCase();
  const vcol = verdict === "FAIL" ? RED : verdict === "PASS" ? GREEN : verdict === "BORDERLINE" ? AMBER : "#8A9098";
  const conf = typeof v.confidence === "number" ? (v.confidence <= 1 ? Math.round(v.confidence * 100) + "%" : v.confidence + "") : "";
  const lensCard = (label, txt) => {
    const body = lensText(txt);
    const inner = body ? mdLite(body) : `<span class="ldim">no material raised on this axis</span>`;
    return `<div class="diag-lens"><div class="ll"><span class="ln">${esc(label)}</span><span class="lm">Sonnet 5</span></div><div class="lt">${inner}</div></div>`;
  };
  const lensRow = reviews
    ? `<div class="diag-lenses">${lensCard("MECHANISM", reviews.mechanism)}${lensCard("PRECEDENT", reviews.precedent)}${lensCard("ADVERSARY", reviews.adversary)}</div>`
    : `<div class="diag-fallback">Claude agents are not configured on this instance, so this shows the deterministic rule verdict. The full multi-agent path (3 Sonnet lenses + Opus adjudicator) runs when the API key is present.</div>`;
  const arch = out.agents !== false
    ? `<span class="diag-arch-mini">4 agents · 3 Sonnet-5 lenses in parallel &rarr; Opus-4.8 adjudicator${out.ms ? " · " + (out.ms / 1000).toFixed(1) + "s" : ""}</span>`
    : `<span class="diag-arch-mini">deterministic fallback · agents off</span>`;
  host.innerHTML =
    `<div class="diag-panel">
    <div class="diag-hd"><span class="cap">CLAUDE VERIFIER · first-party Anthropic API</span>${arch}</div>
    ${lensRow}
    <div class="diag-verdict" style="border-left-color:${vcol}">
      <div class="dv-top"><span class="dv-badge" style="color:${vcol};border-color:${vcol}">${esc(verdict)}</span><span class="dv-model">ADJUDICATOR · Opus 4.8${conf ? " · self-rated confidence " + conf : ""}</span></div>
      <div class="dv-reason">${mdLite(v.reasoning || (refusedSynth ? "The adjudicator declined under the safety classifier; rely on the deterministic gate verdict above." : ""))}</div>
      ${v.recommendation ? `<div class="dv-rec"><span>recommendation</span> ${mdLite(v.recommendation)}</div>` : ""}
    </div>
  </div>`;
}

/* ---------------- live Claude closed-loop optimizer (real /rescue: Claude iterates grounded edits, gate re-scores) ---------------- */
function _fmtGap(g) { return (g >= 0 ? "+" : "−") + Math.abs(g).toFixed(2); }

function renderRescue(host, out) {
  const hist = out.history || [];
  const passed = out.passed;
  const vcol = passed ? GREEN : RED;
  const steps = hist.map((h, i) => {
    const prev = i > 0 ? hist[i - 1].gap : -99;
    const c = h.passed ? GREEN : (h.gap > prev ? AMBER : RED);
    const lbl = h.round === 0 ? "start" : "round " + h.round;
    return `<div class="rx-step"><div class="rx-g" style="color:${c}">${_fmtGap(h.gap)}</div><div class="rx-l">${esc(lbl)}</div><div class="rx-c">${esc(h.most_active)}</div></div>`;
  }).join('<span class="rx-arrow">→</span>');
  const verdict = passed
    ? `RESCUED to ${_fmtGap(out.final_gap)} in ${out.rounds} round${out.rounds === 1 ? "" : "s"}`
    : `not rescued in ${out.rounds} rounds (gap ${_fmtGap(out.final_gap)})`;
  host.innerHTML =
    `<div class="rescue-panel">
    <div class="rx-hd"><span class="cap">CLAUDE CLOSED-LOOP OPTIMIZER · Opus 4.8 iterating, the frozen gate as a tool${out.ms ? " · " + Math.round(out.ms / 1000) + "s" : ""}</span></div>
    <div class="rx-flow">${steps || '<span class="rx-c">no rounds</span>'}</div>
    <div class="rx-verdict" style="border-left-color:${vcol};color:${vcol}">${verdict}</div>
    <div class="rx-note">Claude proposed grounded JASPAR motif edits and re-scored with the frozen gate after each round, iterating a design the gate can only score. In-silico consistency, not wet-lab. At an equal 4-round budget on 97 failing designs, its adaptive search rescues 27% versus a fixed greedy rule's 25% (within noise, CI includes zero); the value shown here is the live tool-using loop itself, not a rescue-rate lift.</div>
  </div>`;
}

async function runRescue(item) {
  const host = $("#ins-rescue-out"), btn = $("#ins-rescue");
  if (!host) return;
  const cached = rescueCache.get(item.id);
  if (cached) { renderRescue(host, cached); host.scrollIntoView({ behavior: "smooth", block: "nearest" }); return; }
  if (btn) { btn.disabled = true; btn.classList.add("busy"); }
  host.innerHTML = `<div class="rescue-panel loading"><div class="rx-hd"><span class="cap">CLAUDE CLOSED-LOOP OPTIMIZER · first-party Anthropic API</span><span class="diag-live"><span class="ld"></span>iterating</span></div><div class="rx-note">Claude is proposing grounded motif edits and re-scoring with the frozen gate each round. Up to 3 rounds, ~30 to 40s.</div></div>`;
  host.scrollIntoView({ behavior: "smooth", block: "nearest" });
  try {
    const out = await api("/rescue", { sequence: item.seq, target_cell: item.target });
    rescueCache.set(item.id, out);
    renderRescue(host, out);
  } catch (e) {
    host.innerHTML = `<div class="rescue-panel"><div class="diag-err">Claude rescue could not run: ${esc(e.message)}. The deterministic fix and the gate verdict above still stand.</div></div>`;
  } finally {
    if (btn) { btn.disabled = false; btn.classList.remove("busy"); }
  }
}

async function runDiagnosis(item) {
  const host = $("#ins-diagnosis"), btn = $("#ins-diagnose");
  if (!host) return;
  const cached = diagCache.get(item.id);
  if (cached) { renderDiagnosis(host, cached); host.scrollIntoView({ behavior: "smooth", block: "nearest" }); return; }
  if (btn) { btn.disabled = true; btn.classList.add("busy"); }
  host.innerHTML = diagLoadingHTML();
  host.scrollIntoView({ behavior: "smooth", block: "nearest" });
  try {
    const out = await api("/diagnose", { sequence: item.seq, target_cell: item.target });
    diagCache.set(item.id, out);
    renderDiagnosis(host, out);
  } catch (e) {
    host.innerHTML = `<div class="diag-panel"><div class="diag-err">Claude diagnosis could not run: ${esc(e.message)}. The deterministic gate verdict above still stands.</div></div>`;
  } finally {
    if (btn) { btn.disabled = false; btn.classList.remove("busy"); }
  }
}


async function applyFix(item) {
  const fixBtn = $("#ins-fix");
  if (fixBtn) fixBtn.disabled = true;
  const scan = $("#insp-scan"); if (scan) scan.style.opacity = "1";
  const hep = $("#ins-hep"), off = $("#ins-off");
  // RE-SCORE flash
  [hep, off].forEach((el) => { if (el) { el.style.background = CYAN; el.style.opacity = "0.2"; el.style.boxShadow = "0 0 22px " + GLOW.CYAN; } });
  $("#ins-pn").textContent = "RE-SCORE"; $("#ins-pn").style.color = CYAN;
  $("#ins-statusbar").style.borderLeftColor = CYAN;
  $("#ins-st").textContent = "Applying the prescribed motif edit and re-scoring with the same frozen external model…";

  try {
    const rd = await api("/redesign", { sequence: item.seq, target_cell: item.target });
    // re-score the REAL edited sequence to get the honest after-profile for the bars
    let after = null, scan2 = null;
    if (rd.edited_sequence) {
      [after, scan2] = await Promise.all([
        api("/predict", { sequence: rd.edited_sequence, target_cell: item.target }).catch(() => null),
        api("/motifs", { sequence: rd.edited_sequence, target_cell: item.target }).catch(() => null),
      ]);
    }
    const passed = rd.after && !rd.after.predicted_fail;
    const col = passed ? GREEN : (rd.after && rd.after.predicted_specificity_gap >= 0 ? GREEN : RED);
    const glow = passed ? GLOW.GREEN : GLOW.RED;
    const gap = rd.after ? rd.after.predicted_specificity_gap : (item.gap + (rd.gap_delta || 0));
    const winner = rd.after ? rd.after.predicted_most_active_cell : item.target;

    let hepH = "80%", offH = "46%";
    if (after && after.predicted_profile_log2fc) {
      const b = barHeights({ predicted_profile_log2fc: after.predicted_profile_log2fc, target_cell: item.target, predicted_most_active_cell: item.cell });
      hepH = b.hep; offH = b.off;
    }

    setTimeout(() => {
      if (hep) { hep.style.background = col; hep.style.opacity = "1"; hep.style.height = hepH; hep.style.boxShadow = "0 0 22px " + glow; }
      if (off) { off.style.background = col; off.style.opacity = "1"; off.style.height = offH; off.style.boxShadow = "0 0 22px " + glow; }
      const setC = (id, prop, val) => { const e = $("#" + id); if (e) e.style[prop] = val; };
      $("#ins-winner").textContent = winner; setC("ins-winner", "color", col);
      $("#ins-gap").textContent = fmtGap(gap); setC("ins-gap", "color", col);
      setC("ins-needle", "left", gapPos(gap)); setC("ins-needle", "background", col); setC("ins-needle", "boxShadow", "0 0 10px " + col);
      $("#ins-pn").textContent = passed ? "FIXED" : "IMPROVED"; setC("ins-pn", "color", col);
      $("#ins-statusbar").style.borderLeftColor = col;
      const nDis = (rd.edits || []).filter((e) => e.action === "disrupt").length;
      const nAdd = (rd.edits || []).filter((e) => e.action === "add").length;
      $("#ins-st").innerHTML = `Fixed and re-scored on the same frozen model after ${nDis} off-target disruptions and ${nAdd} target-motif insertions. Most-active cell is now <b style="color:${col}">${esc(winner)}</b>, specificity gap ${fmtGap(gap)}. ${passed ? "Cleared for synthesis." : "Gap moved " + fmtGap(rd.gap_delta || 0) + "; still flagged."}`;

      const stamp = $("#insp-stamp");
      if (passed) { stamp.textContent = "CLEARED"; stamp.style.color = GREEN; stamp.style.background = "rgba(53,212,138,.1)"; stamp.style.borderColor = "rgba(53,212,138,.55)"; }

      // edit chips
      const chips = (rd.edits || []).slice(0, 14).map((e) =>
        `<span class="echip ${e.action === "add" ? "add" : "disrupt"}">${e.action === "add" ? "＋" : "✕"} ${esc(e.tf)}</span>`).join("");
      const hint = $("#ins-hint");
      if (hint) hint.outerHTML = `<div class="edit-chips" style="flex-basis:100%">${chips}</div>`;
      if (passed) { const fb = $("#ins-fix"); if (fb) fb.hidden = true; const bc = $("#ins-clear"); if (bc) bc.hidden = false; }
      // re-render the detail panels for the EDITED design so the whole instrument stays consistent after the flip
      if (passed && rd.edited_sequence) {
        const es = rd.edited_sequence;
        if (after && after.predicted_profile_log2fc) { const pf = $("#ins-profile"); if (pf) pf.innerHTML = profileHTML(after); }
        const cap = $("#ins-seqcap"); if (cap) cap.textContent = "DESIGNED ENHANCER · " + es.length + " bp";
        const rl = $("#ins-ruler"); if (rl) rl.innerHTML = "<span>0</span><span>" + Math.round(es.length / 4) + "</span><span>" + Math.round(es.length / 2) + "</span><span>" + Math.round(3 * es.length / 4) + "</span><span>" + es.length + "</span>";
        if (scan2) {
          const hits2 = collectHits(scan2), map2 = seqMapHTML(es, hits2), zoom2 = seqZoomHTML(es, hits2);
          const setH = (id, html) => { const e = $("#" + id); if (e) e.innerHTML = html; };
          setH("ins-seqmap", map2.ticks); setH("ins-seqlabels", map2.labels);
          setH("ins-zbases", zoom2.bases); setH("ins-zbracket", zoom2.bracket);
          const zl = $("#ins-zlbl"); if (zl) zl.textContent = zoom2.zlbl;
          if (scan2.by_cell) {
            const d = scan2.by_cell[item.target], tfs = d && d.tfs ? Object.keys(d.tfs) : [];
            const ms = $("#ins-motifset"); if (ms) { ms.textContent = tfs.length ? tfs.join(" · ") : esc(item.target) + " grammar installed"; ms.style.color = GREEN; }
          }
        }
      }
      if (scan) scan.style.opacity = "0";
    }, 650);
  } catch (e) {
    if (scan) scan.style.opacity = "0";
    $("#ins-st").textContent = "redesign failed: " + e.message;
    if (fixBtn) fixBtn.disabled = false;
  }
}

/* ---------------- verify: paste your own (real /predict + /motifs) ---------------- */
function validSeq(s) {
  const c = (s || "").replace(/\s+/g, "").toUpperCase().replace(/U/g, "T");
  return /^[ACGTN]+$/.test(c) && c.length >= 50 && c.length <= 5000 ? c : null;
}
$("#vf-own-btn").addEventListener("click", () => {
  const raw = $("#vf-own-seq").value, seq = validSeq(raw);
  const err = $("#vf-own-err");
  if (!seq) { err.textContent = "Need a DNA sequence (ACGT/U, 50–5000 bp)."; return; }
  err.textContent = "";
  $$(".vf-row").forEach((r) => r.classList.remove("sel"));
  selectDesign({ id: "your design", seq, target: $("#vf-own-target").value });
});

/* ---------------- batch view: live triage tool + econ (real /batch) ---------------- */
let _lastBatch = null;

function parseSeqFile(text) {
  const lines = (text || "").split(/\r?\n/);
  const head = (lines[0] || "").toLowerCase();
  if (head.includes(",") && head.includes("seq")) {
    const cols = lines[0].split(",").map((c) => c.trim().toLowerCase());
    const si = cols.findIndex((c) => c === "sequence" || c === "seq");
    const ii = cols.findIndex((c) => c === "id" || c === "name" || c === "design");
    const out = [];
    for (let k = 1; k < lines.length; k++) {
      if (!lines[k].trim()) continue;
      const parts = lines[k].split(",");
      const seq = (parts[si] || "").trim();
      if (seq) out.push({ id: ii >= 0 ? (parts[ii] || "").trim() || `design_${out.length + 1}` : `design_${out.length + 1}`, seq });
    }
    return out;
  }
  const out = []; let cur = null, id = null;
  for (const ln of lines) {
    const t = ln.trim(); if (!t) continue;
    if (t.startsWith(">")) { if (cur !== null) out.push({ id, seq: cur }); id = t.slice(1).trim() || `design_${out.length + 1}`; cur = ""; }
    else if (cur !== null) cur += t;
    else out.push({ id: `design_${out.length + 1}`, seq: t });
  }
  if (cur !== null) out.push({ id, seq: cur });
  return out;
}

async function scoreChunked(items, target_cell, R) {
  const CHUNK = 64, rows = [];
  for (let i = 0; i < items.length; i += CHUNK) {
    const chunk = items.slice(i, i + CHUNK);
    R.innerHTML = `<div class="empty"><span class="spin" style="border-top-color:#38C6D6"></span><div style="margin-top:10px">scoring ${Math.min(i + CHUNK, items.length)} / ${items.length} designs…</div></div>`;
    const d = await api("/batch", { sequences: chunk.map((x) => x.seq), target_cell });
    for (const r of d.ranking) {
      const it = chunk[r.input_index];
      if (it) rows.push({ id: it.id, seq: it.seq, gap: r.predicted_gap, cell: r.predicted_most_active_cell, fail: r.predicted_fail, low: r.low_activity, lowc: r.low_complexity });
    }
  }
  rows.sort((a, b) => b.gap - a.gap);
  rows.forEach((r, i) => (r.rank = i + 1));
  return rows;
}

function renderBatchResult(rows, R) {
  const n = rows.length, nfail = rows.filter((r) => r.fail).length;
  const half = rows.slice(0, Math.max(1, Math.floor(n / 2)));
  const overall = n ? nfail / n : 0;
  const nlow = rows.filter((r) => r.low).length;
  const nlowc = rows.filter((r) => r.lowc).length;
  // NOT a measured reduction. rows are sorted by pred_gap and r.fail IS pred_gap <= 0, so every
  // predicted failure lands in the riskiest half by construction whenever fewer than half the
  // batch is flagged; the old "% fewer failures" tile therefore read 100% by arithmetic, not by
  // measurement, and a user's own library carries no wet-lab labels to measure against.
  // Report the batch's own predicted-failure rate against the benchmark base rate instead, and
  // put the MEASURED reduction (from the cross-lab benchmark) in the fine print where it belongs.
  const flaggedInRiskiestHalf = nfail - half.filter((r) => r.fail).length;
  let h = `<div class="big-stat">
    <div class="s"><div class="v">${(overall * 100).toFixed(1)}%</div><div class="l">of this batch is <b>predicted</b> to fail, against a 6.29% base rate on the cross-lab benchmark</div></div>
    <div class="s"><div class="v">${nfail}/${n}</div><div class="l">predicted to miss their target cell</div></div>
  </div><div class="dim" style="font-size:11px;margin-top:6px">${flaggedInRiskiestHalf} of ${nfail} predicted failures sort into the riskiest half here, which is by construction rather than a measured result: the ranking and the pass/fail call both come from the same predicted gap, and your library carries no wet-lab labels to score against. The <i>measured</i> safest-half reduction, on the 93,435-design cross-lab benchmark, is <b>41%</b> conditioned within (cell &times; generator) and 70% pooled, where a sequence-free stratum-prior rule reaches 91%.</div><table><thead><tr><th>rank</th><th>design</th><th>gap</th><th>most-active</th><th>call</th></tr></thead><tbody>`;
  h += rows.slice(0, 200).map((r) => `<tr><td>${r.rank}</td><td>${esc(r.id)}${r.lowc ? ` <span class="dim" style="font-size:10px">· degenerate</span>` : (r.low ? ` <span class="dim" style="font-size:10px">· weak</span>` : "")}</td><td>${r.gap >= 0 ? "+" : "−"}${Math.abs(r.gap).toFixed(2)}</td><td>${esc(r.cell)}</td><td><span class="tpill ${r.fail ? "FAIL" : "PASS"}">${r.fail ? "fail" : "pass"}</span></td></tr>`).join("");
  h += `</tbody></table><div class="dim" style="font-size:11px;margin-top:8px">ranked safest-first by predicted specificity gap. Synthesize from the top.${nlowc > 0 ? ` ${nlowc} of ${n} are degenerate or repetitive (marked <i>degenerate</i>): homopolymers or tandem repeats, not enhancer-like, so their specificity call is not meaningful.` : ""}${nlow > 0 ? ` ${nlow} of ${n} predicted weakly active in all cells (marked <i>weak</i>): not enhancer-like, so their specificity call is low-confidence.` : ""}${n > 200 ? ` Showing 200 of ${n}; download the full ranked CSV.` : ""}</div>`;
  h += `<div class="econ">
    <div class="hd">What triaging this batch is worth</div>
    <label style="font-size:13px" class="dim">Your cost per design (synthesis + assay): $<input id="econcost" type="number" min="0" step="50" value="500"></label>
    <div id="econ-out" style="margin-top:10px"></div>
  </div>`;
  R.innerHTML = h;
  const ci = $("#econcost", R);
  if (ci) ci.addEventListener("input", () => renderEcon(rows));
  renderEcon(rows);
}

function renderEcon(rows) {
  const out = $("#econ-out");
  if (!out) return;
  const cost = Math.max(0, parseFloat($("#econcost")?.value) || 0);
  const n = rows.length, nfail = rows.filter((r) => r.fail).length;
  const halfN = Math.max(1, Math.floor(n / 2));
  const halfFail = rows.slice(0, halfN).filter((r) => r.fail).length;
  const randHalfFail = n ? (nfail / n) * halfN : 0;
  const avoided = Math.max(0, randHalfFail - halfFail);
  const money = (x) => "$" + Math.round(x).toLocaleString();
  if (avoided < 0.5) {
    out.innerHTML = `<div class="dim" style="font-size:12px">CisFalcon flags ${nfail}/${n} here. At ${money(cost)}/design, making all ${n} is ${money(n * cost)}. Too few flagged failures on this batch for triage to change the spend much; the value concentrates on failure-prone libraries.</div>`;
    return;
  }
  // `avoided` counts PREDICTED failures, from the same score that did the ranking, so it is an
  // upper bound that assumes every prediction is correct. It is not a measured saving. Scale it
  // by the benchmark's measured precision for the realistic figure, and label both.
  // Precision of the call actually being discounted. `avoided` counts the model's own FAIL
  // calls (pred_gap <= 0) displaced out of the safest half, so the right multiplier is that
  // flag's precision, measured 0.1982 on the cross-lab benchmark (flags 19.2% of designs at
  // recall 0.606). It is NOT 0.24: that belongs to the top 13.2% by risk, which is the
  // recall-0.5 threshold and a different operation. Using it here overstated the figure ~1.2x.
  // Reproduce: PPV of (pred_gap <= 0) over data/gosai_designed/designed_scored.csv.
  const PPV = 0.198;
  out.innerHTML = `<div class="big-stat">
    <div class="s"><div class="v">${money(n * cost)}</div><div class="l">to synthesize all ${n} designs</div></div>
    <div class="s"><div class="v">${money(avoided * cost * PPV)}</div><div class="l">expected averted spend at the measured precision of the fail call itself (PPV 0.198)</div></div>
  </div><div class="dim" style="font-size:11px;margin-top:6px">You enter the cost; CisFalcon supplies the ranking. About <b>${avoided.toFixed(1)}</b> <i>predicted</i> failures move out of the safest half, worth ${money(avoided * cost)} <i>if every prediction were correct</i>, which is an upper bound rather than a measured saving: these are the model's own calls on an unlabelled library, produced by the same score that ranked it. The figure above discounts that by the precision of the same fail call, 0.198 measured across the cross-lab benchmark. That precision is POOLED over all cell types and generators, so like the pooled triage figures it is an optimistic basis for a single lab running one generator against one target cell. Actual averted spend depends on how well it transfers to your library.</div>`;
}

$("#bt-upload").addEventListener("click", () => $("#bt-file").click());
$("#bt-file").addEventListener("change", async (e) => {
  const f = e.target.files[0]; if (!f) return;
  const items = parseSeqFile(await f.text());
  $("#bt-seq").value = items.slice(0, 500).map((x) => `>${x.id}\n${x.seq}`).join("\n");
  $("#bt-err").innerHTML = `<div class="dim" style="font-size:12px">loaded ${items.length} designs from ${esc(f.name)}. Pick the target cell and rank.</div>`;
  e.target.value = "";
});
$("#bt-example").addEventListener("click", async () => {
  try {
    const ex = await api("/example-batch");
    $("#bt-seq").value = (ex.sequences || []).map((s, i) => `>design_${i + 1}\n${s}`).join("\n");
    $("#bt-target").value = ex.target_cell || "HepG2";
  } catch (e) { $("#bt-err").innerHTML = `<div class="err">${esc(e.message)}</div>`; }
});
$("#bt-rank").addEventListener("click", async () => {
  const target_cell = $("#bt-target").value;
  const items = parseSeqFile($("#bt-seq").value).map((x) => ({ id: x.id, seq: validSeq(x.seq) })).filter((x) => x.seq);
  const R = $("#bt-result");
  $("#bt-err").innerHTML = ""; $("#bt-download").style.display = "none";
  if (!items.length) { $("#bt-err").innerHTML = `<div class="err">No valid DNA sequences (need 50-5000 bp each).</div>`; return; }
  try {
    const rows = await scoreChunked(items, target_cell, R);
    _lastBatch = { rows, target: target_cell };
    renderBatchResult(rows, R);
    $("#bt-download").style.display = "";
  } catch (e) { $("#bt-err").innerHTML = `<div class="err">${esc(e.message)}</div>`; R.innerHTML = `<div class="empty">Ranking failed.</div>`; }
});
$("#bt-download").addEventListener("click", () => {
  if (!_lastBatch) return;
  const csv = "rank,design_id,predicted_gap,predicted_most_active_cell,call,sequence\n" +
    _lastBatch.rows.map((r) => `${r.rank},${JSON.stringify(r.id)},${r.gap},${r.cell},${r.fail ? "fail" : "pass"},${r.seq}`).join("\n");
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([csv], { type: "text/csv" }));
  a.download = `cisfalcon_ranked_${_lastBatch.target}.csv`;
  a.click();
  URL.revokeObjectURL(a.href);
});

/* ---------------- init ---------------- */
function populateSelects(cells) {
  ["vf-own-target", "bt-target"].forEach((id) => {
    const sel = $("#" + id); if (!sel) return;
    sel.innerHTML = "";
    cells.forEach((c) => sel.add(new Option(c, c)));
    if (cells.includes("HepG2")) sel.value = "HepG2";
  });
}

async function init() {
  ovStart(); // overview animation runs regardless of API
  populateSelects(TARGET_CELLS_FALLBACK); // usable shape offline; refreshed from META below
  try {
    META = await api("/meta");
    if (META && Array.isArray(META.target_cells) && META.target_cells.length) populateSelects(META.target_cells);
  } catch (e) {
    /* backend not reachable. Nav, overview animation, and static views still work. */
    console.warn("meta unavailable:", e.message);
  }
}
init();
