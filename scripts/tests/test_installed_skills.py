"""Tests for the installed-skill lifecycle: ledger, enable/disable, recycle bin, --tag bulk ops.

Every test runs against a registry under tmp_path and a ledger under the
AGENT_SKILLS_HOME that conftest.py points at tmp_path, so nothing touches the
real home. Project-scope installs resolve against cwd, so tests chdir too.
"""

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(Path(__file__).parent))

import installed_skills as ledger  # noqa: E402
import skill_registry as reg  # noqa: E402
from test_skill_registry import init_registry, make_skill, publish  # noqa: E402


def ns(**kwargs) -> argparse.Namespace:
    return argparse.Namespace(**kwargs)


def install(registry: Path, name: str, **overrides) -> Path:
    args = ns(registry=str(registry), skill_name=name, author=None, tag=None,
              platform="claude-code", project=True, force=False, json=False)
    for key, value in overrides.items():
        setattr(args, key, value)
    reg.cmd_install(args)
    return Path.cwd() / ".claude" / "skills" / name


def lifecycle(command, name=None, **overrides) -> argparse.Namespace:
    args = ns(skill_name=name, tag=None, all=False, platform=None, json=False, force=True, check=False)
    for key, value in overrides.items():
        setattr(args, key, value)
    command(args)
    return args


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    registry = init_registry(tmp_path)
    publish(registry, make_skill(tmp_path, "alpha"), tags="finance,report")
    publish(registry, make_skill(tmp_path, "beta"), tags="finance")
    publish(registry, make_skill(tmp_path, "gamma"), tags="ops")
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.chdir(work)
    return registry


# --- ledger ---

def test_install_records_a_ledger_entry(workspace):
    path = install(workspace, "alpha")
    entries = ledger.load_ledger()["skills"]
    assert len(entries) == 1
    entry = entries[0]
    assert entry["name"] == "alpha"
    assert entry["path"] == str(path)
    assert entry["platform"] == "claude-code"
    assert entry["scope"] == "project"
    assert entry["version"] == "1.0.0"
    assert entry["tags"] == ["finance", "report"]
    assert entry["enabled"] is True
    assert ledger.ledger_path().is_relative_to(Path(os.environ["AGENT_SKILLS_HOME"]))


def test_reinstall_with_force_replaces_the_entry_not_duplicates(workspace):
    install(workspace, "alpha")
    install(workspace, "alpha", force=True)
    assert len(ledger.load_ledger()["skills"]) == 1


def test_installed_lists_and_filters_by_tag(workspace, capsys):
    install(workspace, "alpha")
    install(workspace, "gamma")
    capsys.readouterr()  # drop install chatter
    reg.cmd_installed(ns(tag="finance", platform=None, json=True))
    listed = json.loads(capsys.readouterr().out)
    assert [e["name"] for e in listed] == ["alpha"]


# --- update ---

def bump_registry_version(registry: Path, name: str, version: str) -> None:
    data = reg.load_registry(registry)
    for entry in data["skills"]:
        if entry["name"] == name:
            entry["version"] = version
    reg.save_registry(registry, data)


def test_update_check_reports_outdated_and_exits_2(workspace, capsys):
    install(workspace, "alpha")
    bump_registry_version(workspace, "alpha", "1.1.0")
    capsys.readouterr()  # drop install chatter
    with pytest.raises(SystemExit) as exc:
        lifecycle(reg.cmd_update, "alpha", check=True, json=True)
    assert exc.value.code == 2
    result = json.loads(capsys.readouterr().out)[0]
    assert result["status"] == "outdated"
    assert (result["installed"], result["available"]) == ("1.0.0", "1.1.0")
    # --check must not touch the ledger.
    assert ledger.load_ledger()["skills"][0]["version"] == "1.0.0"


def test_update_reinstalls_and_bumps_ledger_version(workspace):
    install(workspace, "alpha")
    bump_registry_version(workspace, "alpha", "2.0.0")
    lifecycle(reg.cmd_update, "alpha", force=False)
    assert ledger.load_ledger()["skills"][0]["version"] == "2.0.0"


