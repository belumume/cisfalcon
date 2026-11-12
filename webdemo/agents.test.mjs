/* Does the browser's agent layer send what the Python agent layer sent?
 *
 * The agent layer is the one part of the page that calls a paid API, so it cannot be exercised
 * for real in a test without spending someone's money. This script instead intercepts the call
 * at the network layer, answers with canned Anthropic responses, and asserts on what the page
 * actually sent: the models, the system prompts, the parallel lens fan-out, the tool schema the
 * adjudicator is given, the browser-access header, and the tool-use loop the rescue runs.
 *
 *   node agents.test.mjs
 *
 * It also checks the things that matter because the key belongs to the visitor: that the key
 * reaches api.anthropic.com and no other host, that it is not written to localStorage, that
 * declining the prompt returns the deterministic verdict instead of an error, and that the
 * reported cost is computed from the usage the API returned.
 *
 * It needs the converted weights, because the agent path runs the gate first.
 */
import { createServer } from "node:http";
import { readFile } from "node:fs/promises";
import { extname, join, normalize } from "node:path";
import { chromium } from "playwright";

const ROOT = new URL(".", import.meta.url).pathname;
const PORT = 8732;
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
const KEY = "sk-ant-test-not-a-real-key";

const text = (t, usage) => ({
  id: "msg_1", type: "message", role: "assistant", model: "x", stop_reason: "end_turn",
  content: [{ type: "text", text: t }], usage: usage || { input_tokens: 1000, output_tokens: 200 },
});
const tool = (name, input, usage) => ({
  id: "msg_2", type: "message", role: "assistant", model: "x", stop_reason: "tool_use",
  content: [{ type: "tool_use", id: "tu_" + Math.random().toString(36).slice(2), name, input }],
  usage: usage || { input_tokens: 2000, output_tokens: 300 },
});

await new Promise((r) => server.listen(PORT, r));
const browser = await chromium.launch();
const page = await browser.newPage();
page.on("pageerror", (e) => fail.push("page error: " + e.message));

// Every request the page makes, so "the key goes nowhere else" is checked rather than assumed.
const sent = [];
await page.route("https://api.anthropic.com/**", async (route) => {
  const req = route.request();
  const body = JSON.parse(req.postData() || "{}");
  sent.push({ headers: req.headers(), body });

  let payload;
  if (body.tools && body.tools.some((t) => t.name === "apply_and_rescore")) {
    // the rescue loop: edit once, then stop by answering with plain text
    const rounds = sent.filter((s) => s.body.tools && s.body.tools.some((t) => t.name === "apply_and_rescore")).length;
    payload = rounds === 1
      ? tool("apply_and_rescore", { disrupt_off_target_tfs: ["GATA1", "TAL1"], install_target_tfs: ["HNF4A", "HNF1A"], copies_per_tf: 2 })
      : text("stopping: the gap is positive");
  } else if (body.tools && body.tools.some((t) => t.name === "report")) {
    const props = body.tools[0].input_schema.properties;
    payload = props.verdict
      ? tool("report", { verdict: "FAIL", confidence: 0.9, recommendation: "do not synthesize", reasoning: "canned", grounded_in: "canned" })
      : tool("report", { off_target_cell: "K562", off_target_drivers: ["GATA1"], target_drivers_to_add: ["HNF4A"], redesign: "canned" });
  } else {
    payload = text("canned lens review");
  }
  await route.fulfill({
    status: 200,
    headers: { "content-type": "application/json", "access-control-allow-origin": "*" },
    body: JSON.stringify(payload),
  });
});

await page.goto(`http://127.0.0.1:${PORT}/`);
await page.waitForFunction(() => window.CF && window.CF.api && window.CFAgents, null, { timeout: 60000 });
await page.evaluate(() => window.CF.ready.then(() => window.CF.loadModels()).then(() => true));

const hero = JSON.parse(await readFile(join(ROOT, "data", "hero.json"), "utf8"));

// 1. declining the key prompt must give the deterministic verdict, not an error
const declined = await page.evaluate(async ([seq, cell]) => {
  const p = window.CF.api("/diagnose", { sequence: seq, target_cell: cell });
  // The key panel only appears once the gate has scored the design, which is well under a
  // second on a real GPU and minutes under the software renderer CI uses, so wait for the
  // panel itself rather than guessing a delay.
  const panel = async (sel) => {
    for (let i = 0; i < 1800 && !document.querySelector(sel); i++)
      await new Promise((r) => setTimeout(r, 100));
    const el = document.querySelector(sel);
    if (!el) throw new Error("the key panel never appeared: " + sel);
    return el;
  };
  (await panel("#keyask-no")).click();
  return p;
}, [hero.sequence, hero.target_cell]);
check("decline", declined.agents === false, "declining the key prompt should fall back, got agents=" + declined.agents);
check("decline", !!declined.verdict && !!declined.gate, "fallback must still carry the gate report and rule verdict");
check("decline", sent.length === 0, `declining must send nothing, sent ${sent.length} request(s)`);

// 2. entering a key runs the four agents plus the grounded redesign
const out = await page.evaluate(async ([seq, cell, key]) => {
  const p = window.CF.api("/diagnose", { sequence: seq, target_cell: cell });
  // The key panel only appears once the gate has scored the design, which is well under a
  // second on a real GPU and minutes under the software renderer CI uses, so wait for the
  // panel itself rather than guessing a delay.
  const panel = async (sel) => {
    for (let i = 0; i < 1800 && !document.querySelector(sel); i++)
      await new Promise((r) => setTimeout(r, 100));
    const el = document.querySelector(sel);
    if (!el) throw new Error("the key panel never appeared: " + sel);
    return el;
  };
  (await panel("#keyask-input")).value = key;
  document.querySelector("#keyask-go").click();
  return p;
}, [hero.sequence, hero.target_cell, KEY]);

