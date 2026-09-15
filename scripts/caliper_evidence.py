#!/usr/bin/env python3
"""Turn a Caliper run into marketplace compatibility-certification evidence.

Caliper (https://github.com/edonadei/caliper) runs a real agent with a skill
installed in a fresh HOME, k attempts per task, and saves one JSON file per run.
The file-level evals shipped in every skill (`scripts/run_evals.py`) never run an
agent; a Caliper run is the only evidence that an agent discovers the skill and
follows it. This adapter binds such a run to the exact skill payload, enforces
reliability thresholds, and emits the evidence JSON that
`team_marketplace.py certify --evidence` already accepts.

    python3 scripts/caliper_evidence.py RESULT.json --skill DIR --evidence-out OUT.json

Metrics are recomputed from every attempt's `outcome`; stored aggregate fields
are cross-checked and a hand-edited file is refused. Stored certification
records keep only check names, so each name carries its threshold and the
observed value. Nothing here calls an agent or the network.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from marketplace_distribution import ADAPTER_VERSION, adapter_for
from platforms import normalize_platform_name
from skill_document import SkillDoc

SUPPORTED_ERAS = {"install-and-discover"}
USABLE_OUTCOMES = frozenset({"pass", "task_fail", "cheat"})
UNUSABLE_OUTCOMES = frozenset({"infra_error", "timeout", "judge_error"})
KNOWN_OUTCOMES = USABLE_OUTCOMES | UNUSABLE_OUTCOMES | {"not_checked"}
CHECK_PREFIX = "caliper"
_TOLERANCE = 1e-9


class CaliperEvidenceError(ValueError):
    """A Caliper result is malformed, unbound to the skill, or below threshold."""


@dataclass(frozen=True)
class Thresholds:
    """Minimum reliability a run must show before it may certify a platform."""

    min_success_rate: float = 0.9
    min_pass_hat_k: float = 0.7
    max_unusable: int = 1
    min_activation: float = 0.9
    min_ablation_delta: float = 0.2


def _mapping(value: object, where: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise CaliperEvidenceError(f"{where} must be a JSON object")
    return value


def _sequence(value: object, where: str) -> list[Any]:
    if not isinstance(value, list):
        raise CaliperEvidenceError(f"{where} must be a JSON array")
    return value


def load_result(path: Path) -> dict[str, Any]:
    """Load a Caliper run and check the top-level shape this adapter relies on."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise CaliperEvidenceError(f"cannot read Caliper result {path}: {exc}") from exc
    result = _mapping(data, "Caliper result")
    for key in ("run", "skill_snapshots", "task_results", "aggregate"):
        if key not in result:
            raise CaliperEvidenceError(f"Caliper result is missing '{key}'")
    run = _mapping(result["run"], "run")
    era = run.get("era")
    if era not in SUPPORTED_ERAS:
        raise CaliperEvidenceError(f"unsupported Caliper run era {era!r}; expected one of {sorted(SUPPORTED_ERAS)}")
    return dict(result)


def _close(stored: object, computed: float | None) -> bool:
    if stored is None or computed is None:
        return stored is None and computed is None
    return isinstance(stored, (int, float)) and abs(float(stored) - computed) <= _TOLERANCE


def summarize_task(task: Mapping[str, Any], k: int) -> dict[str, Any]:
    """Recompute one task's scoreboard from its attempts and cross-check stored fields."""
    name = str(task.get("task_name") or task.get("task_id") or "?")
    attempts = _sequence(task.get("attempts"), f"task {name!r} attempts")
    if len(attempts) != k:
        raise CaliperEvidenceError(f"task {name!r} has {len(attempts)} attempts; the run declares k={k}")
    outcomes: list[str] = []
    cheats = 0
    activation_usable = 0
    activation_successes = 0
    for attempt in attempts:
        record = _mapping(attempt, f"task {name!r} attempt")
        outcome = str(record.get("outcome"))
        if outcome not in KNOWN_OUTCOMES:
            raise CaliperEvidenceError(f"task {name!r} has unknown outcome {outcome!r}")
        outcomes.append(outcome)
        cheats += outcome == "cheat"
        # Activation is scored on every attempt that produced a transcript and asserted `activates:`.
        if outcome not in {"infra_error", "timeout"} and record.get("activation_passed") is not None:
            activation_usable += 1
            activation_successes += record["activation_passed"] is True
    successes = outcomes.count("pass")
    usable = sum(outcome in USABLE_OUTCOMES for outcome in outcomes)
    unusable = sum(outcome in UNUSABLE_OUTCOMES for outcome in outcomes)
    score = successes / usable if usable else None
    pass_hat_k = score**usable if score is not None else None
    activation_score = activation_successes / activation_usable if activation_usable else None
    for field, computed in (("score", score), ("pass_hat_k", pass_hat_k), ("activation_score", activation_score)):
        if field in task and not _close(task[field], computed):
            raise CaliperEvidenceError(
                f"task {name!r} stored {field}={task[field]!r} but attempts imply {computed!r}; refusing edited results"
            )
    if "unusable" in task and task["unusable"] != unusable:
        raise CaliperEvidenceError(f"task {name!r} stored unusable={task['unusable']!r} but attempts imply {unusable}")
    return {
        "name": name,
        "outcomes": outcomes,
        "successes": successes,
        "usable": usable,
        "unusable": unusable,
        "cheats": cheats,
        "score": score,
        "pass_hat_k": pass_hat_k,
        "activation_expected": task.get("activation_expected"),
        "activation_score": activation_score,
        "trigger_only": usable == 0 and unusable == 0,
    }


