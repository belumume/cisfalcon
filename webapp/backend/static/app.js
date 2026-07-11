const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const api = (p, body) =>
  fetch("/api" + p, body ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) } : undefined)
    .then(async (r) => { const j = await r.json().catch(() => ({})); if (!r.ok) throw new Error(j.detail || r.statusText); return j; });

const CELL_LABEL = {
  NT2_D1: "NT2-D1 (embryonal carcinoma)", GM12878: "GM12878 (lymphoblastoid)", "786_O": "786-O (renal)",
  SKNSH: "SK-N-SH (neuroblastoma)", WERI_Rb1: "WERI-Rb1 (retinoblastoma)", SJCRH30: "SJCRH30 (rhabdomyosarcoma)",
  HepG2: "HepG2 (hepatocyte)", K562: "K562 (erythroleukemia)", MCF7: "MCF7 (breast)", HeLaS3: "HeLa-S3 (cervical)",
};
const clabel = (c) => CELL_LABEL[c] || c;

let META = null;

// ---- tabs
$$(".tab").forEach((t) =>
  t.addEventListener("click", () => {
    $$(".tab").forEach((x) => x.classList.toggle("on", x === t));
    ["check", "triage", "screen", "how"].forEach((n) => ($("#tab-" + n).hidden = n !== t.dataset.tab));
  })
);

// ---- init
async function init() {
  META = await api("/meta");
  const sel = $("#target"), bsel = $("#btarget");
  META.target_cells.forEach((c) => {
    const o = new Option(clabel(c), c); sel.add(o.cloneNode(true)); bsel.add(o);
  });
  sel.value = "HepG2"; bsel.value = "HepG2";
  if (META.screenaudit) renderScreenAudit(META.screenaudit);
}
init();

$("#seq").addEventListener("input", (e) => {
  const n = e.target.value.replace(/\s|>.*$/gm, "").length;
  $("#seqlen").textContent = n + " bp";
});

$("#loadex").addEventListener("click", async () => {
  const ex = await api("/example");
  $("#seq").value = ex.sequence || "";
  $("#seq").dispatchEvent(new Event("input"));
  $("#target").value = ex.target_cell;
  $("#result").innerHTML = `<div class="note">Loaded a real BODA/Malinois design optimized for <b>HepG2</b> specificity. Measured in the wet lab: HepG2 log2FC −0.1, K562 log2FC +6.5 (about 90x on a linear scale) — it barely touches its target and fires strongly in the wrong cell. Run a check and watch CisFalcon call it from sequence alone.</div>`;
});

$("#loadbrain")?.addEventListener("click", async () => {
  const ex = await api("/example-brain");
  $("#seq").value = ex.sequence || "";
  $("#seq").dispatchEvent(new Event("input"));
  $("#target").value = ex.target_cell;
  $("#result").innerHTML = `<div class="note">Loaded a real design optimized for the brain-derived <b>SKNSH</b> line (a neuroblastoma cell). Measured in the wet lab: SKNSH log2FC +0.5, K562 log2FC +5.8 — it barely touches its brain target and fires in a blood cell instead. Enhancer specificity like this is the targeting element of brain enhancer-AAV gene therapy. Run a check and watch CisFalcon flag it from sequence alone.</div>`;
});

// ---------- rendering ----------
function verdictWord(r) { return r.predicted_fail ? "LIKELY OFF-TARGET" : r.predicted_specificity_gap < 0.5 ? "UNCERTAIN" : "LIKELY SPECIFIC"; }
function verdictClass(r) { return r.predicted_fail ? "FAIL" : r.predicted_specificity_gap < 0.5 ? "BORDERLINE" : "PASS"; }

function chartHTML(profile, target, winner) {
  const cells = META.target_cells;
  const vals = cells.map((c) => profile[c] ?? 0);
  const lo = Math.min(0, ...vals), hi = Math.max(0.001, ...vals), span = hi - lo;
  const zero = ((0 - lo) / span) * 100;
  return `<div class="chart">` + cells.map((c) => {
    const v = profile[c] ?? 0, w = ((v - lo) / span) * 100;
    const cls = c === target ? "target" : c === winner ? "winner" : "";
    return `<div class="bar-row ${cls}"><div class="cn">${c}</div>
      <div class="bar-track"><div class="zero-line" style="left:${zero}%"></div><div class="bar-fill" style="width:${w}%"></div></div>
      <div class="bv">${v >= 0 ? "+" : ""}${v.toFixed(2)}</div></div>`;
  }).join("") + `</div><div class="dim" style="font-size:11px;margin-top:6px">predicted activity (log2FC) per cell · target in teal · predicted winner in red</div>`;
}

