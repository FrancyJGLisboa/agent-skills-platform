#!/usr/bin/env python3
"""Generate a durable ``VERIFICATION.md`` from a skill's real quality evidence.

Run this after the representative or live run:

    python3 scripts/generate_verification.py path/to/skill --run-kind live \
      --environment codex
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from skill_document import SkillDoc

ROOT = Path(__file__).resolve().parent
STATE_PREFIX = "<!-- agent-skill-verification: "


def content_fingerprint(skill_dir: Path) -> str:
    """Hash the behavior-defining files a verification report covers."""
    files = [skill_dir / "SKILL.md"]
    for directory in (skill_dir / "scripts", skill_dir / "evals"):
        if directory.is_dir():
            files.extend(
                path for path in directory.rglob("*")
                if path.is_file() and "__pycache__" not in path.parts
                # Tool caches such as Caliper's `.caliper/results/` sit beside a spec
                # and change on every run; they are not behavior-defining files.
                and not any(part.startswith(".") for part in path.relative_to(skill_dir).parts)
            )
    digest = hashlib.sha256()
    for path in sorted(files):
        relative = path.relative_to(skill_dir).as_posix()
        digest.update(relative.encode("utf-8") + b"\0" + path.read_bytes() + b"\0")
    return digest.hexdigest()


def _commit(skill_dir: Path) -> str:
    result = subprocess.run(["git", "-C", str(skill_dir), "rev-parse", "HEAD"], text=True, capture_output=True, check=False)
    return result.stdout.strip() if result.returncode == 0 else "uncommitted"


def _is_report_only_followup(skill_dir: Path, recorded_commit: object) -> bool:
    """Return whether the only change since evidence was recorded is its report.

    A report necessarily records the commit that existed immediately before the
    report itself was committed.  Accept that one-file follow-up while refusing
    a commit mismatch whenever any behavior-defining file also changed.
    """
    if not isinstance(recorded_commit, str) or not recorded_commit:
        return False
    current_commit = _commit(skill_dir)
    if current_commit == "uncommitted":
        return recorded_commit == "uncommitted"
    if recorded_commit == "uncommitted":
        return False
    if recorded_commit == current_commit:
        return True
    result = subprocess.run(
        ["git", "-C", str(skill_dir), "diff", "--name-only", "--relative", f"{recorded_commit}..{current_commit}", "--", "."],
        text=True,
        capture_output=True,
        check=False,
    )
    changed = {line.replace("\\", "/") for line in result.stdout.splitlines() if line.strip()}
    return result.returncode == 0 and changed == {"VERIFICATION.md"}


def verification_errors(skill_dir: Path) -> list[str]:
    """Return missing, stale, or failed-evidence reasons for marketplace gates."""
    path = skill_dir / "VERIFICATION.md"
    if not path.is_file():
        return ["VERIFICATION.md is missing"]
    marker = next((line for line in path.read_text(encoding="utf-8").splitlines() if line.startswith(STATE_PREFIX)), "")
    if not marker.endswith(" -->"):
        return ["VERIFICATION.md has no machine-readable evidence state"]
    try:
        state = json.loads(marker[len(STATE_PREFIX):-4])
    except json.JSONDecodeError:
        return ["VERIFICATION.md has malformed evidence state"]
    version = SkillDoc.from_path(skill_dir / "SKILL.md").metadata.get("version", "")
    errors: list[str] = []
    if state.get("version") != version:
        errors.append("verification version does not match SKILL.md")
    if state.get("fingerprint") != content_fingerprint(skill_dir):
        errors.append("verification is stale: SKILL.md, scripts, or evals changed")
    if not _is_report_only_followup(skill_dir, state.get("commit")):
        errors.append("verification commit does not match current Git commit")
    if not state.get("clean"):
        errors.append("verification records failed gates or evals")
    return errors


def _run(command: list[str]) -> dict:
    """Run one gate without leaking its output into the generated report."""
    result = subprocess.run(command, text=True, capture_output=True, check=False)
    return {"passed": result.returncode == 0, "stdout": result.stdout, "stderr": result.stderr}


def _eval_summary(skill_dir: Path, rollout: bool) -> dict:
    """Run the generated eval runner and normalize its machine-readable summary."""
    command = [sys.executable, str(skill_dir / "scripts" / "run_evals.py"), str(skill_dir), "--json"]
    if rollout:
        command.append("--rollout")
    result = _run(command)
    try:
        payload = json.loads(result["stdout"])
    except json.JSONDecodeError:
        payload = {}
    return {
        "passed": int(payload.get("passed", 0)),
        "failed": int(payload.get("failed", 0)),
        "errors": int(payload.get("errors", 0)),
        "regressions": int(payload.get("regressions", 0)),
        "clean": result["passed"],
    }


def render_report(skill_dir: Path, gates: dict[str, bool], evals: dict, run_kind: str, environments: list[str]) -> str:
    """Render a compact, evidence-only Markdown report."""
    name = skill_dir.name
    completed = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    gate_lines = "\n".join(f"- {'PASS' if passed else 'FAIL'} — {label}" for label, passed in gates.items())
    environments_text = ", ".join(environments) if environments else "not recorded"
    state = {"version": SkillDoc.from_path(skill_dir / "SKILL.md").metadata.get("version", ""), "commit": _commit(skill_dir), "fingerprint": content_fingerprint(skill_dir), "clean": all(gates.values()) and evals["clean"]}
    return f"""# Verification: {name}

