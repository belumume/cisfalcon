"""Re-capture docs/hero_overview.png from the LIVE corrected page.

The hero is a screenshot, so a stale hero is fixed by redeploying and re-shooting rather than
by editing pixels. It rendered the disowned pooled 70% for as long as the deployed page did.

Viewport matches the existing asset (1440x787) so the README's layout does not shift.
Verifies afterwards that the corrected figures are present and the disowned ones are gone,
because a screenshot that silently captured the wrong scroll position or a pre-hydration
frame looks fine and asserts nothing.
"""

import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

URL = "https://cisfalcon-lifesci.fly.dev/"
OUT = Path(__file__).resolve().parent / "hero_overview.png"
W, H = 1440, 787

# Scoped to what the OVERVIEW tab actually shows. The conditioned enrichment (2.59x) lives on
# the Batch triage tab, so requiring it here refused a correct page. Verified by probing the
# live DOM: 2.59 and 7.74 are in the HTML but not in Overview's visible text.
MUST_APPEAR = ["41%", "6.29"]
# The disowned bare headline must be gone. 70% may still appear, but only labelled as the
# pooled basis, which the adjacent 41% card states explicitly.
MUST_BE_ABSENT = ["70% FEWER", "7.8x"]

with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width": W, "height": H}, device_scale_factor=1)
    pg.goto(URL, wait_until="networkidle", timeout=60_000)
    pg.wait_for_timeout(1500)

    text = pg.inner_text("body")
    missing = [s for s in MUST_APPEAR if s not in text]
    if missing:
        print(f"REFUSING to capture: live page lacks {missing}", file=sys.stderr)
        b.close()
        raise SystemExit(1)
    stale = [s for s in MUST_BE_ABSENT if s in text]
    if stale:
        print(
            f"REFUSING to capture: disowned headline still present {stale}",
            file=sys.stderr,
        )
        b.close()
        raise SystemExit(1)

    pg.screenshot(path=str(OUT), clip={"x": 0, "y": 0, "width": W, "height": H})
    b.close()

print(f"wrote {OUT} ({OUT.stat().st_size} bytes)")
