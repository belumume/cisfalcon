/* The Claude agent layer, run from the visitor's own browser with the visitor's own key.
 *
 * The hosted tool ran this server-side on the author's API credit. A static page has no server
 * and no credit, and the alternative designs are both worse: a shared proxy key would put every
 * stranger's usage on one card, and dropping the layer would cut the thing the published
 * ablation is about. So the page asks the visitor for their own key, keeps it in this tab, and
 * calls Anthropic directly from here.
 *
 * WHAT THAT COSTS THE VISITOR, AND WHAT IT COSTS THE PAGE'S OWNER. Usage bills the key's own
 * account, so a diagnosis costs the visitor a few cents and the page's owner nothing. The real
 * token usage comes back in every response, so the panel reports what the call actually cost
 * rather than an estimate (PRICES below, from Anthropic's published per-million-token prices).
 *
 * THE KEY. It is read from a password field, held in a variable, and sent in one place: a fetch
 * to https://api.anthropic.com. It is never written to localStorage, never put in a URL, and
 * never sent anywhere else — and that is not only a promise, because the page ships a Content
 * Security Policy whose connect-src allows itself and api.anthropic.com and nothing else, so
 * the browser refuses any other destination. "Remember while this tab is open" uses
 * sessionStorage, which the browser drops when the tab closes. Anthropic's own guidance is to
 * call the API from a back end rather than from a page, because a page's author can expose their
 * own key that way; the case here is the inverse, a key the visitor holds and types themselves,
 * which is the pattern the TypeScript SDK's dangerouslyAllowBrowser flag exists for.
 *
 * FROZEN MODELS. ORCH_MODEL and LENS_MODEL match verifier.py exactly. They are frozen
 * experimental parameters: PREREG.md names the Opus 4.8 adjudicator as the arm under test and
 * every committed agent-layer result was produced by this pair, so a newer model here would
 * silently stop reproducing the published panel.
 */