function motifHTML(scan) {
  if (!scan || !scan.by_cell) return "";
  let h = `<div class="hd" style="border-top:1px solid var(--line);margin-top:4px">Grounded motif scan · JASPAR</div><div style="padding:14px 0">`;
  for (const [cell, d] of Object.entries(scan.by_cell)) {
    const isOff = cell === (scan.off_target_cell || scan.predicted_most_active_cell);
    h += `<div class="motif-cell"><div class="mh">${isOff ? "off-target" : "target"} <b>${cell}</b> driver motifs in the sequence: ${d.n_driver_tfs_present ? "" : '<span class="dim">none found</span>'}</div><div class="chips">`;
    for (const [tf, v] of Object.entries(d.tfs)) {
      h += `<span class="chip ${isOff ? "off" : "tgt"}"><b>${tf}</b><span class="ct">${v.n_sites} sites · ${v.matrix_id}</span></span>`;
    }
    if (!d.n_driver_tfs_present) h += `<span class="chip none">no driver sites</span>`;
    h += `</div></div>`;
  }
  return h + `</div>`;
}

function verdictHTML(r) {
  const cls = verdictClass(r), gapc = r.predicted_specificity_gap < 0 ? "neg" : "pos";
  const line = r.predicted_fail
    ? `Predicted most-active in <b style="color:var(--fail)">${clabel(r.predicted_most_active_cell)}</b>, not its ${clabel(r.target_cell)} target.`
    : `Predicted most-active in its <b style="color:var(--pass)">${clabel(r.target_cell)}</b> target.`;
  return `<div class="verdict"><div class="badge ${cls}">${cls}</div><div class="vtext">
    <div class="big">${verdictWord(r)}</div>
    <div class="sub">${line} Specificity gap <span class="gap-num ${gapc}">${r.predicted_specificity_gap >= 0 ? "+" : ""}${r.predicted_specificity_gap}</span> · calibrated failure probability ${(r.calibrated_fail_probability * 100).toFixed(0)}%.</div>
  </div></div>`;
}

async function runCheck() {
  const sequence = $("#seq").value, target_cell = $("#target").value;
  $("#err").innerHTML = "";
  const R = $("#result");
  R.innerHTML = `<div class="empty"><span class="spin" style="border-top-color:var(--brand)"></span><div style="margin-top:12px">scoring against the frozen activity model…</div></div>`;
  try {
    const [rep, scan] = await Promise.all([api("/predict", { sequence, target_cell }), api("/motifs", { sequence, target_cell }).catch(() => null)]);
    let h = verdictHTML(rep) + chartHTML(rep.predicted_profile_log2fc, rep.target_cell, rep.predicted_most_active_cell);
    if (scan) h += motifHTML(scan);
    h += `<div class="btns" style="margin-top:16px"><button class="b ghost" id="r-diag">Full diagnosis (built with Claude)</button>`;
    if (rep.predicted_fail || rep.predicted_specificity_gap < 0.5) h += `<button class="b primary" id="r-fix">Apply the fix &amp; re-score</button>`;
    h += `</div><div id="diag2"></div><div id="loop2"></div>`;
    R.innerHTML = h;
    $("#r-diag")?.addEventListener("click", runDiagnose);
    $("#r-fix")?.addEventListener("click", runRedesign);
  } catch (e) { $("#err").innerHTML = `<div class="err">${e.message}</div>`; R.innerHTML = `<div class="empty">Check failed.</div>`; }
}

async function runDiagnose() {
  const sequence = $("#seq").value, target_cell = $("#target").value;
  const D = $("#diag2");
  D.innerHTML = `<div class="hd" style="border-top:1px solid var(--line);margin-top:8px">Built with Claude · parallel agents</div>
    <div class="agents">
      <div class="agent"><div class="an"><span class="dot run"></span>mechanism</div><div class="atx">reviewing the predicted profile…</div></div>
      <div class="agent"><div class="an"><span class="dot run"></span>precedent</div><div class="atx">grounding in the held-out benchmark…</div></div>
      <div class="agent"><div class="an"><span class="dot run"></span>adversary</div><div class="atx">challenging the call…</div></div>
    </div><div class="dim" style="font-size:12px">a synthesizer adjudicates, and a motif-redesign agent grounded in the JASPAR scan proposes the fix…</div>`;
  try {
    const out = await api("/diagnose", { sequence, target_cell });
    if (out.agents === false) { D.innerHTML = `<div class="note">Agent layer not configured on this instance; showing the deterministic gate verdict. Set ANTHROPIC_API_KEY to enable the parallel-agent diagnosis.</div>`; return; }
    const rev = out.reviews || {};
    let h = `<div class="hd" style="border-top:1px solid var(--line);margin-top:8px">Built with Claude · parallel agents</div><div class="agents">`;
    for (const k of ["mechanism", "precedent", "adversary"]) {
      const t = typeof rev[k] === "string" ? rev[k] : JSON.stringify(rev[k] || "");
      h += `<div class="agent"><div class="an"><span class="dot"></span>${k}</div><div class="atx">${esc(t)}</div></div>`;
    }
    h += `</div>`;
    const v = out.verdict || {};
    if (v.verdict) h += `<div class="verdict" style="margin-top:6px"><div class="badge ${v.verdict}">${v.verdict}</div><div class="vtext"><div class="big">${esc(v.recommendation || "")}</div><div class="sub">${esc(v.reasoning || "")}</div></div></div>`;
    if (out.redesign) {
      const rd = out.redesign;
      h += `<div class="redesign"><div class="rl">motif-level redesign · grounded in the JASPAR scan</div><div class="rr">
        <div class="g"><div class="gl">remove (off-target drivers)</div><div class="chips">${(rd.off_target_drivers || []).map((t) => `<span class="chip off"><b>${esc(t)}</b></span>`).join("")}</div></div>
        <div class="g"><div class="gl">add (target drivers)</div><div class="chips">${(rd.target_drivers_to_add || []).map((t) => `<span class="chip tgt"><b>${esc(t)}</b></span>`).join("")}</div></div>
      </div><div class="fix">${esc(rd.redesign || "")}</div></div>`;
    }
    D.innerHTML = h;
  } catch (e) { D.innerHTML = `<div class="err">${e.message}</div>`; }
}

