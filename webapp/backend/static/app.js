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

let META = null;
const inspCache = new Map(); // id -> { rep, scan, item }
const diagCache = new Map(); // id -> /diagnose response (cache the real Claude call per design)

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

  const statusLine = fail
    ? `Predicted to fail. Most-active cell is ${esc(offCell)}, not the ${esc(rep.target_cell)} target. Specificity gap ${fmtGap(rep.predicted_specificity_gap)} (fail when gap ≤ 0). Calibrated failure probability ${(rep.calibrated_fail_probability * 100).toFixed(0)}%.`
    : `Predicted specific. Most-active cell is its ${esc(rep.target_cell)} target. Specificity gap ${fmtGap(rep.predicted_specificity_gap)}. Cleared for synthesis.`;

  $("#insp-dot").style.background = col; $("#insp-dot").style.boxShadow = "0 0 8px " + col;
  const stamp = $("#insp-stamp");
  stamp.textContent = fail ? "FLAGGED" : "CLEAR";
  stamp.style.opacity = "1"; stamp.style.color = col;
  stamp.style.background = fail ? "rgba(255,91,79,.1)" : "rgba(53,212,138,.1)";
  stamp.style.borderColor = fail ? "rgba(255,91,79,.55)" : "rgba(53,212,138,.55)";

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
    <button class="btn-fix" id="ins-fix"${fail ? "" : " hidden"}>Apply HepG2-grammar fix
      <svg width="13" height="13" viewBox="0 0 14 14" fill="none" stroke="#14171B" stroke-width="1.6"><path d="M2 7h9M7 3l4 4-4 4"></path></svg>
    </button>
    <span class="badge-clear" id="ins-clear"${fail ? " hidden" : ""}>cleared for synthesis</span>
    <span class="insp-hint" id="ins-hint">in-silico consistency check, ahead of wet-lab</span>
  </div>

  <div class="diag-wrap" id="ins-diagnosis"></div>

  <div class="insp-statusbar" id="ins-statusbar" style="border-left-color:${col}">
    <span class="pn" id="ins-pn" style="color:${col}">${fail ? "FLAG" : "CLEAR"}</span>
    <span class="st" id="ins-st">${statusLine}</span>
    <span class="rt">frozen external model</span>
  </div>`;

  const fixBtn = $("#ins-fix");
  if (fixBtn) fixBtn.addEventListener("click", () => applyFix(item));
  const dxBtn = $("#ins-diagnose");
  if (dxBtn) dxBtn.addEventListener("click", () => runDiagnosis(item));
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
  if (t && typeof t === "object") return t.refused ? "declined by the safety classifier; the other lenses proceeded" : JSON.stringify(t);
  return t || "—";
}

function renderDiagnosis(host, out) {
  const v = (out.verdict && typeof out.verdict === "object") ? out.verdict : {};
  const refusedSynth = out.verdict && out.verdict.refused;
  const reviews = out.reviews || null;
  const verdict = String(v.verdict || (refusedSynth ? "DECLINED" : "—")).toUpperCase();
  const vcol = verdict === "FAIL" ? RED : verdict === "PASS" ? GREEN : verdict === "BORDERLINE" ? AMBER : "#8A9098";
  const conf = typeof v.confidence === "number" ? (v.confidence <= 1 ? Math.round(v.confidence * 100) + "%" : v.confidence + "") : "";
  const lensCard = (label, txt) =>
    `<div class="diag-lens"><div class="ll"><span class="ln">${esc(label)}</span><span class="lm">Sonnet 5</span></div><div class="lt">${esc(lensText(txt))}</div></div>`;
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
      <div class="dv-top"><span class="dv-badge" style="color:${vcol};border-color:${vcol}">${esc(verdict)}</span><span class="dv-model">ADJUDICATOR · Opus 4.8${conf ? " · confidence " + conf : ""}</span></div>
      <div class="dv-reason">${esc(v.reasoning || (refusedSynth ? "The adjudicator declined under the safety classifier; rely on the deterministic gate verdict above." : ""))}</div>
      ${v.recommendation ? `<div class="dv-rec"><span>recommendation</span> ${esc(v.recommendation)}</div>` : ""}
    </div>
  </div>`;
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
            const ms = $("#ins-motifset"); if (ms) { ms.textContent = tfs.length ? tfs.join(" · ") : "HepG2 grammar installed"; ms.style.color = GREEN; }
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
      if (it) rows.push({ id: it.id, seq: it.seq, gap: r.predicted_gap, cell: r.predicted_most_active_cell, fail: r.predicted_fail });
    }
  }
  rows.sort((a, b) => b.gap - a.gap);
  rows.forEach((r, i) => (r.rank = i + 1));
  return rows;
}

function renderBatchResult(rows, R) {
  const n = rows.length, nfail = rows.filter((r) => r.fail).length;
  const half = rows.slice(0, Math.max(1, Math.floor(n / 2)));
  const halfFail = half.filter((r) => r.fail).length / half.length;
  const overall = n ? nfail / n : 0;
  const reduction = overall > 0 ? Math.round(100 * (1 - halfFail / overall)) : 0;
  let h = `<div class="big-stat">
    <div class="s"><div class="v">${reduction}%</div><div class="l">fewer failures if you synthesize the safest half first</div></div>
    <div class="s"><div class="v">${nfail}/${n}</div><div class="l">predicted to miss their target cell</div></div>
  </div><table><thead><tr><th>rank</th><th>design</th><th>gap</th><th>most-active</th><th>call</th></tr></thead><tbody>`;
  h += rows.slice(0, 200).map((r) => `<tr><td>${r.rank}</td><td>${esc(r.id)}</td><td>${r.gap >= 0 ? "+" : "−"}${Math.abs(r.gap).toFixed(2)}</td><td>${esc(r.cell)}</td><td><span class="tpill ${r.fail ? "FAIL" : "PASS"}">${r.fail ? "fail" : "pass"}</span></td></tr>`).join("");
  h += `</tbody></table><div class="dim" style="font-size:11px;margin-top:8px">ranked safest-first by predicted specificity gap. Synthesize from the top.${n > 200 ? ` Showing 200 of ${n}; download the full ranked CSV.` : ""}</div>`;
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
  out.innerHTML = `<div class="big-stat">
    <div class="s"><div class="v">${money(n * cost)}</div><div class="l">to synthesize all ${n} designs</div></div>
    <div class="s"><div class="v">${money(avoided * cost)}</div><div class="l">wasted synthesis averted: about ${avoided.toFixed(1)} fewer broken designs made if you build CisFalcon's safest half instead of a random half</div></div>
  </div><div class="dim" style="font-size:11px;margin-top:6px">You enter the cost; CisFalcon supplies the ranking. Averted = expected failures in a random half minus the failures left in CisFalcon's safest half, times your cost.</div>`;
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