(function () {
  "use strict";

  const API = "https://api.anthropic.com/v1/messages";
  const VERSION = "2023-06-01";
  const ORCH_MODEL = "claude-opus-4-8";
  const LENS_MODEL = "claude-sonnet-5";

  // US dollars per million tokens, from Anthropic's published pricing (read 2026-11-12).
  const PRICES = {
    "claude-opus-4-8": { in: 5, out: 25 },
    "claude-sonnet-5": { in: 2, out: 10 },
  };

  const SS_KEY = "cisfalcon.anthropic_key";
  let KEY = null;
  try { KEY = sessionStorage.getItem(SS_KEY) || null; } catch (e) { /* private mode */ }

  const spend = { usd: 0, calls: 0 };

  const GROUND_TRUTH =
    "Leakage-immune cross-lab validation of this gate: on 93,435 INDEPENDENT AI-designed enhancers " +
    "from a different lab, activity model, and generators the model never saw (Gosai et al 2024, " +
    "Nature; zero training overlap), it discriminates measured wet-lab specificity failures at AUROC " +
    "0.80, versus 0.50 for GC-content and length baselines. It is a triage RANKER, not a hard abort " +
    "gate: pooled at the 6.3% base failure rate, flagging the riskiest 2% enriches for real failures " +
    "7.74x (PPV 0.49) and the riskiest 10% captures 43% of all failures. Those pooled triage figures " +
    "are NOT evidence of sequence-level discrimination: a sequence-free rule ranking by stratum base " +
    "rate alone achieves a 91% pooled reduction versus the model's 70%. Conditioned within " +
    "(cell x generator) the genuine triage value is 41% macro reduction and 2.59x macro enrichment, " +
    "with three strata below 1.0x. The genuine per-sequence signal, " +
    "with both the target-cell and generator base-rates removed, is AUROC 0.66 (strong on failure-" +
    "prone designs, near chance on the best-optimized ones). An in-distribution sanity check scores " +
    "0.896 but carries a near-duplicate-leakage caveat, so the cross-lab number is the flagship. " +
    "Failure is defined transparently: a design FAILS if it is not most-active in its intended target " +
    "cell (specificity gap <= 0). The emitted failure probability is calibrated marginally on this " +
    "design population (held-out ECE 0.0031), not conditioned per target cell. Marginal calibration " +
    "is dominated by the low-risk bin, which holds 79% of held-out designs, so the middle of the " +
    "range is close to exact (0.4-0.5 bin: 0.420 predicted, 0.420 observed, n=355) while the " +
    "high-risk tail is thinly measured (0.6-0.7 bin: 0.696 predicted, 0.619 observed, n=42). Treat " +
    "the ranking as the reliable signal and an absolute risk above ~0.6 as noisy.\n\n" +
    "PLAUSIBILITY PRE-CHECK (do this FIRST): the report carries two flags. If low_complexity is " +
    "true the sequence is degenerate or repetitive (a homopolymer like poly-A or a short-period " +
    "tandem repeat), not a diverse enhancer-like sequence. If low_activity is true it is predicted " +
    "weakly active in every cell (within the range of random sequences). In EITHER case the design " +
    "is NOT a credible enhancer and the specificity/off-target question is moot: say that plainly and " +
    "first, and do NOT diagnose off-target cell risk as if it were a real design.";

  const PROSE = " Answer in 2 to 4 sentences of plain prose. Do not use markdown, headers, bold, or bullet lists.";
  const LENSES = {
    mechanism:
      "You are a regulatory-genomics reviewer. Given a model-predicted per-cell-type activity " +
      "profile for an AI-designed enhancer and its intended target cell, explain in mechanistic " +
      "terms whether it is predicted to be cell-type SPECIFIC, and name the specific off-target " +
      "cell types that are the risk. Be concrete and brief." + PROSE,
    precedent:
      "You are a QC analyst grounding a prediction in measured data. Given the design's predicted " +
      "specificity gap and target cell, state what the held-out benchmark implies about this " +
      "design's failure probability, and how much to trust it. Cite the ground-truth numbers." + PROSE,
    adversary:
      "You are an adversarial skeptic. Argue the gate's verdict on this design could be WRONG: " +
      "model blind spots, out-of-distribution sequence features, calibration limits, target cells " +
      "the model predicts poorly. Default to raising real doubts, not rubber-stamping." + PROSE,
  };

  const VERDICT_SCHEMA = {
    type: "object",
    properties: {
      verdict: { type: "string", enum: ["FAIL", "PASS", "BORDERLINE"] },
      confidence: { type: "number" },
      recommendation: { type: "string" },
      reasoning: { type: "string" },
      grounded_in: { type: "string" },
    },
    required: ["verdict", "confidence", "recommendation", "reasoning"],
  };

  const RESCUE_TOOL = {
    name: "apply_and_rescore",
    description:
      "Apply a grounded motif edit to the CURRENT design and re-score it with the frozen activity " +
      "gate. Disrupts the named off-target driver TF sites and installs consensus copies of the named " +
      "target driver TFs, then returns the new predicted specificity gap and most-active cell.",
    input_schema: {
      type: "object",
      properties: {
        disrupt_off_target_tfs: { type: "array", items: { type: "string" },
          description: "Driver TF names of the predicted OFF-target cell to disrupt." },
        install_target_tfs: { type: "array", items: { type: "string" },
          description: "Driver TF names of the TARGET cell to install." },
        copies_per_tf: { type: "integer", description: "Consensus copies per installed TF (1-3)." },
      },
      required: ["disrupt_off_target_tfs", "install_target_tfs", "copies_per_tf"],
    },
  };

  /* ------------------------------------------------------------------ the one network call */
  function priceOf(model, usage) {
    const p = PRICES[model];
    if (!p || !usage) return 0;
    return ((usage.input_tokens || 0) * p.in + (usage.output_tokens || 0) * p.out) / 1e6;
  }

  async function call(body) {
    if (!KEY) throw new Error("no API key set");
    const res = await fetch(API, {
      method: "POST",
      headers: {
        "content-type": "application/json",
        "x-api-key": KEY,
        "anthropic-version": VERSION,
        // Documented opt-in for calling the API from a page; without it the browser's
        // cross-origin request is refused.
        "anthropic-dangerous-direct-browser-access": "true",
      },
      body: JSON.stringify(body),
    });
    const j = await res.json().catch(() => ({}));
    if (!res.ok) {
      const msg = (j && j.error && j.error.message) || res.statusText;
      if (res.status === 401 && /CORS requests are not allowed/i.test(msg)) {
        throw new Error(
          "This key's organization has zero data retention or the Compliance API enabled, and " +
          "Anthropic blocks browser calls for those organizations. Run the agent layer from the " +
          "repository instead: python verifier.py --seq ... --target ..."
        );
      }
      if (res.status === 401) throw new Error("Anthropic rejected the key: " + msg);
      throw new Error(`Anthropic API ${res.status}: ${msg}`);
    }
    spend.usd += priceOf(body.model, j.usage);
    spend.calls += 1;
    return j;
  }

  // Same contract as verifier._agent: free text, or the tool input when a schema is given.
  async function agent(model, system, user, schema) {
    const body = { model, max_tokens: 2000, system, messages: [{ role: "user", content: user }] };
    if (schema) {
      body.tools = [{ name: "report", description: "Return the structured result.", input_schema: schema }];
      body.tool_choice = { type: "tool", name: "report" };
    }
    const resp = await call(body);
    if (resp.stop_reason === "refusal") return { refused: true };
    if (schema) {
      const tu = (resp.content || []).find((b) => b.type === "tool_use");
      return tu ? tu.input : {};
    }
    return (resp.content || []).filter((b) => b.type === "text").map((b) => b.text).join("");
  }

  /* ------------------------------------------------------------------------ the four agents */
  async function diagnose(report, scan) {
    const ctx = `${GROUND_TRUTH}\n\nDESIGN under review (predicted, pre-synthesis):\n${JSON.stringify(report, null, 2)}`;
    const names = Object.keys(LENSES);
    // the three lenses run in parallel, as the ThreadPoolExecutor did server-side
    const texts = await Promise.all(names.map((n) => agent(LENS_MODEL, LENSES[n], ctx)));
    const reviews = {};
    names.forEach((n, i) => (reviews[n] = texts[i]));

    const verdict = await agent(
      ORCH_MODEL,
      "You are the CisFalcon adjudicator. Synthesize the gate report and the three " +
      "independent reviews into ONE pre-synthesis verdict for a wet-lab scientist deciding " +
      "whether to synthesize this AI-designed enhancer. This is a DEFENSIVE gate: a FAIL " +
      "means 'do not synthesize, it will likely miss its target cell'. Be calibrated and " +
      "cite the measured ground truth.",
      `${ctx}\n\nINDEPENDENT REVIEWS:\n${JSON.stringify(reviews, null, 2)}`,
      VERDICT_SCHEMA
    );
    return { reviews, verdict };
  }

  // The motif-redesign agent from the web backend: name the drivers to remove and add, grounded
  // in the real PWM scan rather than in the model's memory of which TF drives which cell.
  async function motifRedesign(report, scan, scanSummary) {
    const schema = {
      type: "object",
      properties: {
        off_target_cell: { type: "string" },
        off_target_drivers: { type: "array", items: { type: "string" } },
        target_drivers_to_add: { type: "array", items: { type: "string" } },
        redesign: { type: "string" },
      },
      required: ["off_target_drivers", "target_drivers_to_add", "redesign"],
    };
    const user =
      `An AI-designed enhancer intended to be specific to ${report.target_cell} is predicted ` +
      `most-active in ${report.predicted_most_active_cell} instead (specificity gap ` +
      `${report.predicted_specificity_gap}). Per-cell predicted activity (log2FC): ` +
      `${JSON.stringify(report.predicted_profile_log2fc)}.\n\n${scanSummary}\n\n` +
      "Using the grounded motif scan above as evidence, name the transcription-factor motifs " +
      `that drive the predicted off-target cell (${report.predicted_most_active_cell}) and ` +
      "should be REMOVED (prefer motifs the scan confirms are present), the TF motifs that drive " +
      `${report.target_cell} specificity and should be ADDED (prefer ones the scan shows are ` +
      "absent), and a one-sentence concrete redesign. Cite the scanned evidence; use real TF names.";
    try {
      return await agent(
        LENS_MODEL,
        "You are a cis-regulatory design expert. Ground every claim in the provided JASPAR " +
        "motif scan. Give a precise, mechanistic, actionable motif-level redesign. No hedging.",
        user,
        schema
      );
    } catch (e) {
      return null;
    }
  }

  /* --------------------------------------------- the tool-using rescue loop (closed_loop.py) */
  async function rescue(seq, target, deps, maxRounds) {
    maxRounds = maxRounds || 4;
    const { score, driverSites, consensusSeq, DRIVERS } = deps;

    async function applyEdit(cur, offCell, targetCell, disruptTfs, installTfs, copies) {
      const offDrivers = new Set(DRIVERS[offCell] || []);
      const want = new Set((disruptTfs || []).filter((t) => offDrivers.has(t)));
      const chars = cur.split("");
      for (const site of await driverSites(cur, offCell, 8)) {
        if (!want.has(site.tf)) continue;
        const p = site.pos, L = site.length;
        if (p + L <= chars.length) {
          const filler = "GAATTC".repeat(Math.floor(L / 6) + 1).slice(0, L);
          chars.splice(p, L, ...filler.split(""));
        }
      }
      let edited = chars.join("");
      const tgtDrivers = new Set(DRIVERS[targetCell] || []);
      let n = 0;
      const cp = Math.max(1, Math.min(parseInt(copies || 2, 10) || 2, 3));
      for (const tf of installTfs || []) {
        if (!tgtDrivers.has(tf)) continue;
        const cons = await consensusSeq(tf);
        if (!cons) continue;
        for (let i = 0; i < cp; i++) {
          const at = Math.min(edited.length, 25 + n * (cons.length + 10));
          edited = edited.slice(0, at) + cons + edited.slice(at);
          n++;
        }
      }
      return edited.slice(0, 500);
    }

    let cur = seq;
    let rpt = await score(cur, target);
    const off = rpt.most_active;
    const history = [{ round: 0, gap: rpt.gap, most_active: off, passed: !rpt.fail }];
    if (!rpt.fail) {
      return { passed: true, final_gap: rpt.gap, rounds: 0, history, final_seq: cur, start_gap: rpt.gap };
    }
    const offDrivers = DRIVERS[off] || [], tgtDrivers = DRIVERS[target] || [];
    const system =
      "You are a cis-regulatory design-rescue agent. An AI-designed enhancer meant to be specific to " +
      `${target} is predicted most-active in ${off} instead, so it FAILS (the specificity gap must be > 0 ` +
      "to pass). Iteratively edit it so the frozen activity model predicts it most-active in its target. " +
      `You may ONLY disrupt the off-target cell's real driver TFs (${offDrivers.join(", ") || "none"}) and ` +
      `install the target cell's real driver TFs (${tgtDrivers.join(", ") || "none"}); you cannot invent ` +
      "sequence. Call apply_and_rescore, read the new gap, and iterate. Stop the moment the gap is positive " +
      "(PASS), or abort if an edit does not improve the gap. Be efficient; prefer the smallest edit that works.";
    const messages = [{
      role: "user",
      content:
        `Current design: predicted specificity gap ${rpt.gap} (negative = failing), most-active ${off}, ` +
        `target ${target}. Rescue it to a positive gap.`,
    }];
    let passed = false;
    for (let rnd = 1; rnd <= maxRounds; rnd++) {
      const resp = await call({
        model: ORCH_MODEL, max_tokens: 2000, system, tools: [RESCUE_TOOL], messages,
      });
      messages.push({ role: "assistant", content: resp.content });
      const tu = (resp.content || []).find((b) => b.type === "tool_use");
      if (!tu) break; // Claude stopped or aborted
      cur = await applyEdit(cur, off, target, tu.input.disrupt_off_target_tfs,
        tu.input.install_target_tfs, tu.input.copies_per_tf);
      rpt = await score(cur, target);
      passed = !rpt.fail;
      history.push({ round: rnd, gap: rpt.gap, most_active: rpt.most_active, passed });
      messages.push({
        role: "user",
        content: [{
          type: "tool_result",
          tool_use_id: tu.id,
          content: `After the edit: specificity gap ${rpt.gap}, most-active ${rpt.most_active}, ` +
            (passed ? "PASS (gap > 0)." : "still failing (gap <= 0)."),
        }],
      });
      if (passed) break;
    }
    return {
      passed, final_gap: rpt.gap, rounds: history.length - 1, history,
      final_seq: cur, start_gap: history[0].gap,
    };
  }

  /* ------------------------------------------------------------------------- the key prompt */
  const KEY_HELP_URL = "https://platform.claude.com/settings/keys";

  function ask() {
    // Resolves with true once a key is entered, false if the visitor cancels.
    return new Promise((resolve) => {
      const wrap = document.createElement("div");
      wrap.className = "keyask";
      wrap.innerHTML = `
        <div class="keyask-card" role="dialog" aria-modal="true" aria-labelledby="keyask-h">
          <div class="cap">CLAUDE AGENT LAYER · your key, your tab</div>
          <h3 id="keyask-h">This part needs an Anthropic API key</h3>
          <p>Everything else on this page runs offline in your browser. The four-agent diagnosis
             calls Anthropic, which costs money, so it runs on <b>your</b> key and bills your
             account: typically a few cents per design, and the exact cost of each call is shown
             afterwards.</p>
          <p class="keyask-sec">The key is held in this tab and sent to
             <code>api.anthropic.com</code> and nowhere else. This page's content security policy
             permits no other destination, so your browser enforces that rather than trusting it.
             Nothing is stored unless you tick the box, and that store is cleared when you close
             the tab.</p>
          <label class="keyask-lbl" for="keyask-input">API key</label>
          <input id="keyask-input" type="password" autocomplete="off" spellcheck="false"
                 placeholder="sk-ant-..." />
          <label class="keyask-remember"><input id="keyask-remember" type="checkbox" />
            remember while this tab is open</label>
          <div class="keyask-row">
            <button class="keyask-go" id="keyask-go">Run the diagnosis</button>
            <button class="keyask-no" id="keyask-no">Cancel</button>
            <a href="${KEY_HELP_URL}" target="_blank" rel="noopener">get a key</a>
          </div>
          <div class="keyask-err" id="keyask-err"></div>
        </div>`;
      document.body.appendChild(wrap);
      const input = wrap.querySelector("#keyask-input");
      const errEl = wrap.querySelector("#keyask-err");
      input.focus();
      const close = (ok) => { wrap.remove(); resolve(ok); };
      wrap.querySelector("#keyask-no").addEventListener("click", () => close(false));
      wrap.addEventListener("click", (e) => { if (e.target === wrap) close(false); });
      wrap.addEventListener("keydown", (e) => { if (e.key === "Escape") close(false); });
      const go = () => {
        const v = input.value.trim();
        if (!v) { errEl.textContent = "Paste a key, or cancel."; return; }
        KEY = v;
        if (wrap.querySelector("#keyask-remember").checked) {
          try { sessionStorage.setItem(SS_KEY, v); } catch (e) { /* private mode: keep it in memory */ }
        }
        close(true);
      };
      wrap.querySelector("#keyask-go").addEventListener("click", go);
      input.addEventListener("keydown", (e) => { if (e.key === "Enter") go(); });
    });
  }

  async function ensureKey() {
    if (KEY) return true;
    return ask();
  }

  function forgetKey() {
    KEY = null;
    try { sessionStorage.removeItem(SS_KEY); } catch (e) { /* nothing to clear */ }
  }

  /* --------------------------------------------------------------- what it actually cost */
  // Priced from the usage each response carries, so the visitor sees a measured number rather
  // than an estimate. The chip also carries the way out: forget the key.
  function showCost() {
    if (!spend.calls) return;
    let chip = document.getElementById("cf-cost");
    if (!chip) {
      chip = document.createElement("div");
      chip.id = "cf-cost";
      chip.className = "cost-chip";
      document.body.appendChild(chip);
    }
    const usd = spend.usd < 0.01 ? spend.usd.toFixed(4) : spend.usd.toFixed(3);
    chip.textContent = "Anthropic usage this tab: $" + usd + " over " + spend.calls +
      (spend.calls === 1 ? " call" : " calls") + ", on your key · ";
    const forget = document.createElement("button");
    forget.className = "cost-forget";
    forget.textContent = "forget key";
    forget.addEventListener("click", () => { forgetKey(); chip.remove(); });
    chip.appendChild(forget);
  }

  window.CFAgents = {
    hasKey: () => !!KEY,
    showCost,
    ensureKey,
    forgetKey,
    diagnose,
    motifRedesign,
    rescue,
    spend,
    models: { ORCH_MODEL, LENS_MODEL },
    costUsd: () => spend.usd,
  };
})();
