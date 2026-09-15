"""Agent-run reliability: Caliper per declared platform, certified in one marketplace step."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scripts" / "tests"))

import marketplace_reliability as reliability  # noqa: E402
import team_marketplace as market  # noqa: E402
from test_team_marketplace import init_marketplace, make_skill, recommit_and_attest  # noqa: E402

FIXTURE = ROOT / "scripts" / "tests" / "fixtures" / "caliper_result_sample.json"
SPEC = "skills:\n  - ../../SKILL.md\ntasks:\n  - name: happy\n    prompt: run it\n    activates: [demo]\n"


def add_spec(skill: Path) -> Path:
    spec_dir = skill / "evals" / "caliper"
    spec_dir.mkdir(parents=True)
    spec = spec_dir / f"{skill.name}.eval.yaml"
    spec.write_text(SPEC, encoding="utf-8")
    return spec


def which_all(name: str) -> str | None:
    return f"/usr/local/bin/{name}"


def which_only(*names: str):
    return lambda name: f"/usr/local/bin/{name}" if name in names else None


def fake_runner(*, fail_platforms: set[str] = frozenset(), crash_platforms: set[str] = frozenset()):
    """A `caliper run` stand-in: writes the fixture result bound to the skill it was pointed at."""
    calls: list[list[str]] = []
    real_run = subprocess.run

    def run(command: list[str], **kwargs) -> subprocess.CompletedProcess[str]:
        if not (len(command) > 1 and command[1] == "run" and Path(command[0]).name == "caliper"):
            return real_run(command, **kwargs)  # git and other helpers keep working when patched globally
        calls.append(command)
        backend = command[command.index("--model") + 1]
        output = Path(command[command.index("--output") + 1])
        spec = Path(command[2])
        skill_dir = spec.parent.parent.parent
        if backend in crash_platforms:
            return subprocess.CompletedProcess(command, 2, "", "boom: no agent")
        result = json.loads(FIXTURE.read_text(encoding="utf-8"))
        result["run"]["backend"] = backend
        result["run"]["judge_backend"] = command[command.index("--judge-model") + 1]
        skill_md = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
        snapshot = result["skill_snapshots"][0]
        snapshot["name"] = skill_dir.name
        snapshot["files"]["SKILL.md"] = {"content": skill_md, "hash": "sha256:" + hashlib.sha256(skill_md.encode()).hexdigest()}
        if backend in fail_platforms:
            task = result["task_results"][0]
            for attempt in task["attempts"]:
                attempt["outcome"], attempt["passed"] = "task_fail", False
            task.update({"successes": 0, "score": 0.0, "pass_hat_k": 0.0, "pass_at_k": 0.0})
            result["aggregate"]["avg_score"] = 0.5
        output.write_text(json.dumps(result), encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, "ok", "")

    run.calls = calls  # type: ignore[attr-defined]
    return run


def test_select_platforms_reports_why_each_platform_is_or_is_not_measured() -> None:
    rows = reliability.select_platforms(["codex", "claude-code", "github-copilot"], which=which_only("claude", "caliper"))
    assert [(row["platform"], row["status"]) for row in rows] == [
        ("claude-code", "run"), ("codex", "skipped"), ("github-copilot", "skipped"),
    ]
    assert "attestation" in rows[2]["reason"] and "'codex'" in rows[1]["reason"]
    with pytest.raises(reliability.ReliabilityError, match="not declared"):
        reliability.select_platforms(["codex"], ["claude-code"], which=which_all)


def test_judge_prefers_the_other_vendor_and_falls_back() -> None:
    assert reliability.judge_for("claude-code", which=which_all) == "codex"
    assert reliability.judge_for("claude-code", which=which_only("claude")) == "claude-code"
    command = reliability.caliper_command("caliper", Path("s.eval.yaml"), backend="codex", judge="claude-code", k=3, timeout=180, output=Path("o.json"))
    assert "--workers" in command and command[command.index("--workers") + 1] == "1"


def test_run_reliability_binds_certifies_refuses_and_reports_failures(tmp_path: Path) -> None:
    skill = tmp_path / "demo"
    skill.mkdir()
    (skill / "SKILL.md").write_text("---\nname: demo\nmetadata:\n  version: 1.0.0\n---\n# Demo\n", encoding="utf-8")
    with pytest.raises(reliability.ReliabilityError, match="no evals/caliper"):
        reliability.run_reliability(skill, ["claude-code"], results_dir=tmp_path / "runs", which=which_all, runner=fake_runner())
    add_spec(skill)
    runner = fake_runner(fail_platforms={"codex"})
    report = reliability.run_reliability(
        skill, ["claude-code", "codex", "github-copilot"], results_dir=tmp_path / "runs",
        which=which_all, runner=runner,
    )
    by_platform = {row["platform"]: row for row in report["platforms"]}
    assert by_platform["claude-code"]["status"] == "certifiable"
    assert by_platform["claude-code"]["evidence"]["platform"] == "claude-code"
    assert Path(by_platform["claude-code"]["pruned_run"]).is_file()
    assert by_platform["codex"]["status"] == "refused" and "success_rate" in by_platform["codex"]["reason"]
    assert by_platform["github-copilot"]["status"] == "skipped"
    assert len(runner.calls) == 2 and all(str(skill / "evals" / "caliper") in call[2] for call in runner.calls)
    crashed = reliability.run_reliability(
        skill, ["claude-code"], results_dir=tmp_path / "runs2", which=which_all, runner=fake_runner(crash_platforms={"claude-code"}),
    )
    assert crashed["platforms"][0]["status"] == "failed" and "boom" in crashed["platforms"][0]["reason"]


def test_run_reliability_requires_caliper_only_when_something_will_run(tmp_path: Path) -> None:
    skill = tmp_path / "demo"
    skill.mkdir()
    (skill / "SKILL.md").write_text("---\nname: demo\n---\n# Demo\n", encoding="utf-8")
    add_spec(skill)
    report = reliability.run_reliability(skill, ["github-copilot"], results_dir=tmp_path / "runs", which=lambda _n: None, runner=fake_runner())
    assert report["platforms"][0]["status"] == "skipped"
    with pytest.raises(reliability.ReliabilityError, match="caliper is not installed"):
        reliability.run_reliability(skill, ["codex"], results_dir=tmp_path / "runs", which=which_only("codex"), runner=fake_runner())


def test_reliability_check_failures_only_concern_caliper_capable_platforms() -> None:
    entry = {"compatibility": {"certified": [
        {"platform": "codex", "checks": ["representative-load"]},
        {"platform": "claude-code", "checks": ["caliper:success_rate>=0.90(observed=1.00)"]},
        {"platform": "github-copilot", "checks": ["representative-load"]},
    ]}}
    assert reliability.reliability_check_failures(entry) == ["codex certification carries no agent-run (caliper:*) checks"]


def test_marketplace_reliability_certifies_in_one_step_and_release_can_require_it(tmp_path: Path) -> None:
    repo = init_marketplace(tmp_path)
    skill = make_skill(tmp_path, "report-skill")
    discovery = json.loads((skill / "discovery.json").read_text(encoding="utf-8"))
    discovery["compatibility"] = {"declared": ["claude-code", "codex", "github-copilot"]}
    (skill / "discovery.json").write_text(json.dumps(discovery), encoding="utf-8")
    add_spec(skill)
    recommit_and_attest(skill)
    market.add_skill(repo, skill, "finance", "base")

    runner = fake_runner(fail_platforms={"codex"})
    report = market.reliability_skill(
        repo, "finance", "report-skill", results_dir=tmp_path / "runs", which=which_all, runner=runner,
    )
    statuses = {row["platform"]: row["status"] for row in report["platforms"]}
    assert statuses == {"claude-code": "certified", "codex": "refused", "github-copilot": "skipped"}
    assert report["certified"] == ["claude-code"]
    assert "evidence" not in report["platforms"][0]
    entry = market._find_skill(market.load_manifest(repo), "finance", "report-skill")
    certified = {item["platform"]: item for item in entry["compatibility"]["certified"]}
    assert certified["claude-code"]["passed"] is True
    assert any(name.startswith("caliper:success_rate>=") for name in certified["claude-code"]["checks"])
    assert "codex" not in certified

    # Hand-written codex evidence still certifies, but --require-reliability names it at release.
    market.certify_skill(repo, "finance", "report-skill", "codex", {
        "platform": "codex", "skill_version": "1.2.3", "adapter": "native-skill", "adapter_version": "1.0.0",
        "checks": [{"name": "representative-load", "passed": True}],
    })
    market.certify_skill(repo, "finance", "report-skill", "github-copilot", {
        "platform": "github-copilot", "skill_version": "1.2.3", "adapter": "native-skill", "adapter_version": "1.0.0",
        "checks": [{"name": "representative-load", "passed": True}],
    })
    market.transition_skill(repo, "finance", "report-skill", "published")
    assert market.check_marketplace(repo, require_published=True) == []
    errors = market.check_marketplace(repo, require_published=True, require_reliability=True)
    assert errors == ["report-skill: codex certification carries no agent-run (caliper:*) checks"]

    # Measuring again without certifying leaves the manifest alone.
    before = (repo / "registry.json").read_text(encoding="utf-8")
    dry = market.reliability_skill(
        repo, "finance", "report-skill", platforms=["claude-code"], certify=False,
        results_dir=tmp_path / "runs2", which=which_all, runner=fake_runner(),
    )
    assert dry["platforms"][0]["status"] == "certifiable" and dry["certified"] == []
    assert (repo / "registry.json").read_text(encoding="utf-8") == before


def test_reliability_cli_exit_code_reflects_refusals(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    repo = init_marketplace(tmp_path)
    skill = make_skill(tmp_path, "report-skill")
    discovery = json.loads((skill / "discovery.json").read_text(encoding="utf-8"))
    discovery["compatibility"] = {"declared": ["claude-code"]}
    (skill / "discovery.json").write_text(json.dumps(discovery), encoding="utf-8")
    add_spec(skill)
    recommit_and_attest(skill)
    market.add_skill(repo, skill, "finance", "base")
    monkeypatch.setattr(reliability.shutil, "which", which_all)
    monkeypatch.setattr(reliability.subprocess, "run", fake_runner())
    code = market.main([
        "reliability", "report-skill", "--department", "finance", "--marketplace", str(repo),
        "--results-dir", str(tmp_path / "runs"),
    ])
    assert code == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed["certified"] == ["claude-code"]
    monkeypatch.setattr(reliability.subprocess, "run", fake_runner(fail_platforms={"claude-code"}))
    code = market.main([
        "reliability", "report-skill", "--department", "finance", "--marketplace", str(repo),
        "--results-dir", str(tmp_path / "runs2"),
    ])
    assert code == 1
