"""Fail if a POOLED headline figure appears without its conditioning nearby.

WHY THIS EXISTS. The same defect shipped twice in this repo. First the public headline quoted a
pooled 70% failure reduction while the AUROC beside it was properly conditioned. Then, after that
was corrected everywhere a reader would READ, `reproduce_flagship.py` was still PRINTING the pooled
70% and 7.74x under the label "These are the deployment numbers", conditioning only the AUROC. Two
independent blind audits passed over the second one because both read the repo and neither ran it.

Conditioning does not propagate. Every derived number carries its own or it carries none.

THE RULE ENFORCED: wherever a pooled figure appears, at least one conditioning token must appear
within WINDOW lines of it. That is deliberately mechanical. It cannot judge whether the framing is
honest; it can only guarantee the reader is never shown a pooled number with no conditioning in
sight, which is the specific way this defect reached the public surface twice.

Exit 0 clean, 1 on violations, 2 if the check cannot run.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

WINDOW = 12

# Pooled figures, NARROWED after measuring against the real repo. The first draft also matched
# 6.29% and 1.91% and fired 14 times, mostly wrongly: those two are BASE RATES, a property of the
# dataset rather than a pooled-vs-conditioned claim, so demanding conditioning beside them is
# incoherent. A bare "70%" was likewise matching an unrelated benchmark's failure rate. So the
# enrichment figures stand alone (they are only ever this claim), while 70% must appear in a
# triage-claim context on its own line to count.
ENRICHMENT = re.compile(r"\b7\.7[0-9]x|\b7\.8x")  # only ever this claim; stands alone
SEVENTY = re.compile(r"\b70%")
# 70% is only the pooled triage claim when the line frames it as a REDUCTION. "roughly 70% failed"
# is a different benchmark's rate and matching it was a false positive in the first draft; keying
# on the word "fail" alone could not tell the two apart.
REDUCTION_CTX = re.compile(r"\b(?:fewer|reduc|cuts?|drops?|unranked|safest)", re.I)

# Any one of these within WINDOW lines discharges the obligation.
CONDITIONED = re.compile(
    r"\b(?:41%|2\.59x?|91%|pooled|POOLED|macro|conditioned|stratum|within[- ]\(?cell)",
    re.I,
)

# .ipynb earns its place the hard way: the first version of this check omitted it, and the
# README's most prominent reproduce path is a notebook that printed the pooled figures with no
# conditioning at all. A gate whose scope is narrower than the surface it claims reports clean
# about the part it never read. Notebooks are JSON, so a text scan reaches their source strings.
SCAN_SUFFIXES = {".md", ".py", ".html", ".js", ".json", ".txt", ".ipynb"}

# Exemptions, each with its reason. Keep this list short: an exemption whose condition the check
# cannot itself evaluate would make the gate unfalsifiable, so every entry here is a whole file
# that is frozen or historical by construction, never a judgement call about wording.
EXEMPT = {
    "PREREG-ERRATA.md",  # documents the superseded wording on purpose; quoting it is the point
    "PREREG.md",  # frozen and hash-locked. Editing it to satisfy a linter would break the hash
    #                and destroy the only thing a pre-registration is for.
}
# Directories that are dated records of what was true then, not claims made now.
EXEMPT_DIRS = ("build-readiness/",)


def tracked_files(repo: Path) -> list[Path]:
    out = subprocess.run(
        ["git", "ls-files"],
        cwd=repo,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if out.returncode != 0:
        print(f"FATAL: git ls-files failed: {out.stderr.strip()}", file=sys.stderr)
        raise SystemExit(2)
    files = []
    for line in out.stdout.splitlines():
        if any(line.startswith(d) for d in EXEMPT_DIRS):
            continue
        p = repo / line
        if p.suffix.lower() in SCAN_SUFFIXES and p.name not in EXEMPT and p.is_file():
            files.append(p)
    return files


def is_pooled_claim(line: str) -> bool:
    if ENRICHMENT.search(line):
        return True
    return bool(SEVENTY.search(line) and REDUCTION_CTX.search(line))


def violations_in(text: str) -> list[tuple[int, str]]:
    lines = text.splitlines()
    bad = []
    for i, line in enumerate(lines):
        if not is_pooled_claim(line):
            continue
        lo = max(0, i - WINDOW)
        hi = min(len(lines), i + WINDOW + 1)
        if CONDITIONED.search("\n".join(lines[lo:hi])):
            continue
        bad.append((i + 1, line.strip()))
    return bad


MUST_FIRE = [
    (
        "bare reduction claim",
        "The model cuts failures by 70% on a mixed batch.\nShip it.",
    ),
    (
        "the printed framing",
        "  reduction vs unranked : 70%\n  These are the deployment numbers.",
    ),
    ("bare enrichment", "The riskiest 2% are enriched 7.74x for real failures."),
]

MUST_NOT_FIRE = [
    ("conditioned nearby", "cuts failures by 70% pooled.\nConditioned macro is 41%."),
    # OVER-CORRECTION CONTROLS. Each shares vocabulary with a must-fire case and differs only in
    # the discriminating feature. Without them, narrowing the pattern to kill a false positive is
    # indistinguishable from having disabled the detector for the whole topic.
    (
        "base rate, not a pooled claim",
        "Measured at the real 6.29% cross-lab base rate.",
    ),
    ("safest-half rate, not a reduction", "failure rate in what you make: 1.91%"),
    (
        "a different benchmark's rate",
        "roughly 70% failed. The 682 is that benchmark's count.",
    ),
]


def self_test() -> None:
    """The check refuses to report until it proves it discriminates, in BOTH directions."""
    for label, text in MUST_FIRE:
        if not violations_in(text):
            print(
                f"FATAL self-test: must-fire case NOT flagged -> {label}",
                file=sys.stderr,
            )
            raise SystemExit(2)
    for label, text in MUST_NOT_FIRE:
        if violations_in(text):
            print(
                f"FATAL self-test: must-NOT-fire case WAS flagged -> {label}",
                file=sys.stderr,
            )
            raise SystemExit(2)
    print(
        f"self-test ok: {len(MUST_FIRE)} must-fire, {len(MUST_NOT_FIRE)} must-not-fire"
    )


def main() -> int:
    self_test()
    repo = Path(__file__).resolve().parent
    if not (repo / ".git").exists():
        repo = Path.cwd()
    total = 0
    for f in tracked_files(repo):
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for lineno, line in violations_in(text):
            rel = f.relative_to(repo).as_posix()
            print(
                f"{rel}:{lineno}: pooled figure with no conditioning within {WINDOW} lines"
            )
            print(f"    {line[:150]}")
            total += 1
    if total:
        print(
            f"\n{total} unconditioned pooled figure(s). Each needs its basis stated nearby."
        )
        return 1
    print(f"clean: every pooled figure has conditioning within {WINDOW} lines")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