async function runRedesign() {
  const sequence = $("#seq").value, target_cell = $("#target").value;
  const L = $("#loop2");
  L.innerHTML = `<div class="empty"><span class="spin" style="border-top-color:var(--brand)"></span><div style="margin-top:10px">applying the motif edit and re-scoring with the same gate…</div></div>`;
  try {
    const d = await api("/redesign", { sequence, target_cell });
    const b = d.before, a = d.after;
    const badge = d.fixed ? `<span class="pill PASS">FIXED</span>` : `<span class="pill ${a.predicted_fail ? "FAIL" : "PASS"}">${a.predicted_fail ? "improved" : "now passes"}</span>`;
    L.innerHTML = `<div class="redesign"><div class="rl">closed loop · apply the fix, re-score with the external model ${badge}</div>
      <div class="rr">
        <div class="g"><div class="gl">before</div><div>most-active <b style="color:var(--fail)">${b.predicted_most_active_cell}</b> · gap <span class="gap-num neg">${b.predicted_specificity_gap}</span></div></div>
        <div class="g"><div class="gl">after the motif edit</div><div>most-active <b style="color:${a.predicted_fail ? "var(--warn)" : "var(--pass)"}">${a.predicted_most_active_cell}</b> · gap <span class="gap-num ${a.predicted_specificity_gap < 0 ? "neg" : "pos"}">${a.predicted_specificity_gap >= 0 ? "+" : ""}${a.predicted_specificity_gap}</span></div></div>
      </div>
      <div class="fix">The gate's predicted specificity gap moved <b class="gap-num pos">${d.gap_delta >= 0 ? "+" : ""}${d.gap_delta}</b> after ${d.edits.filter((e) => e.action === "disrupt").length} off-target motif disruptions and ${d.edits.filter((e) => e.action === "add").length} target-motif insertions. The <b>same external model</b> confirms the fix — not a model narrating a score.</div>
      <div class="chips" style="margin-top:10px">${d.edits.slice(0, 12).map((e) => `<span class="chip ${e.action === "add" ? "tgt" : "off"}"><b>${e.action === "add" ? "＋" : "✕"} ${esc(e.tf)}</b></span>`).join("")}</div>
    </div>`;
  } catch (e) { L.innerHTML = `<div class="err">${e.message}</div>`; }
}

$("#btn-check").addEventListener("click", runCheck);
$("#btn-diag").addEventListener("click", async () => { await runCheck(); $("#r-diag")?.click(); });

// ---------- batch (paste OR upload a CSV/FASTA library; chunks large sets; CSV download) ----------
let _lastBatch = null; // { rows:[{rank,id,seq,gap,cell,fail}], target }

function _validSeq(s) {
  const c = (s || "").replace(/\s+/g, "").toUpperCase().replace(/U/g, "T");
  return /^[ACGTN]+$/.test(c) && c.length >= 50 && c.length <= 5000 ? c : null;
}

