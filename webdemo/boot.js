/* Weight loading, shown honestly.
 *
 * The three fold models are 120 MB of float16 weights, so the first visit downloads them once
 * and the browser caches them. Loading starts the moment the page opens, while the visitor is
 * still reading the overview, so by the time they reach Verify the gate is usually warm. The
 * chip reports what is happening and gets out of the way; nothing in the page is blocked.
 */
(function () {
  "use strict";
  const bar = document.createElement("div");
  bar.className = "boot-bar";
  const chip = document.createElement("div");
  chip.className = "boot-chip";
  chip.innerHTML = '<span class="boot-dot"></span><span class="boot-txt">loading the model</span>';
  const txt = () => chip.querySelector(".boot-txt");

  document.addEventListener("DOMContentLoaded", () => {
    document.body.appendChild(bar);
    document.body.appendChild(chip);
    start();
  });

  function hide(delay) {
    setTimeout(() => { bar.classList.add("gone"); chip.classList.add("gone"); }, delay);
  }

  // 120 MB is not a download to start behind someone's back on a metered connection, so on a
  // slow or data-saving link the page says what it will cost and waits for the visitor to ask
  // for a check; the first call then loads the model.
  function metered() {
    const c = navigator.connection;
    if (!c) return false;
    return !!c.saveData || ["slow-2g", "2g", "3g"].includes(c.effectiveType);
  }

  async function start() {
    const CF = window.CF;
    if (!CF || typeof tf === "undefined") {
      chip.classList.add("bad");
      txt().textContent = "this page's scripts did not finish loading; reload the page";
      return;
    }
    if (metered()) {
      txt().textContent = "model is 120 MB; it loads when you run your first check";
      bar.classList.add("gone");
      chip.classList.add("ok");
      hide(9000);
      return;
    }
    CF.onProgress((p) => {
      const pct = Math.round(p.frac * 100);
      bar.style.width = Math.max(2, pct) + "%";
      if (pct < 100) txt().textContent = `loading the model · 120 MB · ${pct}%`;
    });
    const t0 = performance.now();
    try {
      await CF.ready;
      await CF.loadModels();
      const backend = tf.getBackend();
      const secs = ((performance.now() - t0) / 1000).toFixed(1);
      chip.classList.add("ok");
      txt().textContent = backend === "webgl" || backend === "webgpu"
        ? `model ready in ${secs}s · running on your GPU`
        : `model ready in ${secs}s · running on your CPU, so a check takes a few seconds`;
      hide(4500);
    } catch (e) {
      chip.classList.add("bad");
      txt().textContent = "the model did not load: " + (e && e.message ? e.message : "unknown error");
      bar.classList.add("gone");
    }
  }
})();
