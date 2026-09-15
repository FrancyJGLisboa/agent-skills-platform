#!/usr/bin/env python3
"""Agent-run reliability for the marketplace: run Caliper per declared platform, certify what passes.

The operator agent calls `team_marketplace.py reliability`; this module does the work
without touching the manifest. For every declared platform that Caliper supports and
whose CLI is installed, it runs the skill's `evals/caliper/*.eval.yaml`, binds the run to
the skill with `caliper_evidence.py`, and returns certification evidence for the driver
to persist. Platforms Caliper cannot drive (GitHub Copilot and the rest) are reported as
skipped and keep the representative-run attestation as their evidence.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Sequence

from caliper_evidence import CaliperEvidenceError, Thresholds, build_evidence, load_result, prune_result
from platforms import normalize_platform_name

# Platform id -> the agent CLI Caliper drives for it. Caliper's backend ids equal these
# platform ids, which is what lets `--model <platform>` and `certify --platform` agree.
CALIPER_BACKENDS: dict[str, str] = {"claude-code": "claude", "codex": "codex"}
# Cross-vendor judging by preference; falls back to the backend judging itself.
JUDGE_PREFERENCE: dict[str, str] = {"claude-code": "codex", "codex": "claude-code"}
DEFAULT_K = 3
DEFAULT_TIMEOUT = 180

Which = Callable[[str], "str | None"]
Runner = Callable[..., "subprocess.CompletedProcess[str]"]


class ReliabilityError(ValueError):
    """Reliability evidence could not be produced for policy or environment reasons."""


def find_spec(skill_dir: Path) -> Path | None:
    """The skill's Caliper spec, if it ships one."""
    specs = sorted((skill_dir / "evals" / "caliper").glob("*.eval.yaml"))
    return specs[0] if specs else None


def select_platforms(
    declared: Sequence[str], requested: Sequence[str] | None = None, *, which: Which | None = None,
) -> list[dict[str, str]]:
    """Decide, per declared platform, whether Caliper can measure it on this machine."""
    # Resolved at call time so tests (and monkeypatches) can replace shutil.which.
    which = which or shutil.which
    wanted = {normalize_platform_name(item) for item in (requested or declared)}
    rows: list[dict[str, str]] = []
    for platform in sorted({normalize_platform_name(item) for item in declared}):
        if platform not in wanted:
            continue
        cli = CALIPER_BACKENDS.get(platform)
        if cli is None:
            rows.append({"platform": platform, "status": "skipped", "reason": "no Caliper backend; attestation evidence applies"})
        elif which(cli) is None:
            rows.append({"platform": platform, "status": "skipped", "reason": f"agent CLI '{cli}' is not installed"})
        else:
            rows.append({"platform": platform, "status": "run", "reason": ""})
    unknown = wanted - {normalize_platform_name(item) for item in declared}
    if unknown:
        raise ReliabilityError("platform(s) not declared by the skill: " + ", ".join(sorted(unknown)))
    return rows


def judge_for(platform: str, *, which: Which | None = None) -> str:
    """Prefer the other vendor as judge; use the backend itself when that CLI is absent."""
    which = which or shutil.which
    preferred = JUDGE_PREFERENCE.get(platform, platform)
    cli = CALIPER_BACKENDS.get(preferred)
    return preferred if cli and which(cli) else platform


def caliper_command(
    caliper: str, spec: Path, *, backend: str, judge: str, k: int, timeout: int, output: Path,
) -> list[str]:
    # --workers 1: attempts of one task otherwise run in parallel and specs use fixed work paths.
    return [
        caliper, "run", str(spec), "--k", str(k), "--workers", "1", "--timeout", str(timeout),
        "--model", backend, "--judge-model", judge, "--output", str(output),
    ]


def run_reliability(
    skill_dir: Path, declared: Sequence[str], *, results_dir: Path, platforms: Sequence[str] | None = None,
    k: int = DEFAULT_K, timeout: int = DEFAULT_TIMEOUT, thresholds: Thresholds = Thresholds(),
    skill_version: str | None = None, which: Which | None = None, runner: Runner | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Run Caliper for each measurable platform and return per-platform evidence or the reason there is none."""
    which = which or shutil.which
    runner = runner or subprocess.run
    spec = find_spec(skill_dir)
    if spec is None:
        raise ReliabilityError(f"{skill_dir.name} ships no evals/caliper/*.eval.yaml; nothing to measure")
    caliper = which("caliper")
    rows = select_platforms(declared, platforms, which=which)
    if any(row["status"] == "run" for row in rows) and caliper is None:
        raise ReliabilityError("caliper is not installed (uv tool install caliper-eval==0.11.0)")
    stamp = (now or datetime.now(timezone.utc)).astimezone(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
    results_dir.mkdir(parents=True, exist_ok=True)
    report: dict[str, Any] = {
        "skill": skill_dir.name, "spec": str(spec), "k": k, "timeout": timeout, "platforms": [],
    }
    for row in rows:
        if row["status"] != "run":
            report["platforms"].append(row)
            continue
        platform = row["platform"]
        judge = judge_for(platform, which=which)
        output = results_dir / f"{skill_dir.name}-{platform}-{stamp}.json"
        command = caliper_command(str(caliper), spec, backend=platform, judge=judge, k=k, timeout=timeout, output=output)
        completed = runner(command, capture_output=True, text=True, cwd=str(skill_dir))
        entry: dict[str, Any] = {"platform": platform, "judge": judge, "run": str(output)}
        if not output.is_file():
            tail = (completed.stderr or completed.stdout or "").strip().splitlines()[-3:]
            entry.update({"status": "failed", "reason": f"caliper exited {completed.returncode} without a result: " + " | ".join(tail)})
            report["platforms"].append(entry)
            continue
        try:
            result = load_result(output)
            evidence = build_evidence(
                result, skill_dir=skill_dir, platform=platform, skill_version=skill_version, thresholds=thresholds,
            )
        except CaliperEvidenceError as exc:
            entry.update({"status": "refused", "reason": str(exc)})
        else:
            pruned = output.with_name(output.stem + ".pruned.json")
            pruned.write_text(_dumps(prune_result(result)), encoding="utf-8")
            entry.update({"status": "certifiable", "reason": "", "evidence": evidence, "pruned_run": str(pruned)})
        report["platforms"].append(entry)
    return report


def _dumps(data: Any) -> str:
    return json.dumps(data, indent=2, sort_keys=True) + "\n"


def reliability_check_failures(entry: dict[str, Any]) -> list[str]:
    """Release-time policy: every Caliper-capable certified platform must carry Caliper checks."""
    failures: list[str] = []
    certified = entry.get("compatibility", {}).get("certified", [])
    for record in certified:
        if not isinstance(record, dict):
            continue
        platform = normalize_platform_name(str(record.get("platform", "")))
        if platform not in CALIPER_BACKENDS:
            continue
        checks = record.get("checks", [])
        if not any(isinstance(name, str) and name.startswith("caliper:") for name in checks):
            failures.append(f"{platform} certification carries no agent-run (caliper:*) checks")
    return failures