def summarize_run(result: Mapping[str, Any]) -> dict[str, Any]:
    """Recompute the run's scoreboards from attempt outcomes."""
    run = _mapping(result.get("run"), "run")
    k = run.get("k")
    if not isinstance(k, int) or k < 1:
        raise CaliperEvidenceError("run.k must be a positive integer")
    if run.get("interrupted") is True:
        raise CaliperEvidenceError("run was interrupted; an incomplete run cannot certify")
    tasks = [summarize_task(_mapping(task, "task"), k) for task in _sequence(result.get("task_results"), "task_results")]
    if not tasks:
        raise CaliperEvidenceError("run has no tasks")
    scored = [task["score"] for task in tasks if task["score"] is not None]
    hat = [task["pass_hat_k"] for task in tasks if task["pass_hat_k"] is not None]
    activation = [task["activation_score"] for task in tasks if task["activation_score"] is not None]
    asserted = sum(task["activation_expected"] is not None for task in tasks)
    avg_score = sum(scored) / len(scored) if scored else None
    aggregate = _mapping(result.get("aggregate"), "aggregate")
    if "avg_score" in aggregate and scored and not _close(aggregate["avg_score"], avg_score):
        raise CaliperEvidenceError(
            f"aggregate.avg_score={aggregate['avg_score']!r} disagrees with recomputed {avg_score!r}; refusing edited results"
        )
    usage_in = usage_out = 0
    wall = 0.0
    for task in _sequence(result.get("task_results"), "task_results"):
        for attempt in task.get("attempts", []):
            usage = attempt.get("usage") or {}
            usage_in += int(usage.get("input_tokens") or 0) + int(usage.get("cache_read_tokens") or 0) + int(usage.get("cache_creation_tokens") or 0)
            usage_out += int(usage.get("output_tokens") or 0)
            wall += float(attempt.get("duration_seconds") or 0.0)
    return {
        "spec": str(run.get("spec") or ""),
        "timestamp": str(run.get("timestamp") or ""),
        "k": k,
        "backend": str(run.get("backend") or ""),
        "model": run.get("model"),
        "judge_backend": run.get("judge_backend"),
        "judge_model": run.get("judge_model"),
        "ablated": list(run.get("ablated") or []),
        "tasks": tasks,
        "scored_tasks": len(scored),
        "avg_score": avg_score,
        "min_pass_hat_k": min(hat) if hat else None,
        "unusable": sum(task["unusable"] for task in tasks),
        "cheats": sum(task["cheats"] for task in tasks),
        "activation_asserted": asserted,
        "min_activation": min(activation) if activation else None,
        "usage": {"input_tokens": usage_in, "output_tokens": usage_out, "wall_seconds": round(wall, 1)},
    }


