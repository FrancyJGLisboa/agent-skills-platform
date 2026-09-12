import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import check_verification  # noqa: E402
from check_verification import changed_skill_dirs, repair_for  # noqa: E402


def test_changed_skill_dirs_returns_no_skills_when_diff_is_empty() -> None:
    assert changed_skill_dirs("HEAD", "HEAD") == []


def test_repair_names_the_regenerate_command_for_stale_evidence() -> None:
    repair = repair_for("verification is stale: SKILL.md, scripts, or evals changed", "skills/foo")
    assert "generate_verification.py skills/foo" in repair


def test_repair_sends_a_failed_gate_to_the_graph_runner_first() -> None:
    repair = repair_for("verification records failed gates or evals", "skills/foo")
    assert "skill_graph.py run skills/foo" in repair
    assert "fix the failing gate or eval first" in repair


def test_repair_falls_back_to_regenerating_for_an_unrecognized_error() -> None:
    assert "generate_verification.py skills/foo" in repair_for("something new", "skills/foo")


def test_failure_output_carries_a_repair_line_and_the_commit_sequence(monkeypatch, capsys) -> None:
    monkeypatch.setattr(check_verification, "changed_skill_dirs", lambda base: [Path("skills/foo")])
    monkeypatch.setattr(check_verification, "verification_errors", lambda skill: ["VERIFICATION.md is missing"])

    assert check_verification.main(["--base", "HEAD~1"]) == 1

    err = capsys.readouterr().err
    assert f"{Path('skills/foo')}: VERIFICATION.md is missing" in err
    assert "repair: regenerate with python3" in err
    # The report-only follow-up rule is the part a contributor cannot guess.
    assert "exactly {VERIFICATION.md}" in err
    assert "not in step 3" in err
