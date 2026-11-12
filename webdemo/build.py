"""Build the browser bundle: take the served frontend, point it at the in-browser engine, and
convert the three activity fold models for the web.

ONE SOURCE OF TRUTH. The page a visitor sees is the frontend in `webapp/backend/static/`, not a
copy of it. A second committed copy would drift from the first the next time someone edits the
UI, and nothing would say so. This script copies it, applies a small, asserted patch (point
`api()` at `engine.js`; load the runtime; say on the page that it runs locally), and fails loudly
if any patched string is no longer there — which is the signal that the frontend changed and the
patch needs updating, rather than a silently stale demo.

WHY ONLY THREE MODELS. The Zenodo record ships six. `gate.py` loads the `dhs64_mpra_*` trio for
every activity prediction (`kind="mpra"`, the default); the `dhs64_*` trio is the accessibility
head, used only by `accessibility_baseline.py` and `accessibility_crosslab.py`, offline. So the
browser needs half the weights: 251 MB of .h5 in, 120 MB of float16 TensorFlow.js weights out,
downloaded once per visitor and then cached by the browser.

WHY FLOAT16 IS SAFE HERE, AND HOW THAT IS CHECKED. The gate's published numbers are a ranking
and a sign test on a predicted activity gap, both far coarser than the precision float16 costs.
That is a reason to expect agreement, not evidence of it: `parity.test.mjs` measures the real
difference against the Python gate on a fixed design set and fails if any verdict, flag,
most-active cell or motif call moves, or any predicted log2FC drifts past its tolerance.

    python webdemo/build.py              # sync the page, convert the weights
    python webdemo/build.py --no-models  # sync only (no TensorFlow needed)
    node webdemo/parity.test.mjs         # then prove it matches Python

Conversion needs tensorflowjs, which pins its own TensorFlow; keep it in its own virtualenv
rather than beside the reviewer requirements, which deliberately exclude TensorFlow altogether:

    python3.11 -m venv .tfjs && .tfjs/bin/pip install 'tensorflowjs==4.22.0' \
        'tensorflow==2.19.0' 'ydf==0.15.0' 'setuptools<81'

The two extra pins matter: unpinned, pip pairs a protobuf-5 TensorFlow with a protobuf-6 ydf
and the converter fails at import.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
STATIC = ROOT / "webapp" / "backend" / "static"
FOLDS = [0, 1, 3]
CACHE_BUST = "20261112a"

# The two typefaces the page uses, both under the SIL Open Font License, which permits
# serving them from this origin. Latin and latin-ext cover every glyph the page renders.
GOOGLE_FONTS = (
    "https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600"
    "&family=Space+Grotesk:wght@400;500;600;700&display=swap"
)
FONT_SUBSETS = ("latin", "latin-ext")

# Small data files the page fetches, copied from the paths the API used to read them from.
DATA_FILES = [
    (ROOT / "data" / "gosai_designed" / "hero.json", "hero.json"),
    (ROOT / "data" / "gosai_designed" / "brain_hero.json", "brain_hero.json"),
    (ROOT / "data" / "gosai_designed" / "batch_example.json", "batch_example.json"),
    (ROOT / "screenaudit" / "screenaudit_result.json", "screenaudit_result.json"),
]

# (what the served frontend says, what the static build says instead). Every one is asserted.
HTML_PATCHES = [
    # The agent layer runs on the visitor's own API key, so the page states where that key may
    # be sent and then has the browser enforce it: connect-src allows this origin and Anthropic,
    # and nothing else. A promise in prose would be worth less than a header the browser applies.
    # 'unsafe-eval' is present because the TensorFlow.js runtime needs it; the restriction that
    # matters for a typed-in key is connect-src.
    #
    # The served frontend loads its two typefaces from Google, which would tell Google the IP
    # of everyone who opens the page. Both are openly licensed, so the build fetches them once
    # and serves them from this origin instead: the policy above then allows no outside host at
    # all until the visitor asks for an agent diagnosis.
    (
        '<link rel="preconnect" href="https://fonts.googleapis.com">\n'
        '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>\n'
        '<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600'
        '&family=Space+Grotesk:wght@400;500;600;700&display=swap" rel="stylesheet">',
        '<meta http-equiv="Content-Security-Policy" content="'
        "default-src 'none'; "
        "script-src 'self' 'unsafe-eval'; "
        "style-src 'self' 'unsafe-inline'; "
        "font-src 'self'; "
        "img-src 'self' data:; "
        "connect-src 'self' https://api.anthropic.com; "
        "base-uri 'none'; form-action 'none'\">\n"
        '<link rel="stylesheet" href="fonts.css?v=%(v)s">',
    ),
    (
        '<link rel="stylesheet" href="/styles.css?v=20260804a">',
        '<link rel="stylesheet" href="styles.css?v=%(v)s">\n'
        '<link rel="stylesheet" href="boot.css?v=%(v)s">',
    ),
    (
        '<script src="/app.js?v=20260804a"></script>',
        '<script src="vendor/tf.min.js"></script>\n'
        '<script src="agents.js?v=%(v)s"></script>\n'
        '<script src="engine.js?v=%(v)s"></script>\n'
        '<script src="boot.js?v=%(v)s"></script>\n'
        '<script src="app.js?v=%(v)s"></script>',
    ),
    (
        '<span class="lbl">frozen · online</span>',
        '<span class="lbl">frozen · in this tab</span>',
    ),
    (
        "        <div>DHS64-MPRA activity</div>",
        "        <div>DHS64-MPRA activity</div>\n        <div>scored on your machine</div>",
    ),
    (
        '<a href="https://belumume.github.io/cisfalcon/" target="_blank" rel="noopener">live tool · belumume.github.io/cisfalcon',
        '<a href="https://zenodo.org/records/17410822" target="_blank" rel="noopener">model weights · Zenodo 17410822',
    ),
    (
        '              <div class="fine">MIT licensed. The predictor is a public, already-released model.</div>',
        '              <div class="fine">MIT licensed. The predictor is a public, already-released '
        "model, and it runs here in your browser: the three fold models are downloaded once and "
        "every score on this page is computed on your own machine. The sequence you paste never "
        "leaves this tab. If you ask for the agent diagnosis, what goes to Anthropic is the "
        "predicted numbers and the names of the motifs found, on a key you enter here and that is "
        "billed to you.</div>",
    ),
    (
        "A measured ablation shows the agents do not improve classification over the gate; their value is the redesign guidance.</div>",
        "A measured ablation shows the agents do not improve classification over the gate; their "
        "value is the redesign guidance. This page has no server, so the four agents run from your "
        "browser on an Anthropic key you paste in: it stays in the tab, goes only to Anthropic, "
        "bills your account a few cents per design, and the exact cost is shown afterwards. "
        "Everything else here, the gate, the motif scan and the deterministic fix loop, needs no "
        "key at all.</div>",
    ),
]

APP_JS_OLD = """const api = (p, body) =>
  fetch("/api" + p, body
    ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }
    : undefined)
    .then(async (r) => { const j = await r.json().catch(() => ({})); if (!r.ok) throw new Error(j.detail || r.statusText); return j; });"""

APP_JS_NEW = """/* The same endpoint paths this frontend has always called, served by the in-browser engine
   (engine.js) instead of a server: the fold models run in this tab, so there is nothing to
   deploy, nothing to pay for, and no sequence leaves the machine. */
