/* Does the browser give the same answer as the Python gate?
 *
 * The weights were converted to float16, so the two paths are not bit-identical and a claim
 * that they agree has to be measured rather than assumed. This script serves webdemo/ over
 * HTTP, runs headless Chromium against it, and compares every number the page shows for a
 * fixed set of designs against the reference the Python gate produced for the same designs
 * (reference built by tools/build_parity_reference.py, committed as parity_reference.json).
 *
 *   node parity.test.mjs [path/to/parity_reference.json]
 *
 * It fails loudly if a verdict, a most-active cell, a flag or a motif call differs, or if any
 * predicted log2FC drifts more than TOL. Exit code 0 means the page you are about to publish
 * reproduces the published pipeline.
 */
import { createServer } from "node:http";
import { readFile } from "node:fs/promises";
import { extname, join, normalize } from "node:path";
import { chromium } from "playwright";

const ROOT = new URL(".", import.meta.url).pathname;
const REF = process.argv[2] || join(ROOT, "parity_reference.json");
const TOL = 0.02; // log2FC units; float16 weights, so exact equality is not the standard
const PORT = 8731;

const TYPES = { ".html": "text/html", ".js": "text/javascript", ".mjs": "text/javascript",
  ".css": "text/css", ".json": "application/json", ".bin": "application/octet-stream" };

const server = createServer(async (req, res) => {
  const p = normalize(decodeURIComponent(req.url.split("?")[0])).replace(/^(\.\.[/\\])+/, "");
  const file = join(ROOT, p === "/" ? "index.html" : p);
  try {
    const body = await readFile(file);
    res.writeHead(200, { "Content-Type": TYPES[extname(file)] || "application/octet-stream" });
    res.end(body);
  } catch {
    res.writeHead(404).end("not found");
  }
});

const fail = [];
const check = (name, cond, detail) => { if (!cond) fail.push(`${name}: ${detail}`); };

await new Promise((r) => server.listen(PORT, r));
const ref = JSON.parse(await readFile(REF, "utf8"));
const browser = await chromium.launch();
const page = await browser.newPage();
page.on("pageerror", (e) => fail.push("page error: " + e.message));
await page.goto(`http://127.0.0.1:${PORT}/`);
await page.waitForFunction(() => window.CF && window.CF.api, null, { timeout: 60000 });
const t0 = Date.now();
await page.evaluate(() => window.CF.ready.then(() => window.CF.loadModels()).then(() => true));
const loadMs = Date.now() - t0;
const backend = await page.evaluate(() => tf.getBackend());
console.log(`models loaded in ${(loadMs / 1000).toFixed(1)}s on the ${backend} backend`);

