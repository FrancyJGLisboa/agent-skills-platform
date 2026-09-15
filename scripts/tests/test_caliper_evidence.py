"""Caliper run → marketplace certification evidence adapter tests."""

from __future__ import annotations

import copy
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import caliper_evidence as adapter  # noqa: E402
import marketplace_distribution as distribution  # noqa: E402

FIXTURE = ROOT / "scripts" / "tests" / "fixtures" / "caliper_result_sample.json"
NOW = datetime(2026, 9, 15, 12, tzinfo=timezone.utc)


@pytest.fixture
def result() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


@pytest.fixture
def skill(result: dict, tmp_path: Path) -> Path:
    skill_dir = tmp_path / "demo-skill"
    skill_dir.mkdir()
    content = result["skill_snapshots"][0]["files"]["SKILL.md"]["content"]
    (skill_dir / "SKILL.md").write_text(content, encoding="utf-8")
    return skill_dir


def names(evidence: dict) -> list[str]:
    return [check["name"] for check in evidence["checks"]]


def test_summary_recomputes_metrics_from_attempt_outcomes(result: dict) -> None:
    summary = adapter.summarize_run(result)
    happy, edge, silence = summary["tasks"]
    assert (happy["successes"], happy["usable"], happy["pass_hat_k"]) == (3, 3, 1.0)
    assert (edge["successes"], edge["usable"], edge["unusable"], edge["pass_hat_k"]) == (2, 2, 1, 1.0)
    assert silence["trigger_only"] and silence["score"] is None and silence["activation_score"] == 1.0
    assert summary["scored_tasks"] == 2 and summary["avg_score"] == 1.0
    assert summary["unusable"] == 1 and summary["cheats"] == 0 and summary["min_activation"] == 1.0
    assert summary["usage"]["output_tokens"] == 900


def test_edited_stored_metrics_are_refused(result: dict) -> None:
    result["task_results"][1]["score"] = 1.0
    result["task_results"][1]["attempts"][0]["outcome"] = "task_fail"
    with pytest.raises(adapter.CaliperEvidenceError, match="refusing edited results"):
        adapter.summarize_run(result)


def test_evidence_encodes_thresholds_and_observations(result: dict, skill: Path) -> None:
    evidence = adapter.build_evidence(result, skill_dir=skill)
    assert evidence["platform"] == "claude-code" and evidence["skill_version"] == "1.0.0"
    assert evidence["adapter"] == "native-skill" and evidence["adapter_version"] == distribution.ADAPTER_VERSION
    assert all(check["passed"] is True for check in evidence["checks"])
    assert "caliper:success_rate>=0.90(observed=1.00)" in names(evidence)
    assert "caliper:min_pass_hat_k>=0.70(observed=1.00)" in names(evidence)
    assert "caliper:unusable_attempts<=1(observed=1)" in names(evidence)
    assert "caliper:activation>=0.90(observed=1.00)" in names(evidence)
    assert "caliper:judge=codex" in names(evidence) and "caliper:k=3" in names(evidence)
    assert evidence["caliper"]["snapshot"]["name"] == "demo-skill"
    assert evidence["caliper"]["metrics"]["unusable"] == 1


def test_evidence_is_accepted_by_certify_compatibility(result: dict, skill: Path) -> None:
    evidence = adapter.build_evidence(result, skill_dir=skill)
    record = distribution.certify_compatibility(
        platform="claude-code", skill_version="1.0.0", declared_platforms=["claude-code", "codex"],
        evidence=evidence, timestamp=NOW,
    )
    assert record["passed"] is True and record["platform"] == "claude-code"
    assert any(name.startswith("caliper:success_rate>=") for name in record["checks"])


def test_unusable_attempts_cannot_hide_behind_the_success_rate(result: dict, skill: Path) -> None:
    thresholds = adapter.Thresholds(max_unusable=0)
    with pytest.raises(adapter.CaliperEvidenceError, match=r"unusable_attempts<=0\(observed=1\)"):
        adapter.build_evidence(result, skill_dir=skill, thresholds=thresholds)


def test_failed_task_lowers_pass_hat_k_below_threshold(result: dict, skill: Path) -> None:
    task = result["task_results"][0]
    task["attempts"][2]["outcome"] = "task_fail"
    task["attempts"][2]["passed"] = False
    task["successes"], task["score"], task["pass_hat_k"] = 2, 2 / 3, (2 / 3) ** 3
    task["pass_at_k"] = 1 - (1 / 3) ** 3
    result["aggregate"]["avg_score"] = (2 / 3 + 1.0) / 2
    with pytest.raises(adapter.CaliperEvidenceError, match=r"success_rate>=0.90\(observed=0.83\)"):
        adapter.build_evidence(result, skill_dir=skill)


def test_platform_must_match_the_run_backend(result: dict, skill: Path) -> None:
    with pytest.raises(adapter.CaliperEvidenceError, match="cannot certify platform 'codex'"):
        adapter.build_evidence(result, skill_dir=skill, platform="codex")