def test_update_current_skill_is_a_noop(workspace, capsys):
    install(workspace, "alpha")
    lifecycle(reg.cmd_update, "alpha", force=False)
    assert "current" in capsys.readouterr().out


def test_update_keeps_a_disabled_skill_disabled(workspace):
    path = install(workspace, "alpha")
    lifecycle(reg.cmd_disable, "alpha")
    bump_registry_version(workspace, "alpha", "2.0.0")
    lifecycle(reg.cmd_update, "alpha", force=False)
    entry = ledger.load_ledger()["skills"][0]
    assert entry["version"] == "2.0.0"
    assert entry["enabled"] is False
    assert not path.exists()
    assert (Path(entry["parked_path"]) / "SKILL.md").exists()


# --- enable / disable ---

def test_disable_moves_files_out_of_the_tool_tree_and_enable_restores(workspace):
    path = install(workspace, "alpha")
    lifecycle(reg.cmd_disable, "alpha")
    entry = ledger.load_ledger()["skills"][0]
    assert entry["enabled"] is False
    assert not path.exists()
    parked = Path(entry["parked_path"])
    assert parked.is_relative_to(ledger.disabled_dir())
    assert (parked / "SKILL.md").exists()

    lifecycle(reg.cmd_enable, "alpha")
    entry = ledger.load_ledger()["skills"][0]
    assert entry["enabled"] is True
    assert "parked_path" not in entry
    assert (path / "SKILL.md").exists()
    assert not parked.exists()


def test_disable_is_idempotent(workspace, capsys):
    install(workspace, "alpha")
    lifecycle(reg.cmd_disable, "alpha")
    lifecycle(reg.cmd_disable, "alpha")
    assert "already disabled" in capsys.readouterr().out


def test_lifecycle_requires_exactly_one_selector(workspace, capsys):
    install(workspace, "alpha")
    with pytest.raises(SystemExit):
        lifecycle(reg.cmd_disable, "alpha", tag="finance")
    with pytest.raises(SystemExit):
        lifecycle(reg.cmd_disable, None)
    assert "exactly one of" in capsys.readouterr().err


def test_unknown_installed_skill_exits(workspace, capsys):
    with pytest.raises(SystemExit):
        lifecycle(reg.cmd_disable, "nope")
    assert "not recorded as installed" in capsys.readouterr().err


# --- recycle bin ---

def test_uninstall_moves_to_trash_and_restore_brings_it_back(workspace, capsys):
    path = install(workspace, "alpha")
    lifecycle(reg.cmd_uninstall, "alpha")
    assert not path.exists()
    assert ledger.load_ledger()["skills"] == []
    items = ledger.list_trash()
    assert len(items) == 1
    assert items[0]["kind"] == "install"
    assert (Path(items[0]["item"]) / "files" / "SKILL.md").exists()

    reg.cmd_restore(ns(skill_name="alpha", force=False, json=False))
    assert (path / "SKILL.md").exists()
    assert ledger.list_trash() == []
    entry = ledger.load_ledger()["skills"][0]
    assert entry["name"] == "alpha" and entry["enabled"] is True


def test_uninstall_without_force_refuses(workspace, capsys):
    path = install(workspace, "alpha")
    with pytest.raises(SystemExit):
        lifecycle(reg.cmd_uninstall, "alpha", force=False)
    assert "Use --force" in capsys.readouterr().err
    assert path.exists()


def test_uninstall_of_a_disabled_skill_restores_to_the_live_path(workspace):
    path = install(workspace, "alpha")
    lifecycle(reg.cmd_disable, "alpha")
    lifecycle(reg.cmd_uninstall, "alpha")
    assert ledger.list_trash()[0]["origin"] == str(path)
    reg.cmd_restore(ns(skill_name="alpha", force=False, json=False))
    assert (path / "SKILL.md").exists()


def test_restore_refuses_to_clobber_without_force(workspace, capsys):
    install(workspace, "alpha")
    lifecycle(reg.cmd_uninstall, "alpha")
    install(workspace, "alpha")
    with pytest.raises(SystemExit):
        reg.cmd_restore(ns(skill_name="alpha", force=False, json=False))
    assert "already exists" in capsys.readouterr().err