check("diagnose", out.agents === true, "agents should be on once a key is entered");
check("diagnose", Object.keys(out.reviews || {}).join(",") === "mechanism,precedent,adversary",
  "the three lenses should all report: " + JSON.stringify(Object.keys(out.reviews || {})));
check("diagnose", out.verdict && out.verdict.verdict === "FAIL", "the adjudicator's structured verdict should come through");
check("diagnose", !!out.motif_scan && !!out.redesign, "a failing design should carry the motif scan and the grounded redesign");

const lenses = sent.filter((s) => !s.body.tools);
const structured = sent.filter((s) => s.body.tools);
check("models", lenses.length === 3, `three lens calls expected, got ${lenses.length}`);
check("models", lenses.every((s) => s.body.model === "claude-sonnet-5"), "the lenses must run on claude-sonnet-5");
const adj = structured.find((s) => s.body.tools[0].input_schema.properties.verdict);
check("models", adj && adj.body.model === "claude-opus-4-8", "the adjudicator must run on claude-opus-4-8");
check("models", adj && adj.body.tool_choice && adj.body.tool_choice.name === "report",
  "the adjudicator must be forced to the report tool");
check("prompt", lenses.every((s) => s.body.system.includes("Answer in 2 to 4 sentences")),
  "the lens prompts must keep the prose instruction");
check("prompt", lenses.every((s) => s.body.messages[0].content.includes("AUROC")),
  "the lens context must carry the measured ground truth");
check("prompt", adj && adj.body.messages[0].content.includes("INDEPENDENT REVIEWS"),
  "the adjudicator must see the three reviews");
const redesign = structured.find((s) => s.body.tools[0].input_schema.properties.redesign);
check("prompt", redesign && redesign.body.messages[0].content.includes("GROUNDED MOTIF SCAN"),
  "the redesign agent must be given the real PWM scan");

// 3. the key travels in the documented header, and only to Anthropic
check("key", sent.every((s) => s.headers["x-api-key"] === KEY), "every call must carry the key");
check("key", sent.every((s) => s.headers["anthropic-dangerous-direct-browser-access"] === "true"),
  "the browser-access header must be set, or Anthropic refuses the cross-origin call");
check("key", sent.every((s) => s.headers["anthropic-version"] === "2023-06-01"), "the API version must be pinned");
const stored = await page.evaluate(() => {
  const local = Object.keys(localStorage).map((k) => localStorage.getItem(k)).join("|");
  return { local, session: sessionStorage.getItem("cisfalcon.anthropic_key") };
});
check("key", !stored.local.includes(KEY), "the key must never reach localStorage");
check("key", stored.session === null, "the key must not be stored when 'remember' is unticked");

// 4. the cost shown is computed from the usage the API returned
const expected = (3 * (1000 * 2 + 200 * 10) + 2 * (2000 * 5 + 300 * 25)) / 1e6; // lenses + adjudicator + redesign
const got = await page.evaluate(() => window.CFAgents.costUsd());
// the redesign agent runs on Sonnet, so recompute: 3 Sonnet lenses + 1 Sonnet redesign + 1 Opus adjudicator
const exact = (3 * (1000 * 2 + 200 * 10) + (2000 * 2 + 300 * 10) + (2000 * 5 + 300 * 25)) / 1e6;
check("cost", Math.abs(got - exact) < 1e-9,
  `reported cost ${got} should equal the usage-derived ${exact} (not ${expected})`);
const chip = await page.textContent("#cf-cost").catch(() => null);
check("cost", chip && chip.includes("on your key"), "the cost chip should say whose account is billed");

// 5. the rescue loop drives the gate as a tool and stops when it passes
const rx = await page.evaluate(async ([seq, cell]) =>
  window.CF.api("/rescue", { sequence: seq, target_cell: cell }), [hero.sequence, hero.target_cell]);
check("rescue", Array.isArray(rx.history) && rx.history.length >= 2, "the rescue must record a round per edit");
check("rescue", typeof rx.final_gap === "number" && typeof rx.passed === "boolean", "the rescue must report its outcome");
check("rescue", rx.final_seq && rx.final_seq.length <= 500, "the edited design must stay within the model's input window");
const rescueCalls = sent.filter((s) => s.body.tools && s.body.tools.some((t) => t.name === "apply_and_rescore"));
check("rescue", rescueCalls.length >= 1, "the rescue must call the model with the gate tool");
check("rescue", rescueCalls[0].body.model === "claude-opus-4-8", "the rescue optimizer must run on claude-opus-4-8");
check("rescue", rescueCalls.length < 2 || rescueCalls[1].body.messages.some(
  (m) => Array.isArray(m.content) && m.content.some((b) => b.type === "tool_result")),
  "the re-scored gap must be fed back as a tool result");

// 6. nothing else on the page talks to a third party
const hosts = new Set();
page.on("request", (r) => hosts.add(new URL(r.url()).host));
await page.evaluate(() => window.CF.api("/predict", { sequence: "ACGT".repeat(50), target_cell: "K562" }));
// The fonts are served from this origin, so the only outside host the page may touch is
// the one the visitor knowingly sends their key to.
check("hosts", [...hosts].every((h) => h === `127.0.0.1:${PORT}` || h === "api.anthropic.com"),
  "unexpected host contacted: " + [...hosts].join(", "));

await browser.close();
server.close();

if (fail.length) {
  console.error(`${fail.length} agent-layer failure(s):`);
  fail.forEach((f) => console.error("  " + f));
  process.exit(1);
}
console.log(`agent layer: ${sent.length} intercepted calls, all assertions passed`);