def _git_head(skill_dir: Path) -> str | None:
    try:
        completed = subprocess.run(
            ["git", "-C", str(skill_dir), "rev-parse", "HEAD"], capture_output=True, text=True, check=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return completed.stdout.strip() or None


def verify_snapshot(result: Mapping[str, Any], skill_dir: Path, *, allow_git_drift: bool = False) -> dict[str, Any]:
    """Bind the run to the skill on disk: frontmatter name, SKILL.md hash, and commit."""
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.is_file():
        raise CaliperEvidenceError(f"{skill_md} not found")
    name = (SkillDoc.from_path(skill_md).name or "").strip()
    if not name:
        raise CaliperEvidenceError("SKILL.md frontmatter has no name")
    snapshots = [
        _mapping(item, "skill snapshot") for item in _sequence(result.get("skill_snapshots"), "skill_snapshots")
        if _mapping(item, "skill snapshot").get("name") == name
    ]
    if len(snapshots) != 1:
        raise CaliperEvidenceError(f"run does not contain exactly one snapshot of skill {name!r}")
    snapshot = snapshots[0]
    files = _mapping(snapshot.get("files"), "snapshot files")
    recorded = str(_mapping(files.get("SKILL.md"), "snapshot SKILL.md").get("hash") or "")
    # Caliper hashes the decoded text, so binary-identical files hash identically here.
    current = "sha256:" + hashlib.sha256(skill_md.read_text(encoding="utf-8").encode("utf-8")).hexdigest()
    if recorded != current:
        raise CaliperEvidenceError("snapshot does not match: SKILL.md changed since the Caliper run")
    git_sha = snapshot.get("git_sha")
    head = _git_head(skill_dir)
    if git_sha and head and git_sha != head and not allow_git_drift:
        raise CaliperEvidenceError(
            f"snapshot does not match: run recorded commit {git_sha[:12]} but the skill is at {head[:12]}"
        )
    return {
        "name": name,
        "skill_md_sha256": current.removeprefix("sha256:"),
        "git_sha": git_sha,
        "git_drift": bool(git_sha and head and git_sha != head),
    }


def _fmt(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.2f}"


def build_checks(
    summary: Mapping[str, Any], snapshot: Mapping[str, Any], thresholds: Thresholds,
    *, ablation: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Evaluate thresholds; each check name is self-describing for the name-only registry record."""
    prefix = CHECK_PREFIX
    checks: list[dict[str, Any]] = [
        {"name": f"{prefix}:spec={summary['spec']}", "passed": bool(summary["spec"])},
        {"name": f"{prefix}:backend={summary['backend']}", "passed": bool(summary["backend"])},
        {"name": f"{prefix}:model={summary['model'] or 'cli-default'}", "passed": True},
        {"name": f"{prefix}:judge={summary['judge_backend'] or 'none'}", "passed": True},
        {"name": f"{prefix}:k={summary['k']}", "passed": True},
        {"name": f"{prefix}:tasks={len(summary['tasks'])}", "passed": True},
        {"name": f"{prefix}:skill_sha256={snapshot['skill_md_sha256'][:12]}", "passed": True},
    ]
    if summary["scored_tasks"] == 0:
        raise CaliperEvidenceError("run scored no tasks (trigger probes only); nothing to certify")
    avg = summary["avg_score"]
    checks.append({
        "name": f"{prefix}:success_rate>={thresholds.min_success_rate:.2f}(observed={_fmt(avg)})",
        "passed": avg is not None and avg + _TOLERANCE >= thresholds.min_success_rate,
    })
    hat = summary["min_pass_hat_k"]
    checks.append({
        "name": f"{prefix}:min_pass_hat_k>={thresholds.min_pass_hat_k:.2f}(observed={_fmt(hat)})",
        "passed": hat is not None and hat + _TOLERANCE >= thresholds.min_pass_hat_k,
    })
    checks.append({
        "name": f"{prefix}:unusable_attempts<={thresholds.max_unusable}(observed={summary['unusable']})",
        "passed": summary["unusable"] <= thresholds.max_unusable,
    })
    checks.append({"name": f"{prefix}:cheats=0(observed={summary['cheats']})", "passed": summary["cheats"] == 0})
    if summary["activation_asserted"]:
        activation = summary["min_activation"]
        checks.append({
            "name": f"{prefix}:activation>={thresholds.min_activation:.2f}(observed={_fmt(activation)})",
            "passed": activation is not None and activation + _TOLERANCE >= thresholds.min_activation,
        })
    if ablation is not None:
        if ablation["ablated"] != [snapshot["name"]]:
            raise CaliperEvidenceError(f"ablation run must ablate exactly {snapshot['name']!r}; got {ablation['ablated']!r}")
        if ablation["spec"] != summary["spec"] or ablation["k"] != summary["k"] or ablation["backend"] != summary["backend"]:
            raise CaliperEvidenceError("ablation run must use the same spec, k, and backend as the full run")
        delta = None if avg is None or ablation["avg_score"] is None else avg - ablation["avg_score"]
        checks.append({
            "name": f"{prefix}:ablation_delta>={thresholds.min_ablation_delta:.2f}(observed={_fmt(delta)})",
            "passed": delta is not None and delta + _TOLERANCE >= thresholds.min_ablation_delta,
        })
    if len({check["name"] for check in checks}) != len(checks):
        raise CaliperEvidenceError("internal error: duplicate check names")
    return checks


def build_evidence(
    result: Mapping[str, Any], *, skill_dir: Path, platform: str | None = None, skill_version: str | None = None,
    thresholds: Thresholds = Thresholds(), ablation: Mapping[str, Any] | None = None, allow_git_drift: bool = False,
) -> dict[str, Any]:
    """Produce `certify --evidence` JSON, raising when the run is unbound or below threshold."""
    summary = summarize_run(result)
    if summary["ablated"]:
        raise CaliperEvidenceError("an ablated run measures the agent without the skill and cannot certify it")
    snapshot = verify_snapshot(result, skill_dir, allow_git_drift=allow_git_drift)
    backend = normalize_platform_name(summary["backend"])
    target = normalize_platform_name(platform) if platform else backend
    if target != backend:
        raise CaliperEvidenceError(f"run backend {summary['backend']!r} cannot certify platform {platform!r}")
    if skill_version is None:
        doc = SkillDoc.from_path(skill_dir / "SKILL.md")
        skill_version = str(doc.metadata.get("version") or doc.field("version") or "").strip()
    if not skill_version:
        raise CaliperEvidenceError("skill version is required (metadata.version in SKILL.md or --skill-version)")
    ablation_summary = summarize_run(ablation) if ablation is not None else None
    checks = build_checks(summary, snapshot, thresholds, ablation=ablation_summary)
    failed = [check["name"] for check in checks if not check["passed"]]
    if failed:
        raise CaliperEvidenceError("threshold not met: " + "; ".join(failed))
    adapter = adapter_for(target)
    return {
        "platform": target,
        "skill_version": skill_version,
        "adapter": adapter["name"],
        "adapter_version": ADAPTER_VERSION,
        "checks": [{"name": check["name"], "passed": True} for check in checks],
        # Ignored by certify_compatibility; kept so the evidence file is self-explaining.
        "caliper": {
            "run": {key: summary[key] for key in ("spec", "timestamp", "k", "backend", "model", "judge_backend", "judge_model")},
            "metrics": {key: summary[key] for key in ("avg_score", "min_pass_hat_k", "unusable", "cheats", "min_activation", "usage")},
            "tasks": [
                {key: task[key] for key in ("name", "outcomes", "successes", "usable", "unusable", "score", "pass_hat_k", "activation_score")}
                for task in summary["tasks"]
            ],
            "snapshot": snapshot,
            "ablation": None if ablation_summary is None else {
                "timestamp": ablation_summary["timestamp"], "avg_score": ablation_summary["avg_score"],
            },
        },
    }


def prune_result(result: Mapping[str, Any]) -> dict[str, Any]:
    """Copy a run without transcripts, agent output, or skill file contents (hashes stay)."""
    pruned = json.loads(json.dumps(result))
    for snapshot in pruned.get("skill_snapshots", []):
        for entry in snapshot.get("files", {}).values():
            entry.pop("content", None)
    for task in pruned.get("task_results", []):
        for attempt in task.get("attempts", []):
            attempt.pop("transcript", None)
            attempt.pop("output", None)
    return pruned


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("result", type=Path, help="Caliper run JSON (.caliper/results/... or --output copy)")
    parser.add_argument("--skill", type=Path, required=True, help="skill directory containing SKILL.md")
    parser.add_argument("--platform", help="canonical platform id; defaults to the run's backend")
    parser.add_argument("--skill-version", help="semver; defaults to SKILL.md metadata.version")
    parser.add_argument("--ablation", type=Path, help="Caliper run of the same spec with the skill ablated")
    parser.add_argument("--evidence-out", type=Path, help="write certify --evidence JSON here")
    parser.add_argument("--output", type=Path, help="write a pruned copy of the run here (no transcripts or file contents)")
    parser.add_argument("--allow-git-drift", action="store_true", help="accept a run recorded at a different commit")
    defaults = Thresholds()
    parser.add_argument("--min-success-rate", type=float, default=defaults.min_success_rate)
    parser.add_argument("--min-pass-hat-k", type=float, default=defaults.min_pass_hat_k)
    parser.add_argument("--max-unusable", type=int, default=defaults.max_unusable)
    parser.add_argument("--min-activation", type=float, default=defaults.min_activation)
    parser.add_argument("--min-ablation-delta", type=float, default=defaults.min_ablation_delta)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    thresholds = Thresholds(
        min_success_rate=args.min_success_rate, min_pass_hat_k=args.min_pass_hat_k,
        max_unusable=args.max_unusable, min_activation=args.min_activation,
        min_ablation_delta=args.min_ablation_delta,
    )
    try:
        result = load_result(args.result)
        ablation = load_result(args.ablation) if args.ablation else None
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(prune_result(result), indent=2, sort_keys=True) + "\n", encoding="utf-8")
        evidence = build_evidence(
            result, skill_dir=args.skill, platform=args.platform, skill_version=args.skill_version,
            thresholds=thresholds, ablation=ablation, allow_git_drift=args.allow_git_drift,
        )
    except CaliperEvidenceError as exc:
        print(f"caliper evidence rejected: {exc}", file=sys.stderr)
        return 1
    text = json.dumps(evidence, indent=2, sort_keys=True) + "\n"
    if args.evidence_out:
        args.evidence_out.parent.mkdir(parents=True, exist_ok=True)
        args.evidence_out.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