def test_skill_md_drift_is_rejected(result: dict, skill: Path) -> None:
    with (skill / "SKILL.md").open("a", encoding="utf-8") as handle:
        handle.write("\nOne more line.\n")
    with pytest.raises(adapter.CaliperEvidenceError, match="SKILL.md changed since the Caliper run"):
        adapter.build_evidence(result, skill_dir=skill)


def test_git_drift_is_rejected_unless_allowed(result: dict, skill: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    result["skill_snapshots"][0]["git_sha"] = "a" * 40
    monkeypatch.setattr(adapter, "_git_head", lambda _skill_dir: "b" * 40)
    with pytest.raises(adapter.CaliperEvidenceError, match="recorded commit aaaaaaaaaaaa"):
        adapter.build_evidence(result, skill_dir=skill)
    evidence = adapter.build_evidence(result, skill_dir=skill, allow_git_drift=True)
    assert evidence["caliper"]["snapshot"]["git_drift"] is True


def test_activation_check_only_when_a_task_asserted_it(result: dict, skill: Path) -> None:
    for task in result["task_results"]:
        task["activation_expected"] = None
        task["activation_score"] = None
        task["activation_usable"] = task["activation_successes"] = 0
        for attempt in task["attempts"]:
            attempt["activation_passed"] = None
    evidence = adapter.build_evidence(result, skill_dir=skill)
    assert not any(name.startswith("caliper:activation>=") for name in names(evidence))


def test_incomplete_or_interrupted_runs_are_refused(result: dict, skill: Path) -> None:
    short = copy.deepcopy(result)
    short["task_results"][0]["attempts"].pop()
    with pytest.raises(adapter.CaliperEvidenceError, match="has 2 attempts; the run declares k=3"):
        adapter.build_evidence(short, skill_dir=skill)
    result["run"]["interrupted"] = True
    with pytest.raises(adapter.CaliperEvidenceError, match="interrupted"):
        adapter.build_evidence(result, skill_dir=skill)


def test_ablated_run_cannot_certify_but_measures_the_delta(result: dict, skill: Path) -> None:
    ablated = copy.deepcopy(result)
    ablated["run"]["ablated"] = ["demo-skill"]
    for index in (1, 2):
        attempt = ablated["task_results"][0]["attempts"][index]
        attempt["outcome"], attempt["passed"] = "task_fail", False
    task = ablated["task_results"][0]
    task["successes"], task["score"], task["pass_hat_k"], task["pass_at_k"] = 1, 1 / 3, (1 / 3) ** 3, 1 - (2 / 3) ** 3
    ablated["aggregate"]["avg_score"] = (1 / 3 + 1.0) / 2
    with pytest.raises(adapter.CaliperEvidenceError, match="ablated run"):
        adapter.build_evidence(ablated, skill_dir=skill)
    evidence = adapter.build_evidence(result, skill_dir=skill, ablation=ablated)
    assert "caliper:ablation_delta>=0.20(observed=0.33)" in names(evidence)
    wrong = copy.deepcopy(ablated)
    wrong["run"]["ablated"] = ["other-skill"]
    with pytest.raises(adapter.CaliperEvidenceError, match="must ablate exactly 'demo-skill'"):
        adapter.build_evidence(result, skill_dir=skill, ablation=wrong)


def test_prune_drops_transcripts_output_and_file_contents(result: dict) -> None:
    pruned = adapter.prune_result(result)
    assert "content" not in pruned["skill_snapshots"][0]["files"]["SKILL.md"]
    assert pruned["skill_snapshots"][0]["files"]["SKILL.md"]["hash"].startswith("sha256:")
    attempt = pruned["task_results"][0]["attempts"][0]
    assert "transcript" not in attempt and "output" not in attempt and attempt["outcome"] == "pass"
    assert "transcript" in result["task_results"][0]["attempts"][0]


def test_main_writes_evidence_and_pruned_copy_and_reports_rejections(
    result: dict, skill: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    run = tmp_path / "run.json"
    run.write_text(json.dumps(result), encoding="utf-8")
    evidence_out = tmp_path / "out" / "evidence.json"
    pruned_out = tmp_path / "out" / "pruned.json"
    code = adapter.main([
        str(run), "--skill", str(skill), "--evidence-out", str(evidence_out), "--output", str(pruned_out),
    ])
    assert code == 0
    assert json.loads(capsys.readouterr().out)["platform"] == "claude-code"
    assert json.loads(evidence_out.read_text(encoding="utf-8"))["checks"]
    assert "transcript" not in json.dumps(json.loads(pruned_out.read_text(encoding="utf-8")))
    code = adapter.main([str(run), "--skill", str(skill), "--max-unusable", "0", "--evidence-out", str(tmp_path / "no.json")])
    assert code == 1
    assert "caliper evidence rejected" in capsys.readouterr().err
    assert not (tmp_path / "no.json").exists()
