# The live tool, running in the browser

`webdemo/` is the deployed CisFalcon tool: the same interface, with the gate running in the
visitor's own tab instead of on a server. It is published to
<https://belumume.github.io/cisfalcon/> by `.github/workflows/demo-pages.yml`.

## Why it moved

The tool used to run in a paid container (`Dockerfile`, `fly.toml`): 8 GB of RAM to hold six
Keras models, kept warm so the first visitor of the day did not wait 13 seconds for a cold
load. That is a monthly bill for a demo nobody is charged to use, and when the bill lapses the
tool goes dark. Every free container tier either sleeps, is too small for a 1.16 GB working
set, or wants a card on file.

A static page has no such failure mode. There is no server to pay for, nothing to keep warm,
and no bill that can retire the tool. It also removes a privacy question the hosted version
could only answer with a promise: a sequence pasted into this page is scored on the machine it
was typed on and is never sent anywhere.

## What runs here, and what cannot

| Path | In the browser | Why |
| --- | --- | --- |
| `/predict` — the gate verdict | yes | the three fold models run in the tab |
| `/motifs` — JASPAR motif scan | yes | log-odds PWM scan over the cached matrices in `jaspar/` |
| `/batch` — safest-first triage | yes | same ensemble, 64 designs per call |
| `/redesign` — deterministic closed loop | yes | motif surgery then a re-score with the same gate |
| `/diagnose`, `/rescue` — the Claude agent layer | yes, on the visitor's own key | there is no server to hold a key, so the page asks for one |

Every published number in this repository comes from the gate, which needs no key and runs for
everyone. The agent layer calls a paid API, so it runs on the visitor's own Anthropic key.

### The key, and the money

The hosted tool ran the agents on the author's API credit. The two obvious replacements are both
worse: a shared proxy key puts every stranger's usage on one card, and dropping the layer would
remove the thing the committed ablation is about. So the page asks for a key when you click
"Run Claude diagnosis", and:

- it is typed into a password field, held in the tab, and sent to `api.anthropic.com` — which is
  the only place it can be sent, because the page ships a content security policy whose
  `connect-src` allows this origin and Anthropic and nothing else. The browser enforces that;
  the page is not asking to be trusted on it.
- until you ask for a diagnosis, the page contacts nobody at all. The served frontend loads its
  two typefaces from Google, which would hand Google the IP address of everyone who opens the
  page; both are under the SIL Open Font License, so the build fetches them once into
  `webdemo/fonts/` and serves them from this origin. `agents.test.mjs` fails if any request
  leaves for a third host.
- nothing is stored unless you tick "remember while this tab is open", which uses
  `sessionStorage` and is gone when the tab closes. There is a "forget key" button on the cost
  chip.
- usage bills your account, not the author's. The exact cost of each call is computed from the
  token usage Anthropic returns, at the published per-million-token prices, and shown to you —
  a measured number, not an estimate. A diagnosis is a few cents.
- Anthropic's documented opt-in for calling the API from a page
  (`anthropic-dangerous-direct-browser-access: true`) is what makes the cross-origin call
  possible. Their guidance against browser calls is about a site exposing *its own* key to its
  visitors; here the key is the visitor's own and never leaves their machine except to Anthropic.
- an organization with zero data retention or the Compliance API enabled cannot call the API
  from a browser at all; such a key returns a 401 and the page says so and names the CLI path.

The adjudicator and the lenses use the model IDs frozen in `verifier.py` (`claude-opus-4-8`,
`claude-sonnet-5`), because `PREREG.md` names that pair as the arm under test.
`agents.test.mjs` intercepts the calls and asserts the models, prompts, fan-out, tool schemas,
header and key handling, so the layer is tested without spending anything.

## Half the weights, half again in size

The Zenodo record ships six model files. `gate.py` loads the three `dhs64_mpra_*` activity
models for every prediction; the three `dhs64_*` accessibility models are used only by
`accessibility_baseline.py` and `accessibility_crosslab.py`, offline. So the page needs three,
not six: 251 MB of `.h5`, converted to **120 MB of float16 TensorFlow.js weights**, downloaded
once and then cached by the browser. The conversion keeps the ensemble intact — a mean over the
three independent folds, which is the correct mode for a sequence none of them trained on.

## The conversion is checked, not assumed

Float16 weights are not the same arithmetic as the Python path, so the page's agreement with
the published pipeline is measured:

```bash
python webdemo/build.py          # fetch the three models, convert them into webdemo/models/
node webdemo/parity.test.mjs     # headless Chromium vs the Python reference, design by design
```

`parity.test.mjs` serves this directory, drives a real browser against it, and compares the
verdict, recommendation text, most-active cell, both plausibility flags, the off-target list,
every per-cell predicted log2FC, the calibrated failure probability and the full motif scan
against `parity_reference.json`, which `tools/build_parity_reference.py` generates from the
Python gate. It fails on any categorical difference and on any activity drift past 0.02 log2FC.
The deploy workflow runs it, so a conversion that changed an answer stops at CI.

## What is in git and what is not

Committed: the engine that replaced the backend (`engine.js`), the loading indicator
(`boot.js`, `boot.css`), the vendored TensorFlow.js runtime (`vendor/tf.min.js`, pinned 4.22.0,
so the page depends on no third-party host at run time), the build (`build.py`) and the parity
check with its reference.

Generated, and therefore ignored: `index.html`, `app.js` and `styles.css`, which `build.py`
copies from `webapp/backend/static/` and patches, so the demo can never drift from the frontend
the server serves; `jaspar/` and `data/`, copied from the paths the API read them from;
`data/calibration_iso.json`, exported from `data/calibration.csv`; and `models/`, fetched from
Zenodo and converted. A clone of this repository stays small, and nothing here is a second copy
of something already in it.

If the frontend changes in a way that moves one of the strings `build.py` patches, the build
stops and names the string. That is deliberate: the alternative is a demo that quietly keeps
calling a server that is not there.

## Running it locally

```bash
python webdemo/build.py
python -m http.server 8080 -d webdemo    # then open http://127.0.0.1:8080/
```

`file://` will not work: the model loader fetches JSON and weight shards, which needs HTTP.