const api = (p, body) => window.CF.ready.then(() => window.CF.api(p, body));"""

# The served frontend explains an absent agent layer as "not configured on this instance", which
# is the server's situation, not this one: here the layer is one key away and the visitor holds
# the key. Say that instead, and show the reason the engine actually gave.
FALLBACK_OLD = (
    '`<div class="diag-fallback">Claude agents are not configured on this instance, so this '
    "shows the deterministic rule verdict. The full multi-agent path (3 Sonnet lenses + Opus "
    'adjudicator) runs when the API key is present.</div>`'
)
FALLBACK_NEW = (
    '`<div class="diag-fallback">${out.agents_note ? esc(out.agents_note) : "This shows the '
    'deterministic rule verdict."} This page has no server, so the four-agent path (3 Sonnet 5 '
    "lenses in parallel, Opus 4.8 adjudicator) runs on an Anthropic key you enter in this tab: "
    "a few cents, billed to you, sent only to Anthropic.</div>`"
)

# When a check fails here there is no API to be unreachable and no backend to be down: the
# failure is in this tab, and the reason the engine gave is the only useful thing to show.
SCORE_ERR_OLD = (
    '`<div class="empty" style="padding:24px 10px">could not reach the scoring API<br>'
    '<span class="dim">${esc(e.message)}</span></div>`'
)
SCORE_ERR_NEW = (
    '`<div class="empty" style="padding:24px 10px">the scoring engine in this tab failed<br>'
    '<span class="dim">${esc(e.message)}</span></div>`'
)
BACKEND_ERR_OLD = (
    '`<div class="insp-empty"><div>the verifier needs the live backend</div>'
    '<div class="dim">${esc(e.message)}</div></div>`'
)
BACKEND_ERR_NEW = (
    '`<div class="insp-empty"><div>the model did not finish loading in this tab</div>'
    '<div class="dim">${esc(e.message)}</div></div>`'
)

APP_JS_PATCHES = [
    (APP_JS_OLD, APP_JS_NEW),
    (FALLBACK_OLD, FALLBACK_NEW),
    (SCORE_ERR_OLD, SCORE_ERR_NEW),
    (BACKEND_ERR_OLD, BACKEND_ERR_NEW),
]


def _patch(text: str, pairs, where: str) -> str:
    for old, new in pairs:
        if old not in text:
            raise SystemExit(
                f"[FAIL] {where}: the frontend no longer contains a string this build patches:\n"
                f"       {old[:110]}\n"
                f"       The served frontend changed. Update HTML_PATCHES/APP_JS_OLD in "
                f"webdemo/build.py to match, then re-run."
            )
        text = text.replace(old, new % {"v": CACHE_BUST} if "%(v)s" in new else new, 1)
    return text


def sync_page() -> None:
    (HERE / "data").mkdir(exist_ok=True)
    (HERE / "jaspar").mkdir(exist_ok=True)

    shutil.copy2(STATIC / "styles.css", HERE / "styles.css")
    (HERE / "index.html").write_text(
        _patch((STATIC / "index.html").read_text(), HTML_PATCHES, "index.html")
    )
    (HERE / "app.js").write_text(
        _patch((STATIC / "app.js").read_text(), APP_JS_PATCHES, "app.js")
    )
    print("[sync]  index.html, app.js, styles.css from webapp/backend/static")

    n = 0
    for src in sorted((ROOT / "webapp" / "backend" / "jaspar_cache").glob("*.json")):
        shutil.copy2(src, HERE / "jaspar" / src.name)
        n += 1
    print(f"[sync]  {n} JASPAR matrices")

    for src, name in DATA_FILES:
        shutil.copy2(src, HERE / "data" / name)
    print(f"[sync]  {len(DATA_FILES)} data files")
    sync_fonts()
    write_calibration()


def sync_fonts() -> None:
    """Fetch the page's two typefaces once and serve them from this origin.

    Google's stylesheet is per-browser, so it is requested as a current desktop browser to get
    the woff2 faces, and only the latin and latin-ext subsets are kept: the page's text is
    English and its data is ACGT. The files are committed, so a build with no network reuses
    them and the published page depends on nobody.
    """
    import urllib.request

    out = HERE / "fonts"
    out.mkdir(exist_ok=True)
    req = urllib.request.Request(
        GOOGLE_FONTS,
        headers={
            # Google serves woff2 only to browsers it recognises; a generic client gets ttf.
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            )
        },
    )
    try:
        css = urllib.request.urlopen(req, timeout=60).read().decode()
    except OSError as e:
        # The faces and the stylesheet are committed, so a build with no network is still a
        # correct build; only a change to GOOGLE_FONTS would need the fetch to succeed.
        css_path = HERE / "fonts.css"
        if css_path.exists():
            refs = set(re.findall(r"url\(fonts/([^)]+)\)", css_path.read_text()))
            if refs and all((out / r).exists() for r in refs):
                print(f"[sync]  {len(refs)} font files, reusing the committed copies ({e})")
                return
        raise SystemExit(f"[FAIL] could not fetch the fonts and none are committed: {e}")

    parsed, subset = [], None
    for block in re.split(r"(?=/\* )", css):
        m = re.match(r"/\* ([a-z-]+) \*/", block.strip())
        if m:
            subset = m.group(1)
        if "@font-face" not in block or subset not in FONT_SUBSETS:
            continue
        fam = re.search(r"font-family: '([^']+)'", block).group(1)
        wt = re.search(r"font-weight: (\d+)", block).group(1)
        url = re.search(r"url\((https://[^)]+\.woff2)\)", block).group(1)
        parsed.append((fam, wt, subset, url, block))

    # Space Grotesk is a variable font: Google points all four weights at one file per subset
    # and the browser picks the weight off its axis. Store each distinct file once, named for
    # what it is, rather than four identical copies named as if they were four weights.
    uses = {}
    for _, _, _, url, _ in parsed:
        uses[url] = uses.get(url, 0) + 1
    faces, keep = [], set()
    for fam, wt, sub, url, block in parsed:
        slug = fam.lower().replace(" ", "-")
        name = f"{slug}-{sub}.woff2" if uses[url] > 1 else f"{slug}-{wt}-{sub}.woff2"
        keep.add(name)
        if not (out / name).exists():
            (out / name).write_bytes(urllib.request.urlopen(url, timeout=60).read())
        faces.append(block.replace(url, f"fonts/{name}").strip())
    for stale in out.glob("*.woff2"):
        if stale.name not in keep:
            stale.unlink()

    want = 7 * len(FONT_SUBSETS)
    if len(faces) != want:
        raise SystemExit(
            f"[FAIL] expected {want} font faces (7 weights x {len(FONT_SUBSETS)} subsets), got "
            f"{len(faces)}. Google's stylesheet changed; check GOOGLE_FONTS in webdemo/build.py."
        )
    (HERE / "fonts.css").write_text(
        "/* IBM Plex Mono and Space Grotesk, SIL Open Font License 1.1, served from this origin\n"
        "   so that opening the page tells no one. Generated by webdemo/build.py. */\n"
        + "\n".join(faces)
        + "\n"
    )
    print(f"[sync]  {len(faces)} font faces, served locally")


def write_calibration() -> None:
    """Export the isotonic failure calibration as its own fitted knots.

    The page interpolates between these and clips outside them, which is exactly what
    scikit-learn's predict() does, so the browser reproduces the server's failure probability
    without shipping scikit-learn or re-fitting anything in JavaScript.
    """
    sys.path.insert(0, str(ROOT))
    import verifier

    calib = verifier.Calibration()
    if calib.iso is None:
        raise SystemExit(
            "[FAIL] the isotonic calibration did not fit (scikit-learn missing, or "
            "data/calibration.csv absent). The page would silently fall back to the documented "
            "sigmoid, which is not what the server served."
        )
    out = HERE / "data" / "calibration_iso.json"
    out.write_text(
        json.dumps(
            {
                "x": [float(v) for v in calib.iso.f_.x],
                "y": [float(v) for v in calib.iso.f_.y],
                "base": calib.base,
            }
        )
    )
    print(f"[sync]  calibration: {len(calib.iso.f_.x)} isotonic knots")


def convert_models() -> int:
    sys.path.insert(0, str(ROOT))
    import fetch_models

    # fetch only the activity head; the accessibility trio is not used in the browser
    fetch_models.MODELS = [m for m in fetch_models.MODELS if "mpra" in m[0]]
    if fetch_models.main() != 0:
        return 1

    if not shutil.which("tensorflowjs_converter"):
        print(
            "[FAIL] tensorflowjs_converter is not on PATH; see the header of this file for the "
            "virtualenv to install it in.",
            file=sys.stderr,
        )
        return 1

    out = HERE / "models"
    out.mkdir(parents=True, exist_ok=True)
    for k in FOLDS:
        src = ROOT / "models" / f"dhs64_mpra_split{k}.h5"
        dst = out / f"split{k}"
        if dst.exists():
            shutil.rmtree(dst)
        print(f"[conv]  {src.name} -> webdemo/models/split{k}")
        env = dict(os.environ, TF_CPP_MIN_LOG_LEVEL="3")
        r = subprocess.run(
            [
                "tensorflowjs_converter",
                "--input_format=keras",
                "--quantize_float16=*",
                str(src),
                str(dst),
            ],
            env=env,
        )
        if r.returncode != 0:
            print(f"[FAIL] conversion of {src.name} failed", file=sys.stderr)
            return 1

    total = sum(p.stat().st_size for p in out.rglob("*") if p.is_file())
    print(f"[conv]  {total / 1e6:.0f} MB of float16 weights in webdemo/models")
    return 0


def main() -> int:
    sync_page()
    if "--no-models" not in sys.argv:
        if convert_models() != 0:
            return 1
    print("\nbundle ready. Next: node webdemo/parity.test.mjs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