def test_registry_remove_goes_to_trash_and_restore_re_registers(workspace):
    reg.cmd_remove(ns(registry=str(workspace), skill_name="alpha", author=None, force=True))
    assert "alpha" not in {s["name"] for s in reg.load_registry(workspace)["skills"]}
    assert not (workspace / "skills" / "alice" / "alpha").exists()
    item = ledger.list_trash()[0]
    assert item["kind"] == "registry"

    reg.cmd_restore(ns(skill_name="alpha", force=False, json=False))
    assert (workspace / "skills" / "alice" / "alpha" / "SKILL.md").exists()
    restored = [s for s in reg.load_registry(workspace)["skills"] if s["name"] == "alpha"]
    assert len(restored) == 1 and restored[0]["tags"] == ["finance", "report"]


def test_purge_deletes_only_items_older_than_ttl(workspace):
    install(workspace, "alpha")
    install(workspace, "beta")
    lifecycle(reg.cmd_uninstall, "alpha")
    lifecycle(reg.cmd_uninstall, "beta")
    old = [i for i in ledger.list_trash() if i["name"] == "alpha"][0]
    sidecar = Path(old["item"]) / ledger.TRASH_SIDECAR
    data = json.loads(sidecar.read_text())
    data["trashed_at"] = (datetime.now(timezone.utc) - timedelta(days=40)).isoformat(timespec="seconds")
    sidecar.write_text(json.dumps(data))

    purged = ledger.purge_trash(30)
    assert [i["name"] for i in purged] == ["alpha"]
    assert [i["name"] for i in ledger.list_trash()] == ["beta"]


# --- tag bulk ops ---

def test_install_by_tag_installs_every_tagged_skill(workspace):
    args = ns(registry=str(workspace), skill_name=None, author=None, tag="finance",
              platform="claude-code", project=True, force=False, json=False)
    reg.cmd_install(args)
    names = sorted(e["name"] for e in ledger.load_ledger()["skills"])
    assert names == ["alpha", "beta"]
    assert not (Path.cwd() / ".claude" / "skills" / "gamma").exists()


def test_install_by_unknown_tag_exits(workspace, capsys):
    args = ns(registry=str(workspace), skill_name=None, author=None, tag="nothing",
              platform="claude-code", project=True, force=False, json=False)
    with pytest.raises(SystemExit):
        reg.cmd_install(args)
    assert "no registry skills carry tag" in capsys.readouterr().err


def test_disable_by_tag_touches_only_tagged_skills(workspace):
    install(workspace, "alpha")
    install(workspace, "beta")
    install(workspace, "gamma")
    lifecycle(reg.cmd_disable, None, tag="finance")
    state = {e["name"]: e["enabled"] for e in ledger.load_ledger()["skills"]}
    assert state == {"alpha": False, "beta": False, "gamma": True}


def test_uninstall_all_empties_the_ledger(workspace):
    install(workspace, "alpha")
    install(workspace, "gamma")
    lifecycle(reg.cmd_uninstall, None, all=True)
    assert ledger.load_ledger()["skills"] == []
    assert len(ledger.list_trash()) == 2


def test_registry_list_filters_by_tag(workspace, capsys):
    reg.cmd_list(ns(registry=str(workspace), tag="ops", json=True))
    assert [s["name"] for s in json.loads(capsys.readouterr().out)] == ["gamma"]


# --- CLI wiring ---

def test_parser_exposes_lifecycle_commands():
    parser = reg.build_parser()
    args = parser.parse_args(["update", "--all", "--check"])
    assert (args.command, args.all, args.check) == ("update", True, True)
    args = parser.parse_args(["purge", "--older-than", "7"])
    assert args.older_than == 7
    args = parser.parse_args(["install", "--tag", "finance"])
    assert args.skill_name is None and args.tag == "finance"


def test_platforms_json_lists_every_platform_with_paths(capsys):
    reg.cmd_platforms(ns(json=True))
    rows = json.loads(capsys.readouterr().out)
    assert [r["name"] for r in rows] == reg.ALL_PLATFORMS
    copilot = next(r for r in rows if r["name"] == "github-copilot")
    assert copilot["user_path"] == "~/.copilot/skills"
    assert isinstance(copilot["detected"], bool)