// parse a pasted/uploaded blob into [{id, seq}]: CSV with id/sequence columns, FASTA, or one-per-line
function _parseSeqFile(text) {
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

// score any number of designs by chunking under the per-request cap, then re-rank globally
async function _scoreChunked(items, target_cell, R) {
  const CHUNK = 64, rows = [];
  for (let i = 0; i < items.length; i += CHUNK) {
    const chunk = items.slice(i, i + CHUNK);
    R.innerHTML = `<div class="empty"><span class="spin" style="border-top-color:var(--brand)"></span><div style="margin-top:10px">scoring ${Math.min(i + CHUNK, items.length)} / ${items.length} designs…</div></div>`;
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

function _renderBatch(rows, R) {
  const n = rows.length, nfail = rows.filter((r) => r.fail).length;
  const half = rows.slice(0, Math.max(1, Math.floor(n / 2)));
  const halfFail = half.filter((r) => r.fail).length / half.length;
  const overall = n ? nfail / n : 0;
  const reduction = overall > 0 ? Math.round(100 * (1 - halfFail / overall)) : 0;
  let h = `<div class="big-stat">
    <div class="s"><div class="v">${reduction}%</div><div class="l">fewer failures if you synthesize the safest half first</div></div>
    <div class="s"><div class="v">${nfail}/${n}</div><div class="l">predicted to miss their target cell</div></div>
  </div><table><thead><tr><th>rank</th><th>design</th><th>gap</th><th>most-active</th><th>call</th></tr></thead><tbody>`;
  h += rows.slice(0, 200).map((r) => `<tr><td>${r.rank}</td><td>${esc(r.id)}</td><td>${r.gap >= 0 ? "+" : ""}${r.gap}</td><td>${r.cell}</td><td><span class="pill ${r.fail ? "FAIL" : "PASS"}">${r.fail ? "fail" : "pass"}</span></td></tr>`).join("");
  h += `</tbody></table><div class="dim" style="font-size:11px;margin-top:8px">ranked safest-first by predicted specificity gap. Synthesize from the top.${n > 200 ? ` Showing 200 of ${n}; download the full ranked CSV.` : ""}</div>`;
  R.innerHTML = h;
}

$("#btn-upload").addEventListener("click", () => $("#batchfile").click());
$("#batchfile").addEventListener("change", async (e) => {
  const f = e.target.files[0]; if (!f) return;
  const items = _parseSeqFile(await f.text());
  $("#batchseq").value = items.slice(0, 500).map((x) => `>${x.id}\n${x.seq}`).join("\n");
  $("#berr").innerHTML = `<div class="dim" style="font-size:12px">loaded ${items.length} designs from ${esc(f.name)}. Pick the target cell and rank.</div>`;
  e.target.value = "";
});

$("#btn-batchex").addEventListener("click", async () => {
  const ex = await api("/example-batch");
  $("#batchseq").value = (ex.sequences || []).map((s, i) => `>design_${i + 1}\n${s}`).join("\n");
  $("#btarget").value = ex.target_cell || "HepG2";
});

$("#btn-batch").addEventListener("click", async () => {
  const target_cell = $("#btarget").value;
  const items = _parseSeqFile($("#batchseq").value).map((x) => ({ id: x.id, seq: _validSeq(x.seq) })).filter((x) => x.seq);
  const R = $("#batchresult");
  $("#berr").innerHTML = ""; $("#btn-download").style.display = "none";
  if (!items.length) { $("#berr").innerHTML = `<div class="err">No valid DNA sequences (need 50-5000 bp each).</div>`; return; }
  try {
    const rows = await _scoreChunked(items, target_cell, R);
    _lastBatch = { rows, target: target_cell };
    _renderBatch(rows, R);
    $("#btn-download").style.display = "";
  } catch (e) { $("#berr").innerHTML = `<div class="err">${e.message}</div>`; R.innerHTML = `<div class="empty">Ranking failed.</div>`; }
});

$("#btn-download").addEventListener("click", () => {
  if (!_lastBatch) return;
  const csv = "rank,design_id,predicted_gap,predicted_most_active_cell,call,sequence\n" +
    _lastBatch.rows.map((r) => `${r.rank},${JSON.stringify(r.id)},${r.gap},${r.cell},${r.fail ? "fail" : "pass"},${r.seq}`).join("\n");
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([csv], { type: "text/csv" }));
  a.download = `cisfalcon_ranked_${_lastBatch.target}.csv`;
  a.click();
  URL.revokeObjectURL(a.href);
});

// ---------- screenaudit ----------
function renderScreenAudit(sa) {
  const mean = (sa.reduce((s, g) => s + (g.jaccard_raw || 0), 0) / sa.length).toFixed(2);
  $("#sa-mean").textContent = mean;
  $("#sa-grid").innerHTML = sa.map((g) => {
    const j = g.jaccard_raw, col = j > 0.5 ? "var(--pass)" : j > 0.3 ? "var(--warn)" : "var(--fail)";
    return `<div class="sa-card"><div class="cl">${g.cell_line}</div><div class="jv" style="color:${col}">${j.toFixed(2)}</div><div class="jl">hit-list Jaccard · ${g.n_screens} screens</div></div>`;
  }).join("");
}

function esc(s) { return String(s == null ? "" : s).replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c])); }