{STATE_PREFIX}{json.dumps(state, sort_keys=True)} -->

Generated: {completed}

## Release evidence

- Run type: {run_kind}
- Recorded execution environments: {environments_text}
- Cross-environment compatibility: not established by this report
- Eval rollout: {evals['passed']} passed, {evals['failed']} failed, {evals['errors']} errored, {evals['regressions']} regressed

## Gates

{gate_lines}

## Interpretation

This report records only the checks completed at generation time. It does not prove
future live data, model output, other agent runtimes, or production user outcomes.
Run `python3 scripts/evolve.py` after a correction or material dependency change.
"""


def ensure_readme_link(skill_dir: Path) -> bool:
    """Add a stable verification link to a generated skill's README once."""
    readme = skill_dir / "README.md"
    if not readme.is_file():
        return False
    content = readme.read_text(encoding="utf-8")
    marker = "[VERIFICATION.md](VERIFICATION.md)"
    if marker in content:
        return False
    section = (
        "\n\n## Verification\n\n"
        "[VERIFICATION.md](VERIFICATION.md) records the latest generation-time "
        "gate and eval evidence.\n"
    )
    readme.write_text(content.rstrip() + section, encoding="utf-8")
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate VERIFICATION.md from actual skill checks.")
    parser.add_argument("skill_dir", help="Skill directory to verify.")
    parser.add_argument("--run-kind", choices=("representative", "live"), default="representative")
    parser.add_argument("--environment", action="append", default=[], help="Installed environment; repeatable.")
    parser.add_argument("--no-rollout", action="store_true", help="Use static eval checks instead of an end-to-end rollout.")
    parser.add_argument("--output", default="VERIFICATION.md", help="Report path relative to the skill directory.")
    args = parser.parse_args(argv)

    skill_dir = Path(args.skill_dir).resolve()
    if not (skill_dir / "SKILL.md").is_file():
        print(f"ERROR: SKILL.md not found in {skill_dir}", file=sys.stderr)
        return 2
    gates = {
        "specification": _run([sys.executable, str(ROOT / "validate.py"), str(skill_dir)])["passed"],
        "security": _run([sys.executable, str(ROOT / "security_scan.py"), str(skill_dir)])["passed"],
        "skill graph": _run([sys.executable, str(ROOT / "skill_graph.py"), "run", str(skill_dir), "--jobs", "4"])["passed"],
    }
    evals = _eval_summary(skill_dir, rollout=not args.no_rollout)
    clean = all(gates.values()) and evals["clean"]
    output = skill_dir / args.output
    output.write_text(render_report(skill_dir, gates, evals, args.run_kind, args.environment), encoding="utf-8")
    ensure_readme_link(skill_dir)
    print(output)
    return 0 if clean else 1


if __name__ == "__main__":
    raise SystemExit(main())
