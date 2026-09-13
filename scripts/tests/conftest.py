"""Shared fixtures for scripts/tests."""

import pytest


@pytest.fixture(autouse=True)
def isolated_agent_skills_home(tmp_path, monkeypatch):
    """Keep every test's installed-skill ledger, parking area, and trash out of ~/.agent-skills."""
    home = tmp_path / "agent-skills-home"
    monkeypatch.setenv("AGENT_SKILLS_HOME", str(home))
    return home
