#!/usr/bin/env python3
"""Fail CI when changed skill packages lack current verification evidence."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from generate_verification import verification_errors

REGENERATE = "regenerate with python3 scripts/generate_verification.py {skill}"
REPAIRS = {
    "VERIFICATION.md is missing": REGENERATE,
    "VERIFICATION.md has no machine-readable evidence state": REGENERATE,
    "VERIFICATION.md has malformed evidence state": REGENERATE,
    "verification version does not match SKILL.md": REGENERATE,
    "verification is stale": REGENERATE,
    "verification commit does not match": REGENERATE,
    "verification records failed gates or evals": (
        "fix the failing gate or eval first with "
        "python3 scripts/skill_graph.py run {skill}, then regenerate"
    ),
}
SEQUENCE = """
A report binds to the commit it records, so landing a skill change takes
three steps in this order:

  1. Commit the behavior change. Include the "## Verification" link that
     generate_verification.py appends to README.md -- it must land here,
     not in step 3.
  2. python3 scripts/generate_verification.py <skill-dir>
  3. Commit VERIFICATION.md on its own. The gate accepts a follow-up commit
     whose diff within the skill is exactly {VERIFICATION.md}, so a combined
     commit is rejected even when the evidence itself is current.
"""


def repair_for(error: str, skill: str) -> str:
    """Return the repair line for one verification error."""
    for prefix, repair in REPAIRS.items():
        if error.startswith(prefix):
            return repair.format(skill=skill)
    return REGENERATE.format(skill=skill)


def changed_skill_dirs(base: str, head: str = "HEAD") -> list[Path]:
    """Return unique skill roots affected between two Git revisions."""
    result = subprocess.run(["git", "diff", "--name-only", f"{base}..{head}"], text=True, capture_output=True, check=False)
    if result.returncode:
        raise ValueError(f"cannot diff {base}..{head}")
    roots: set[Path] = set()
    for raw in result.stdout.splitlines():
        path = Path(raw)
        for parent in (path.parent, *path.parents):
            if parent == Path("."):
                break
            if (parent / "SKILL.md").is_file():
                roots.add(parent)
                break
    return sorted(roots)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check verification evidence for changed skills.")
    parser.add_argument("--base", required=True, help="Base Git revision to compare with HEAD.")
    args = parser.parse_args(argv)
    try:
        skills = changed_skill_dirs(args.base)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    failures: list[str] = []
    for skill in skills:
        errors = verification_errors(skill)
        if errors:
            failures.extend(f"- {skill}: {error}" for error in errors)
            # One repair usually covers every error on a skill; list each
            # distinct repair once rather than after every line.
            repairs = dict.fromkeys(repair_for(error, str(skill)) for error in errors)
            failures.extend(f"  repair: {repair}" for repair in repairs)
        else:
            print(f"PASS {skill}: verification evidence is current")
    if failures:
        print("Verification gate failed:", file=sys.stderr)
        print("\n".join(failures), file=sys.stderr)
        print(SEQUENCE, file=sys.stderr)
        return 1
    print(f"Verification gate passed for {len(skills)} changed skill(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