let worst = 0, worstWhere = "";
for (const c of ref) {
  const got = await page.evaluate(async ([seq, cell]) => {
    const t = performance.now();
    const r = await window.CF.api("/predict", { sequence: seq, target_cell: cell });
    const m = await window.CF.api("/motifs", { sequence: seq, target_cell: cell });
    return { r, m, ms: Math.round(performance.now() - t) };
  }, [c.sequence, c.target_cell]);

  const w = c.report, g = got.r;
  check(c.name, g.predicted_most_active_cell === w.predicted_most_active_cell,
    `most-active cell ${g.predicted_most_active_cell} vs ${w.predicted_most_active_cell}`);
  check(c.name, g.predicted_fail === w.predicted_fail, `predicted_fail ${g.predicted_fail} vs ${w.predicted_fail}`);
  check(c.name, g.low_activity === w.low_activity, `low_activity ${g.low_activity} vs ${w.low_activity}`);
  check(c.name, g.low_complexity === w.low_complexity, `low_complexity ${g.low_complexity} vs ${w.low_complexity}`);
  check(c.name, g.complexity === w.complexity, `complexity ${g.complexity} vs ${w.complexity}`);
  check(c.name, g.rule_verdict.verdict === c.rule_verdict.verdict,
    `verdict ${g.rule_verdict.verdict} vs ${c.rule_verdict.verdict}`);
  // The recommendation for a weak or degenerate design quotes the peak activity or the
  // complexity back to the reader, so its text carries a number that is allowed to drift by TOL.
  // Compare the wording, and leave the numbers to the numeric checks below.
  const words = (s) => s.replace(/-?\d+(\.\d+)?/g, "#");
  check(c.name, words(g.rule_verdict.recommendation) === words(c.rule_verdict.recommendation),
    `recommendation wording differs:\n      browser: ${g.rule_verdict.recommendation}\n      python:  ${c.rule_verdict.recommendation}`);

  // A cell joins the off-target list when its predicted activity reaches the target cell's, so a
  // cell sitting within the conversion's own drift of that boundary can legitimately fall either
  // side. Compare the cells that are not within TOL of the boundary, and separately require the
  // browser's own list to be ordered by its own predicted activity.
  const unambiguous = (prof, list, cell) =>
    list.filter((c2) => Math.abs(prof[c2] - prof[cell]) > TOL);
  const gl = unambiguous(g.predicted_profile_log2fc, g.off_target_risk_cells, c.target_cell);
  const wl = unambiguous(w.predicted_profile_log2fc, w.off_target_risk_cells, c.target_cell);
  check(c.name, [...gl].sort().join() === [...wl].sort().join(),
    `off-target cells (excluding cells within ${TOL} of the target) ${JSON.stringify(gl)} vs ${JSON.stringify(wl)}`);

  // The list is ranked, and two cells can sit 0.001 log2FC apart, which is a fifth of the
  // largest difference the conversion makes. Where that happens the two orders are both right,
  // so an inversion is a failure only when Python itself separates the pair by more than TOL.
  for (let i = 0; i < wl.length; i++) {
    for (let j = i + 1; j < wl.length; j++) {
      const sep = Math.abs(w.predicted_profile_log2fc[wl[i]] - w.predicted_profile_log2fc[wl[j]]);
      if (sep <= TOL) continue;
      check(c.name, gl.indexOf(wl[i]) < gl.indexOf(wl[j]),
        `off-target ranking: python puts ${wl[i]} above ${wl[j]} (${sep.toFixed(3)} apart), the browser does not`);
    }
  }
  const acts = g.off_target_risk_cells.map((c2) => g.predicted_profile_log2fc[c2]);
  check(c.name, acts.every((v, i) => i === 0 || acts[i - 1] >= v),
    `off-target list is not ordered by predicted activity: ${JSON.stringify(acts)}`);

  for (const [cell, v] of Object.entries(w.predicted_profile_log2fc)) {
    const d = Math.abs(g.predicted_profile_log2fc[cell] - v);
    if (d > worst) { worst = d; worstWhere = `${c.name}/${cell}`; }
    check(c.name, d <= TOL, `${cell} log2FC ${g.predicted_profile_log2fc[cell]} vs ${v} (|d|=${d.toFixed(4)})`);
  }
  const dg = Math.abs(g.predicted_specificity_gap - w.predicted_specificity_gap);
  check(c.name, dg <= TOL, `gap ${g.predicted_specificity_gap} vs ${w.predicted_specificity_gap}`);
  const dp = Math.abs(g.calibrated_fail_probability - w.calibrated_fail_probability);
  check(c.name, dp <= 0.05, `fail probability ${g.calibrated_fail_probability} vs ${w.calibrated_fail_probability}`);

  // the motif scan is exact arithmetic on the same cached PWMs, so it must match outright
  const stripScan = (s) => JSON.stringify(Object.fromEntries(Object.entries(s.by_cell).map(([k, v]) => [k, v])));
  check(c.name, stripScan(got.m) === stripScan(c.motifs), "motif scan differs");
  check(c.name, JSON.stringify(got.m.erythroid_composite) === JSON.stringify(c.motifs.erythroid_composite),
    "erythroid composite sites differ");

  console.log(`  ${c.name.padEnd(9)} ${g.rule_verdict.verdict.padEnd(10)} gap ${String(g.predicted_specificity_gap).padStart(7)}  ${got.ms} ms`);
}

await browser.close();
server.close();
console.log(`\nlargest log2FC difference vs Python: ${worst.toFixed(4)} (${worstWhere}), tolerance ${TOL}`);
if (fail.length) {
  console.error(`\n${fail.length} parity failure(s):`);
  fail.forEach((f) => console.error("  " + f));
  process.exit(1);
}
console.log(`all ${ref.length} designs match the Python gate`);
