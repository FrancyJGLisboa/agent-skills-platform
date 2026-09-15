#!/usr/bin/env python3
"""Build and operate a governed, provider-neutral team skill marketplace.

The marketplace targets GitHub Copilot Agent Mode with GitHub and GitLab
repository backends. Governance remains repository-native:
department paths, CODEOWNERS, pull-request checks, immutable version pins, and
machine-readable quality evidence in ``registry.json``.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
import time
from abc import ABC, abstractmethod
from contextlib import contextmanager
from datetime import date, datetime, timezone
from functools import wraps
from pathlib import Path
from typing import Any

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from check_pipeline import check as check_pipeline  # noqa: E402
from security_scan import security_scan  # noqa: E402
from skill_document import SkillDoc  # noqa: E402
from validate import validate_skill  # noqa: E402
from marketplace_trust import (  # noqa: E402
    TrustError, create_attestation, transition_lifecycle, validate_attestation,
)
from marketplace_health import build_health_report, report_json, report_markdown  # noqa: E402
from marketplace_discovery import (  # noqa: E402
    DiscoveryError, evaluate_portfolio, render_skill_page, require_operating_contract,
    search_skills, semantic_freshness_failures,
)
from marketplace_metrics import (  # noqa: E402
    CONSENT_SCHEMA, EVENT_TYPES, MetricsError, aggregate_events, create_event,
    record_event, validate_consent,
)
from marketplace_distribution import (  # noqa: E402
    DistributionError, build_install_plan, certify_compatibility,
)
from marketplace_reliability import (  # noqa: E402
    ReliabilityError, reliability_check_failures, run_reliability,
)
from platforms import normalize_platform_name  # noqa: E402
from generate_verification import render_report, verification_errors  # noqa: E402

SCHEMA_VERSION = 2
SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
SEMVER_TAG_RE = re.compile(r"^v(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)(?:-[0-9A-Za-z.-]+)?$")
SEMVER_RE = re.compile(r"^(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)(?:-[0-9A-Za-z.-]+)?$")
APPROVED = "approved"
BLOCKED_TOOLS = {"shell", "bash"}
COPY_IGNORE_PATTERNS = shutil.ignore_patterns(
    ".git", "__pycache__", "node_modules", ".venv", "venv", ".pytest_cache",
    ".mypy_cache", "dist", "build", "*.pyc", "*.pyo",
)
SCAFFOLD_SCRIPTS = (
    "team_marketplace.py", "check_pipeline.py", "security_scan.py",
    "skill_document.py", "structured_interview.py", "validate.py",
    "marketplace_trust.py", "marketplace_health.py", "marketplace_discovery.py",
    "marketplace_metrics.py",
    "marketplace_distribution.py", "platforms.py", "review_staleness.py",
    "generate_verification.py", "marketplace_reliability.py", "caliper_evidence.py",
)
ATTESTATION_FILE = "marketplace-attestation.json"


class MarketplaceError(RuntimeError):
    """A user-correctable marketplace or governance failure."""


@contextmanager
def _marketplace_lock(root: Path, *, timeout_seconds: float = 30.0):
    """Serialize marketplace mutations across threads and CLI processes."""
    lock = root / ".marketplace-mutation.lock"
    deadline = time.monotonic() + timeout_seconds
    while True:
        try:
            lock.mkdir()
            break
        except FileExistsError:
            try:
                stale = time.time() - lock.stat().st_mtime > 300
            except FileNotFoundError:
                continue
            if stale:
                try:
                    lock.rmdir()
                except OSError:
                    pass
                continue
            if time.monotonic() >= deadline:
                raise MarketplaceError(f"timed out waiting for marketplace mutation lock: {lock}")
            time.sleep(0.05)
    try:
        yield
    finally:
        try:
            lock.rmdir()
        except FileNotFoundError:
            pass


def _serialized_mutation(function):
    """Run a root-first marketplace mutation under the repository lock."""
    @wraps(function)
    def wrapped(root: Path, *args: Any, **kwargs: Any):
        with _marketplace_lock(root):
            return function(root, *args, **kwargs)
    return wrapped


class MarketplaceProvider(ABC):
    """Repository-host-specific transport and generated governance files."""

    name: str
    default_host: str

    @abstractmethod
    def generate_files(self, root: Path) -> None:
        """Generate provider-specific CI and governance files."""

    @abstractmethod
    def install(
        self, root: Path, data: dict[str, Any], paths: list[str], scope: str,
        pin: str | None, force: bool, from_local: bool,
    ) -> list[list[str]]:
        """Install a bundle and return executed transport commands."""

    @abstractmethod
    def release(self, root: Path, tag: str) -> None:
        """Publish a checked marketplace release."""


class GitHubProvider(MarketplaceProvider):
    name = "github"
    default_host = "github.com"

    def generate_files(self, root: Path) -> None:
        workflows = root / ".github/workflows"
        workflows.mkdir(parents=True, exist_ok=True)
        (workflows / "marketplace-check.yml").write_text(_CHECK_WORKFLOW, encoding="utf-8")
        (workflows / "marketplace-release.yml").write_text(_RELEASE_WORKFLOW, encoding="utf-8")
        (workflows / "marketplace-health.yml").write_text(_HEALTH_WORKFLOW, encoding="utf-8")

    def install(
        self, root: Path, data: dict[str, Any], paths: list[str], scope: str,
        pin: str | None, force: bool, from_local: bool,
    ) -> list[list[str]]:
        source = str(root.resolve()) if from_local else data["marketplace"]["repository"]
        commands: list[list[str]] = []
        run_cwd = Path.cwd() if scope == "project" else root
        for path in paths:
            selector = Path(path).name if from_local else path
            command = ["gh", "skill", "install", source, selector]
            if from_local:
                command.append("--from-local")
            command += ["--agent", "github-copilot", "--scope", scope]
            if pin:
                command += ["--pin", pin]
            if force:
                command.append("--force")
            result = subprocess.run(
                command, cwd=run_cwd, text=True, check=False, capture_output=True,
            )
            if result.returncode:
                detail = "\n".join(
                    part.strip() for part in (result.stdout, result.stderr) if part and part.strip()
                )
                raise MarketplaceError(
                    f"gh skill install failed for {path}" + (f": {detail}" if detail else "")
                )
            commands.append(command)
        return commands

    def release(self, root: Path, tag: str) -> None:
        command = ["gh", "skill", "publish", str(root.resolve()), "--tag", tag]
        result = subprocess.run(command, cwd=root, text=True, check=False)
        if result.returncode:
            raise MarketplaceError("gh skill publish failed")


class GitLabProvider(MarketplaceProvider):
    name = "gitlab"
    default_host = "gitlab.com"

    def generate_files(self, root: Path) -> None:
        (root / ".gitlab-ci.yml").write_text(_GITLAB_CI, encoding="utf-8")

    def install(
        self, root: Path, data: dict[str, Any], paths: list[str], scope: str,
        pin: str | None, force: bool, from_local: bool,
    ) -> list[list[str]]:
        source_root = root
        commands: list[list[str]] = []
        temporary: tempfile.TemporaryDirectory[str] | None = None
        try:
            if not from_local:
                marketplace = data["marketplace"]
                clone_url = f"https://{marketplace['host']}/{marketplace['repository']}.git"
                temporary = tempfile.TemporaryDirectory(prefix="acme-marketplace-")
                source_root = Path(temporary.name) / "repository"
                command = [
                    "git", "clone", "--depth", "1", "--branch", str(pin),
                    clone_url, str(source_root),
                ]
                result = subprocess.run(command, text=True, check=False)
                if result.returncode:
                    raise MarketplaceError(f"git clone failed for {clone_url} at {pin}")
                commands.append(command)
            destination_root = (
                Path.home() / ".copilot/skills" if scope == "user"
                else Path.cwd() / ".github/skills"
            )
            destination_root.mkdir(parents=True, exist_ok=True)
            for path in paths:
                source = _contained(source_root, path)
                if not source.is_dir():
                    raise MarketplaceError(f"pinned release is missing bundle skill: {path}")
                destination = destination_root / Path(path).name
                if destination.exists():
                    if not force:
                        raise MarketplaceError(
                            f"skill already installed: {destination}; use --force to replace it"
                        )
                    shutil.rmtree(destination)
                shutil.copytree(source, destination, ignore=COPY_IGNORE_PATTERNS)
            return commands
        finally:
            if temporary is not None:
                temporary.cleanup()

    def release(self, root: Path, tag: str) -> None:
        command = [
            "glab", "release", "create", tag, "--ref", "HEAD",
            "--notes", f"Governed marketplace release {tag}",
        ]
        result = subprocess.run(command, cwd=root, text=True, check=False)
        if result.returncode:
            raise MarketplaceError("glab release create failed")


PROVIDERS: dict[str, MarketplaceProvider] = {
    "github": GitHubProvider(),
    "gitlab": GitLabProvider(),
}


def _provider(data: dict[str, Any]) -> MarketplaceProvider:
    name = str(data.get("marketplace", {}).get("provider", "github")).lower()
    try:
        return PROVIDERS[name]
    except KeyError as exc:
        raise MarketplaceError(f"unsupported marketplace provider: {name}") from exc


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _require_slug(value: str, label: str) -> str:
    if not SLUG_RE.fullmatch(value):
        raise MarketplaceError(
            f"invalid {label} '{value}'; use lowercase letters, numbers, and single hyphens"
        )
    return value


def _department_options(values: list[str] | None) -> dict[str, str]:
    """Parse repeatable ``department=owner`` initialization options."""
    result: dict[str, str] = {}
    for value in values or []:
        department, separator, owner = value.partition("=")
        if not separator or not owner.strip():
            raise MarketplaceError("--department must use department=owner")
        department = _require_slug(department.strip(), "department")
        if department in result:
            raise MarketplaceError(f"duplicate department option: {department}")
        result[department] = owner.strip().lstrip("@")
    return result


def _contained(root: Path, relative: str) -> Path:
    target = (root / relative).resolve()
    resolved_root = root.resolve()
    if target == resolved_root or not target.is_relative_to(resolved_root):
        raise MarketplaceError(f"path escapes marketplace root: {relative}")
    return target


def load_manifest(root: Path) -> dict[str, Any]:
    """Load a schema-v2 marketplace manifest."""
    path = root / "registry.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise MarketplaceError(f"registry.json not found in {root}") from exc
    except json.JSONDecodeError as exc:
        raise MarketplaceError(f"invalid registry.json: {exc}") from exc
    if data.get("schema_version") != SCHEMA_VERSION:
        raise MarketplaceError("marketplace requires schema_version 2; migrate schema-v1 explicitly")
    marketplace = data.setdefault("marketplace", {})
    marketplace.setdefault("provider", "github")
    provider = _provider(data)
    marketplace.setdefault("host", provider.default_host)
    supported = marketplace.get("supported_platforms", [])
    if isinstance(supported, list):
        marketplace["supported_platforms"] = sorted({
            normalize_platform_name(value) for value in supported if str(value).strip()
        })
    return data


def save_manifest(root: Path, data: dict[str, Any]) -> None:
    """Atomically save the marketplace manifest."""
    path = root / "registry.json"
    temporary = root / "registry.json.tmp"
    temporary.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def migrate_v1_registry(
    source: Path, repository: str, provider: str = "github", host: str | None = None,
) -> dict[str, Any]:
    """Convert a legacy skill_registry.py manifest without silently approving it."""
    try:
        old = json.loads((source / "registry.json").read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        raise MarketplaceError(f"cannot read schema-v1 registry at {source}: {exc}") from exc
    registry = old.get("registry", {})
    if str(registry.get("schema_version", "1")) != "1":
        raise MarketplaceError("--from-registry accepts only schema-v1 registries")
    skills: list[dict[str, Any]] = []
    for item in old.get("skills", []):
        department = _legacy_department(item)
        author = str(item.get("author", "")).strip()
        legacy_path = item.get("path", f"skills/{item.get('name', '')}")
        governed_path = f"skills/{department}/{item.get('name', '')}"
        skills.append({
            "name": item.get("name", ""),
            "department": department,
            "author": author,
            "owners": [author or department],
            "approval_status": "draft",
            "version": item.get("version", "0.0.0"),
            "description": item.get("description", ""),
            "license": item.get("license", ""),
            "path": governed_path,
            "repository": repository,
            "provenance": {
                "migrated_from_schema": 1, "legacy_path": legacy_path,
                "legacy_published": item.get("published"),
            },
            "quality": {
                "validation": item.get("validation", {"valid": False}),
                "security": {
                    "passed": bool(item.get("security", {}).get("clean", False)),
                    "legacy": item.get("security", {}),
                },
                "pipeline": {"passed": False, "reason": "not run during migration"},
                "evals": {"passed": False, "reason": "not run during migration"},
            },
        })
    return {
        "schema_version": SCHEMA_VERSION,
        "marketplace": {
            "name": registry.get("name", "ACME Skills"),
            "repository": repository,
            "provider": provider,
            "host": host or PROVIDERS[provider].default_host,
            "created": registry.get("created", _now()),
            "migrated_at": _now(),
        },
        "skills": skills,
        "bundles": {},
    }


def _legacy_department(item: dict[str, Any]) -> str:
    author = str(item.get("author", "")).strip().lower()
    candidate = re.sub(r"[^a-z0-9]+", "-", author).strip("-") or "unassigned"
    return candidate if SLUG_RE.fullmatch(candidate) else "unassigned"


def init_marketplace(
    root: Path, name: str, repository: str, from_registry: Path | None = None,
    *, provider: str = "github", host: str | None = None,
    departments: dict[str, str] | None = None, approvers: list[str] | None = None,
    supported_platforms: list[str] | None = None, starter_bundles: list[str] | None = None,
) -> dict[str, Any]:
    """Create the repository scaffold, optionally importing schema-v1 files."""
    if not re.fullmatch(r"[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)+", repository):
        raise MarketplaceError("repository must use OWNER/REPO or GROUP/SUBGROUP/REPO format")
    provider = provider.lower()
    if provider not in PROVIDERS:
        raise MarketplaceError(f"unsupported marketplace provider: {provider}")
    resolved_host = (host or PROVIDERS[provider].default_host).strip().lower()
    if not re.fullmatch(r"[a-z0-9.-]+(?::\d+)?", resolved_host):
        raise MarketplaceError("host must be a hostname, optionally followed by a port")
    if (root / "registry.json").exists():
        raise MarketplaceError(f"marketplace already exists at {root}")
    departments = departments or {}
    normalized_departments = {
        _require_slug(department, "department"): str(owner).strip().lstrip("@")
        for department, owner in departments.items()
    }
    if any(not owner for owner in normalized_departments.values()):
        raise MarketplaceError("every department must declare a non-empty owner")
    normalized_approvers = sorted({str(value).strip().lstrip("@") for value in (approvers or []) if str(value).strip()})
    normalized_platforms = sorted({
        _require_slug(normalize_platform_name(value), "supported platform")
        for value in (supported_platforms or [])
    })
    normalized_bundles = sorted({_require_slug(value, "starter bundle") for value in (starter_bundles or [])})
    root.mkdir(parents=True, exist_ok=True)
    (root / "skills").mkdir(exist_ok=True)
    (root / "bundles").mkdir(exist_ok=True)
    if from_registry:
        data = migrate_v1_registry(from_registry, repository, provider, resolved_host)
        data["marketplace"]["name"] = name
        for entry in data["skills"]:
            source = _contained(from_registry, entry["provenance"]["legacy_path"])
            destination = _contained(root, entry["path"])
            if source.is_dir():
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copytree(source, destination, ignore=COPY_IGNORE_PATTERNS)
    else:
        data = {
            "schema_version": SCHEMA_VERSION,
            "marketplace": {
                "name": name, "repository": repository, "provider": provider,
                "host": resolved_host, "created": _now(),
                "active_owners": sorted(set(normalized_departments.values())),
                "departments": normalized_departments,
                "approvers": normalized_approvers,
                "supported_platforms": normalized_platforms,
                "resolver_policies": [],
                "resolver_attestation": {
                    "issuer": "local-development", "audience": repository,
                    "max_ttl_seconds": 300,
                },
            },
            "skills": [],
            "bundles": {bundle: [] for bundle in normalized_bundles},
        }
    marketplace = data["marketplace"]
    marketplace.setdefault("resolver_policies", [])
    marketplace.setdefault("resolver_attestation", {
        "issuer": "local-development", "audience": repository, "max_ttl_seconds": 300,
    })
    if normalized_departments:
        marketplace["departments"] = normalized_departments
        marketplace["active_owners"] = sorted(set(normalized_departments.values()))
    if normalized_approvers:
        marketplace["approvers"] = normalized_approvers
    if normalized_platforms:
        marketplace["supported_platforms"] = normalized_platforms
    for bundle in normalized_bundles:
        data.setdefault("bundles", {}).setdefault(bundle, [])
    save_manifest(root, data)
    generate_repository_files(root, data)
    return data


def create_marketplace_interactive(args: argparse.Namespace) -> Path:
    """Collect the small set of human decisions and create a marketplace."""
    def ask(label: str, default: str = "") -> str:
        value = getattr(args, label, None) or input(f"{label} [{default}]: ").strip()
        return value or default
    name = ask("name", "My Skills Marketplace")
    repository = ask("repository")
    if not repository:
        raise MarketplaceError("repository is required (for example owner/skills)")
    provider = ask("provider", "github")
    marketplace = Path(ask("marketplace", "./skills-marketplace")).resolve()
    department = ask("department", "general")
    owner = ask("owner", "marketplace-owner")
    bundle = ask("bundle", "starter")
    init_marketplace(marketplace, name, repository, provider=provider,
                     departments={department: owner},
                     approvers=[owner],
                     supported_platforms=["github-copilot"],
                     starter_bundles=[bundle])
    print(f"Marketplace initialized at {marketplace}")
    print(f"Next: add a skill with `python3 scripts/team_marketplace.py add ./skill --department {department} --bundle {bundle} --marketplace {marketplace}`")
    return marketplace


def _metadata(skill: Path) -> dict[str, Any]:
    skill_md = skill / "SKILL.md"
    if not skill_md.exists():
        raise MarketplaceError(f"SKILL.md not found in {skill}")
    doc = SkillDoc.from_text(skill_md.read_text(encoding="utf-8"))
    metadata = doc.metadata
    owners = metadata.get("owners", [])
    if isinstance(owners, str):
        owners = [part.strip() for part in owners.strip("[]").split(",") if part.strip()]
    if not owners:
        owners = doc.list_of_scalars("metadata", "owners")
    discovery: dict[str, Any] = {}
    discovery_path = skill / "discovery.json"
    if discovery_path.exists():
        try:
            loaded = json.loads(discovery_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise MarketplaceError(f"invalid discovery.json: {exc}") from exc
        if not isinstance(loaded, dict):
            raise MarketplaceError("discovery.json must contain a JSON object")
        discovery = loaded
    elif metadata.get("discovery"):
        try:
            loaded = json.loads(metadata["discovery"])
        except (json.JSONDecodeError, TypeError) as exc:
            raise MarketplaceError("metadata.discovery must be inline JSON or use discovery.json") from exc
        if isinstance(loaded, dict):
            discovery = loaded
    return {
        "name": (doc.name or "").strip(),
        "description": (doc.description or "").strip(),
        "license": (doc.license or "").strip(),
        "author": str(metadata.get("author", "")).strip(),
        "owners": [str(owner).strip().lstrip("@") for owner in owners],
        "approval_status": str(metadata.get("approval_status", "draft")).strip().lower(),
        "lifecycle": str(metadata.get("lifecycle") or metadata.get("approval_status", "draft")).strip().lower(),
        "version": str(metadata.get("version") or doc.field("version") or "0.0.0").strip(),
        "allowed_tools": doc.field("allowed-tools") or "",
        "discovery": discovery,
    }


def _gate_skill(skill: Path) -> dict[str, Any]:
    validation = validate_skill(str(skill))
    scan = security_scan(str(skill))
    high = [issue for issue in scan["issues"] if issue.get("severity") == "high"]
    pipeline = check_pipeline(skill)
    eval_runner = skill / "scripts/run_evals.py"
    if eval_runner.exists():
        validation_result = subprocess.run(
            [sys.executable, str(eval_runner), "--validate"], cwd=skill,
            capture_output=True, text=True, check=False,
        )
        gate_result = None
        if validation_result.returncode == 0:
            gate_result = subprocess.run(
                [sys.executable, str(eval_runner), "--rollout", "--include-holdout"], cwd=skill,
                capture_output=True, text=True, check=False,
            )
        evals = {
            "passed": validation_result.returncode == 0 and gate_result is not None and gate_result.returncode == 0,
            "validation_output": ((validation_result.stdout or "") + (validation_result.stderr or "")).strip(),
            "gate_output": (
                ((gate_result.stdout or "") + (gate_result.stderr or "")).strip()
                if gate_result is not None else "not run"
            ),
        }
    else:
        evals = {"passed": False, "status": "required"}
    return {
        "validation": {
            "valid": validation["valid"], "errors": validation["errors"],
            "warnings": validation["warnings"],
        },
        "security": {
            "passed": scan["clean"], "high_findings": high, "issues": scan["issues"],
        },
        "pipeline": {"passed": not pipeline["errors"], **pipeline},
        "evals": evals,
        "checked_at": _now(),
    }


def _source_commit(skill: Path) -> str:
    """Resolve the exact clean Git commit containing a submitted skill."""
    result = subprocess.run(
        ["git", "-C", str(skill), "rev-parse", "HEAD"], capture_output=True,
        text=True, check=False,
    )
    commit = result.stdout.strip()
    if result.returncode or not commit:
        raise MarketplaceError("skill submission must belong to a Git commit")
    dirty = subprocess.run(
        ["git", "-C", str(skill), "status", "--porcelain", "--untracked-files=all", "--", "."],
        capture_output=True, text=True, check=False,
    )
    lines = [
        line for line in dirty.stdout.splitlines()
        if ATTESTATION_FILE not in line and "__pycache__/" not in line
        and not line.rstrip().endswith((".pyc", ".pyo", "VERIFICATION.md"))
    ]
    if dirty.returncode or lines:
        raise MarketplaceError("skill submission has uncommitted files; attest the exact committed contents")
    return commit


def _load_attestation(skill: Path, meta: dict[str, Any], commit: str) -> dict[str, Any]:
    path = skill / ATTESTATION_FILE
    try:
        artifact = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise MarketplaceError(f"representative-run attestation is required: {path}") from exc
    except json.JSONDecodeError as exc:
        raise MarketplaceError(f"invalid representative-run attestation: {exc}") from exc
    errors = validate_attestation(
        artifact, expected_skill=meta["name"], expected_version=meta["version"],
        expected_commit=commit,
    )
    if errors:
        raise MarketplaceError("attestation gate failed: " + "; ".join(errors))
    return artifact


def attest_skill(skill: Path, run_id: str, completed_at: str) -> Path:
    """Run mandatory eval gates and write commit-bound representative evidence."""
    meta = _metadata(skill)
    commit = _source_commit(skill)
    quality = _gate_skill(skill)
    failures = _quality_errors(meta["name"], quality)
    if failures:
        raise MarketplaceError("; ".join(failures))
    report = render_report(skill, {"specification": quality["validation"]["valid"], "security": quality["security"]["passed"], "pipeline": quality["pipeline"]["passed"], "evals": quality["evals"]["passed"]}, {"passed": 0, "failed": 0, "errors": 0, "regressions": 0, "clean": quality["evals"]["passed"]}, "representative", [])
    (skill / "VERIFICATION.md").write_text(report, encoding="utf-8")
    artifact = create_attestation(
        skill_name=meta["name"], skill_version=meta["version"], commit_sha=commit,
        eval_evidence={
            "runner": "scripts/run_evals.py", "executable": True,
            "validation_passed": True, "run_passed": True,
            "checked_at": quality["checked_at"],
        },
        representative_run={
            "passed": True, "run_id": run_id, "completed_at": completed_at,
            "safe_mode": "operator-confirmed",
        },
    )
    path = skill / ATTESTATION_FILE
    path.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _blocked_allowed_tools(value: Any) -> set[str]:
    if isinstance(value, list):
        tokens = {str(item).lower() for item in value}
    else:
        tokens = set(re.findall(r"[a-zA-Z0-9_-]+", str(value).lower()))
    return tokens & BLOCKED_TOOLS


@_serialized_mutation
def add_skill(root: Path, skill: Path, department: str, bundle: str) -> dict[str, Any]:
    """Gate and copy one approved skill into its department namespace."""
    department = _require_slug(department, "department")
    bundle = _require_slug(bundle, "bundle")
    if not skill.is_dir():
        raise MarketplaceError(f"skill path is not a directory: {skill}")
    meta = _metadata(skill)
    if not meta["name"]:
        raise MarketplaceError("skill name is missing")
    if _blocked_allowed_tools(meta["allowed_tools"]):
        raise MarketplaceError("pre-approved shell or bash access is forbidden; runtime permission is required")
    if not meta["owners"]:
        raise MarketplaceError("skill metadata must declare at least one owner")
    if not SEMVER_RE.fullmatch(meta["version"]):
        raise MarketplaceError("skill metadata.version must be semantic versioning, such as 1.2.0")
    if meta["lifecycle"] != APPROVED:
        raise MarketplaceError("skill lifecycle must be approved before marketplace intake")
    try:
        normalized_discovery = require_operating_contract({
            "name": meta["name"], "version": meta["version"], "discovery": meta["discovery"],
        })
    except DiscoveryError as exc:
        raise MarketplaceError(f"invalid discovery metadata: {exc}") from exc
    commit = _source_commit(skill)
    attestation = _load_attestation(skill, meta, commit)
    quality = _gate_skill(skill)
    failures = _quality_errors(meta["name"], quality)
    if failures:
        raise MarketplaceError("; ".join(failures))
    verification = verification_errors(skill)
    if verification:
        raise MarketplaceError(f"{meta['name']}: verification gate failed: " + "; ".join(verification))
    data = load_manifest(root)
    identity = (department, meta["name"])
    if any((item.get("department"), item.get("name")) == identity for item in data["skills"]):
        raise MarketplaceError(f"duplicate skill identity: {department}/{meta['name']}")
    relative = f"skills/{department}/{meta['name']}"
    destination = _contained(root, relative)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(skill, destination, ignore=COPY_IGNORE_PATTERNS)
    entry = {
        "name": meta["name"], "department": department, "author": meta["author"],
        "owners": meta["owners"], "approval_status": meta["approval_status"],
        "lifecycle": meta["lifecycle"],
        "version": meta["version"], "description": meta["description"],
        "license": meta["license"], "path": relative,
        "repository": data["marketplace"]["repository"],
        "provenance": {"source": str(skill.resolve()), "commit_sha": commit, "added_at": _now()},
        "attestation": attestation,
        "discovery": meta["discovery"] if isinstance(meta["discovery"], dict) else {},
        "compatibility": normalized_discovery["compatibility"],
        "quality": quality,
        "lineage_id": secrets.token_hex(16),
    }
    data["skills"].append(entry)
    active_owners = data["marketplace"].setdefault("active_owners", [])
    for owner in meta["owners"]:
        if owner not in active_owners:
            active_owners.append(owner)
    active_owners.sort()
    paths = data.setdefault("bundles", {}).setdefault(bundle, [])
    if relative not in paths:
        paths.append(relative)
        paths.sort()
    save_manifest(root, data)
    generate_repository_files(root, data)
    return entry


def _quality_errors(name: str, quality: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if not quality.get("validation", {}).get("valid", False):
        details = quality.get("validation", {}).get("errors", [])
        errors.append(f"{name}: validation gate failed: " + "; ".join(details or ["no details reported"]))
    if not quality.get("security", {}).get("passed", False):
        findings = quality.get("security", {}).get("high_findings", [])
        details = [str(item.get("message") or item) for item in findings]
        errors.append(f"{name}: security gate failed: " + "; ".join(details or ["scan reported findings"]))
    if not quality.get("pipeline", {}).get("passed", False):
        details = quality.get("pipeline", {}).get("errors", [])
        errors.append(f"{name}: pipeline gate failed: " + "; ".join(details or ["no details reported"]))
    if not quality.get("evals", {}).get("passed", False):
        gate = quality.get("evals", {})
        details = [str(gate.get(key, "")).strip() for key in ("validation_output", "gate_output")]
        errors.append(
            f"{name}: evals gate failed: "
            + "; ".join([item for item in details if item] or ["no details reported"])
        )
    return errors


def _compare_semver(left: str, right: str) -> int:
    """Compare validated semantic versions, including prerelease precedence."""
    pattern = re.compile(
        r"^(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z.-]+))?$"
    )
    left_match, right_match = pattern.fullmatch(left), pattern.fullmatch(right)
    if left_match is None or right_match is None:
        raise MarketplaceError("skill versions must use semantic versioning")
    left_core = tuple(int(left_match.group(index)) for index in range(1, 4))
    right_core = tuple(int(right_match.group(index)) for index in range(1, 4))
    if left_core != right_core:
        return 1 if left_core > right_core else -1
    left_pre, right_pre = left_match.group(4), right_match.group(4)
    if left_pre is None or right_pre is None:
        if left_pre == right_pre:
            return 0
        return 1 if left_pre is None else -1
    left_parts, right_parts = left_pre.split("."), right_pre.split(".")
    for left_part, right_part in zip(left_parts, right_parts):
        if left_part == right_part:
            continue
        left_numeric, right_numeric = left_part.isdigit(), right_part.isdigit()
        if left_numeric and right_numeric:
            return 1 if int(left_part) > int(right_part) else -1
        if left_numeric != right_numeric:
            return -1 if left_numeric else 1
        return 1 if left_part > right_part else -1
    if len(left_parts) == len(right_parts):
        return 0
    return 1 if len(left_parts) > len(right_parts) else -1


@_serialized_mutation
def update_skill(root: Path, skill: Path, department: str) -> dict[str, Any]:
    """Replace one marketplace skill with a fully gated, strictly newer version."""
    department = _require_slug(department, "department")
    if not skill.is_dir():
        raise MarketplaceError(f"skill path is not a directory: {skill}")
    meta = _metadata(skill)
    if not meta["name"]:
        raise MarketplaceError("skill name is missing")
    if _blocked_allowed_tools(meta["allowed_tools"]):
        raise MarketplaceError("pre-approved shell or bash access is forbidden; runtime permission is required")
    if not meta["owners"]:
        raise MarketplaceError("skill metadata must declare at least one owner")
    if not SEMVER_RE.fullmatch(meta["version"]):
        raise MarketplaceError("skill metadata.version must be semantic versioning, such as 1.2.0")
    if meta["lifecycle"] != APPROVED:
        raise MarketplaceError("updated skill lifecycle must be approved before marketplace intake")

    data = load_manifest(root)
    existing = next(
        (
            item for item in data["skills"]
            if item.get("department") == department and item.get("name") == meta["name"]
        ),
        None,
    )
    if existing is None:
        raise MarketplaceError(
            f"skill not found for update: {department}/{meta['name']}; use add for first intake"
        )
    if _compare_semver(meta["version"], str(existing.get("version", ""))) <= 0:
        raise MarketplaceError(
            f"update version {meta['version']} must be strictly newer than {existing.get('version')}"
        )

    try:
        normalized_discovery = require_operating_contract({
            "name": meta["name"], "version": meta["version"], "discovery": meta["discovery"],
        })
    except DiscoveryError as exc:
        raise MarketplaceError(f"invalid discovery metadata: {exc}") from exc
    commit = _source_commit(skill)
    attestation = _load_attestation(skill, meta, commit)
    quality = _gate_skill(skill)
    failures = _quality_errors(meta["name"], quality)
    if failures:
        raise MarketplaceError("; ".join(failures))

    relative = str(existing["path"])
    expected = f"skills/{department}/{meta['name']}"
    if relative != expected:
        raise MarketplaceError(f"existing manifest path must be {expected}")
    destination = _contained(root, relative)
    if not destination.is_dir():
        raise MarketplaceError(f"existing skill directory is missing: {relative}")
    discovery = json.loads(json.dumps(meta["discovery"])) if isinstance(meta["discovery"], dict) else {}
    if isinstance(discovery.get("compatibility"), dict):
        discovery["compatibility"]["certified"] = []
    replacement = {
        "name": meta["name"], "department": department, "author": meta["author"],
        "owners": meta["owners"], "approval_status": meta["approval_status"],
        "lifecycle": APPROVED, "version": meta["version"],
        "description": meta["description"], "license": meta["license"],
        "path": relative, "repository": data["marketplace"]["repository"],
        "provenance": {
            "source": str(skill.resolve()), "commit_sha": commit, "updated_at": _now(),
            "previous_version": existing.get("version"),
        },
        "attestation": attestation, "discovery": discovery,
        "compatibility": {
            "declared": normalized_discovery["compatibility"]["declared"], "certified": [],
        },
        "quality": quality,
        "lineage_id": existing.get("lineage_id") or secrets.token_hex(16),
    }

    manifest_before = (root / "registry.json").read_bytes()
    staging = Path(tempfile.mkdtemp(prefix=f".{meta['name']}-update-", dir=destination.parent))
    backup = destination.parent / f".{meta['name']}-backup-{secrets.token_hex(8)}"
    try:
        shutil.copytree(skill, staging, dirs_exist_ok=True, ignore=COPY_IGNORE_PATTERNS)
        destination.replace(backup)
        staging.replace(destination)
        existing.clear()
        existing.update(replacement)
        save_manifest(root, data)
        generate_repository_files(root, data)
    except Exception:
        if destination.exists():
            shutil.rmtree(destination)
        if backup.exists():
            backup.replace(destination)
        (root / "registry.json").write_bytes(manifest_before)
        raise
    finally:
        if staging.exists():
            shutil.rmtree(staging)
        if backup.exists():
            shutil.rmtree(backup)
    return replacement


@_serialized_mutation
def recreate_skill(root: Path, skill: Path, department: str, reason: str) -> dict[str, Any]:
    """Replace a retired identity with a fresh 1.0.0 lineage and a minimal tombstone."""
    department = _require_slug(department, "department")
    reason = reason.strip()
    if not reason:
        raise MarketplaceError("recreate requires a non-empty reason")
    if not skill.is_dir():
        raise MarketplaceError(f"skill path is not a directory: {skill}")
    meta = _metadata(skill)
    if meta["version"] != "1.0.0":
        raise MarketplaceError("recreated skill must start at version 1.0.0")
    data = load_manifest(root)
    matches = [
        item for item in data["skills"]
        if item.get("department") == department and item.get("name") == meta["name"]
    ]
    if len(matches) != 1:
        raise MarketplaceError(
            f"recreate requires exactly one unambiguous predecessor: {department}/{meta['name']}"
        )
    predecessor = matches[0]
    if predecessor.get("lifecycle") != "retired":
        raise MarketplaceError("recreate requires the predecessor lifecycle to be retired")
    predecessor_lineage = predecessor.get("lineage_id")
    if not isinstance(predecessor_lineage, str) or not predecessor_lineage:
        # Schema-v2 marketplaces created before lineage support are migrated at
        # the recreate boundary. The generated identity becomes immutable in the
        # committed tombstone; no operator registry edit is required.
        predecessor_lineage = secrets.token_hex(16)
    if _blocked_allowed_tools(meta["allowed_tools"]):
        raise MarketplaceError("pre-approved shell or bash access is forbidden; runtime permission is required")
    if not meta["owners"] or meta["lifecycle"] != APPROVED:
        raise MarketplaceError("recreated skill must be approved and declare at least one owner")
    try:
        normalized = require_operating_contract({
            "name": meta["name"], "version": meta["version"], "discovery": meta["discovery"],
        })
    except DiscoveryError as exc:
        raise MarketplaceError(f"invalid discovery metadata: {exc}") from exc
    commit = _source_commit(skill)
    attestation = _load_attestation(skill, meta, commit)
    quality = _gate_skill(skill)
    failures = _quality_errors(meta["name"], quality)
    if failures:
        raise MarketplaceError("; ".join(failures))
    relative = f"skills/{department}/{meta['name']}"
    destination = _contained(root, relative)
    bundles = [name for name, paths in data.get("bundles", {}).items() if relative in paths]
    tombstone = {
        "name": predecessor["name"], "department": department,
        "lineage_id": predecessor_lineage, "version": predecessor.get("version"),
        "retired_at": _now(), "recreate_reason": reason,
    }
    new_lineage = secrets.token_hex(16)
    replacement = {
        "name": meta["name"], "department": department, "author": meta["author"],
        "owners": meta["owners"], "approval_status": APPROVED, "lifecycle": APPROVED,
        "version": "1.0.0", "description": meta["description"], "license": meta["license"],
        "path": relative, "repository": data["marketplace"]["repository"],
        "lineage_id": new_lineage, "predecessor_lineage_id": predecessor_lineage,
        "recreate_reason": reason,
        "provenance": {"source": str(skill.resolve()), "commit_sha": commit, "recreated_at": _now()},
        "attestation": attestation, "discovery": meta["discovery"],
        "compatibility": {"declared": normalized["compatibility"]["declared"], "certified": []},
        "quality": quality,
    }
    staging = Path(tempfile.mkdtemp(prefix=f".{meta['name']}-recreate-", dir=destination.parent))
    backup = destination.parent / f".{meta['name']}-backup-{secrets.token_hex(8)}"
    manifest_before = (root / "registry.json").read_bytes()
    try:
        shutil.copytree(skill, staging, dirs_exist_ok=True, ignore=COPY_IGNORE_PATTERNS)
        destination.replace(backup)
        staging.replace(destination)
        predecessor.clear()
        predecessor.update(replacement)
        data.setdefault("history", []).append(tombstone)
        for bundle in bundles:
            if relative not in data["bundles"][bundle]:
                data["bundles"][bundle].append(relative)
        save_manifest(root, data)
        generate_repository_files(root, data)
    except Exception:
        if destination.exists():
            shutil.rmtree(destination)
        if backup.exists():
            backup.replace(destination)
        (root / "registry.json").write_bytes(manifest_before)
        raise
    finally:
        if staging.exists():
            shutil.rmtree(staging)
        if backup.exists():
            shutil.rmtree(backup)
    return replacement


def check_marketplace(
    root: Path, *, refresh: bool = True, require_published: bool = False,
    require_reliability: bool = False,
) -> list[str]:
    """Return every release-blocking inconsistency; an empty list is releasable.

    ``require_reliability`` additionally demands agent-run (Caliper) checks behind every
    certification of a platform Caliper can drive; see marketplace_reliability.py.
    """
    data = load_manifest(root)
    errors: list[str] = []
    if require_published and not data.get("skills"):
        errors.append("release requires at least one published skill")
    try:
        _provider(data)
    except MarketplaceError as exc:
        errors.append(str(exc))
    identities: set[tuple[str, str]] = set()
    known_paths: set[str] = set()
    for entry in data["skills"]:
        identity = (entry.get("department", ""), entry.get("name", ""))
        if identity in identities:
            errors.append(f"duplicate skill identity: {identity[0]}/{identity[1]}")
        identities.add(identity)
        path = str(entry.get("path", ""))
        if path in known_paths:
            errors.append(f"duplicate skill path: {path}")
        known_paths.add(path)
        if entry.get("lifecycle", entry.get("approval_status")) not in {APPROVED, "published"}:
            state = entry.get("lifecycle", entry.get("approval_status", "draft"))
            errors.append(f"{identity[1]}: lifecycle {state} does not permit release")
        if require_published and entry.get("lifecycle", entry.get("approval_status")) != "published":
            errors.append(f"{identity[1]}: release requires committed published lifecycle")
        if not entry.get("owners"):
            errors.append(f"{identity[1]}: owners are required")
        quality = entry.get("quality", {})
        if not refresh:
            errors.extend(_quality_errors(identity[1], quality))
        expected = f"skills/{identity[0]}/{identity[1]}"
        if path != expected:
            errors.append(f"{identity[1]}: manifest path must be {expected}")
        try:
            skill = _contained(root, path)
        except MarketplaceError as exc:
            errors.append(str(exc))
            continue
        if not skill.is_dir():
            errors.append(f"{identity[1]}: skill directory is missing")
            continue
        meta = _metadata(skill)
        if meta["name"] != identity[1]:
            errors.append(f"{identity[1]}: SKILL.md name is inconsistent")
        for field in ("author", "owners", "approval_status", "version"):
            if meta[field] != entry.get(field):
                errors.append(f"{identity[1]}: SKILL.md {field} is inconsistent with registry.json")
        try:
            normalized_discovery = require_operating_contract({
                "name": meta["name"], "version": meta["version"], "discovery": meta["discovery"],
            })
        except DiscoveryError as exc:
            errors.append(f"{identity[1]}: invalid discovery metadata: {exc}")
        else:
            existing = entry.get("compatibility", {})
            certified = existing.get("certified", []) if isinstance(existing, dict) else []
            entry["compatibility"] = {
                "declared": normalized_discovery["compatibility"]["declared"],
                "certified": certified,
            }
            if require_published:
                stale_semantics = semantic_freshness_failures(
                    normalized_discovery["semantic_contract"], date.today()
                )
                if stale_semantics:
                    errors.append(
                        f"{identity[1]}: release requires current semantic owner review for: "
                        f"{', '.join(stale_semantics)}"
                    )
                declared = set(entry["compatibility"]["declared"])
                current_certified = {
                    normalize_platform_name(str(item.get("platform", ""))) for item in certified
                    if isinstance(item, dict) and item.get("passed") is True
                    and str(item.get("version", item.get("skill_version", ""))) == str(entry.get("version", ""))
                }
                missing = sorted(declared - current_certified)
                if missing:
                    errors.append(
                        f"{identity[1]}: release requires current-version compatibility "
                        f"certification for: {', '.join(missing)}"
                    )
            if require_reliability:
                errors.extend(f"{identity[1]}: {failure}" for failure in reliability_check_failures(entry))
        commit = entry.get("provenance", {}).get("commit_sha", "")
        errors.extend(
            f"{identity[1]}: {error}" for error in validate_attestation(
                entry.get("attestation"), expected_skill=identity[1],
                expected_version=entry.get("version", ""), expected_commit=commit,
            )
        )
        if _blocked_allowed_tools(meta["allowed_tools"]):
            errors.append(f"{identity[1]}: pre-approved shell access is forbidden")
        quality = _gate_skill(skill) if refresh else quality
        if refresh:
            entry["quality"] = quality
            errors.extend(_quality_errors(identity[1], quality))
    for bundle, paths in data.get("bundles", {}).items():
        if not SLUG_RE.fullmatch(bundle):
            errors.append(f"invalid bundle name: {bundle}")
        for path in paths:
            if path not in known_paths:
                errors.append(f"bundle {bundle} references unknown skill: {path}")
        bundle_file = root / "bundles" / f"{bundle}.json"
        expected_bundle = {"name": bundle, "skills": sorted(paths)}
        try:
            actual_bundle = json.loads(bundle_file.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            errors.append(f"bundle manifest is missing or invalid: bundles/{bundle}.json")
        else:
            if actual_bundle != expected_bundle:
                errors.append(f"bundle manifest is inconsistent: bundles/{bundle}.json")
    if require_published:
        try:
            portfolio = evaluate_portfolio(data.get("skills", []))
        except DiscoveryError as exc:
            errors.append(f"portfolio routing contract is invalid: {exc}")
        else:
            for failure in portfolio["failures"]:
                errors.append(
                    f"portfolio routing: {failure['skill']} {failure['expectation']} "
                    f"failed for {failure['query']!r}; observed {failure['observed_owner']}"
                )
    return errors


def _skill_artifact_sha256(skill: Path) -> str:
    """Hash a skill directory deterministically without including local Git state."""
    digest = hashlib.sha256()
    files = sorted(
        path for path in skill.rglob("*")
        if path.is_file() and ".git" not in path.relative_to(skill).parts
        and "__pycache__" not in path.relative_to(skill).parts
    )
    for path in files:
        relative = path.relative_to(skill).as_posix().encode("utf-8")
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        content = path.read_bytes()
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
    return digest.hexdigest()


def _current_certification(entry: dict[str, Any], platform: str) -> dict[str, Any] | None:
    """Return passing certification for the entry's exact current version."""
    certified = entry.get("compatibility", {}).get("certified", [])
    if not isinstance(certified, list):
        return None
    for record in certified:
        if not isinstance(record, dict) or record.get("passed") is not True:
            continue
        if normalize_platform_name(str(record.get("platform", ""))) != platform:
            continue
        if str(record.get("version", record.get("skill_version", ""))) == str(entry.get("version", "")):
            return record
    return None


def _marketplace_commit(root: Path) -> str | None:
    result = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        capture_output=True, text=True, check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else None


POLICY_SELECTOR_FIELDS = ("subjects", "agents", "projects", "environments", "platforms", "skills")


def _policy_revision(rules: list[dict[str, Any]]) -> str:
    payload = json.dumps(rules, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def _validate_resolver_policies(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise MarketplaceError("resolver policies must be a JSON array")
    ids: set[str] = set()
    rules: list[dict[str, Any]] = []
    for raw in value:
        if not isinstance(raw, dict):
            raise MarketplaceError("each resolver policy must be an object")
        rule_id = raw.get("id")
        if not isinstance(rule_id, str) or not SLUG_RE.fullmatch(rule_id) or rule_id in ids:
            raise MarketplaceError("each resolver policy needs a unique slug id")
        effect = raw.get("effect")
        if effect not in {"allow", "deny"}:
            raise MarketplaceError(f"resolver policy {rule_id} effect must be allow or deny")
        rule = {"id": rule_id, "effect": effect}
        for field in POLICY_SELECTOR_FIELDS:
            selector = raw.get(field, ["*"])
            if not isinstance(selector, list) or not selector or any(not isinstance(item, str) or not item for item in selector):
                raise MarketplaceError(f"resolver policy {rule_id} {field} must be a non-empty string array")
            if field == "platforms":
                selector = ["*" if item == "*" else normalize_platform_name(item) for item in selector]
            rule[field] = sorted(set(selector))
        ids.add(rule_id)
        rules.append(rule)
    return sorted(rules, key=lambda rule: rule["id"])


def apply_resolver_policies(root: Path, policies: Any) -> dict[str, Any]:
    """Validate and atomically persist resolver rules in the marketplace manifest."""
    rules = _validate_resolver_policies(policies)
    data = load_manifest(root)
    data["marketplace"]["resolver_policies"] = rules
    data["marketplace"]["resolver_policy_revision"] = _policy_revision(rules)
    save_manifest(root, data)
    return {"rules": rules, "revision": data["marketplace"]["resolver_policy_revision"]}


def _selector_matches(values: set[str], selector: list[str]) -> bool:
    return "*" in selector or bool(values.intersection(selector))


def _policy_decision(
    rules: list[dict[str, Any]], *, user: str, groups: list[str], agent: str,
    project: str, environment: str, platform: str, skill_id: str,
) -> tuple[bool, list[str]]:
    subjects = {user, *(f"group:{group}" for group in groups)}
    matched = [
        rule for rule in rules
        if _selector_matches(subjects, rule["subjects"])
        and _selector_matches({agent}, rule["agents"])
        and _selector_matches({project}, rule["projects"])
        and _selector_matches({environment}, rule["environments"])
        and _selector_matches({platform}, rule["platforms"])
        and _selector_matches({skill_id}, rule["skills"])
    ]
    ids = [rule["id"] for rule in matched]
    return bool(matched) and not any(rule["effect"] == "deny" for rule in matched) and any(
        rule["effect"] == "allow" for rule in matched
    ), ids


def _parse_attestation_time(value: Any, label: str) -> datetime:
    if not isinstance(value, str):
        raise MarketplaceError(f"attestation {label} must be an RFC3339 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise MarketplaceError(f"attestation {label} must be an RFC3339 timestamp") from exc
    if parsed.tzinfo is None:
        raise MarketplaceError(f"attestation {label} must include a timezone")
    return parsed.astimezone(timezone.utc)


def verify_execution_attestation(root: Path, attestation: Any, secret: str | None = None) -> dict[str, Any]:
    """Verify a signed, short-lived identity and managed-device assertion."""
    if not isinstance(attestation, dict):
        raise MarketplaceError("attestation must be a JSON object")
    signature = attestation.get("signature")
    if not isinstance(signature, str) or not re.fullmatch(r"[0-9a-f]{64}", signature):
        raise MarketplaceError("attestation signature must be a lowercase SHA-256 HMAC")
    key = secret if secret is not None else os.environ.get("SKILL_RESOLVER_ATTESTATION_SECRET")
    if not key:
        raise MarketplaceError("SKILL_RESOLVER_ATTESTATION_SECRET is required to verify attestations")
    unsigned = {field: value for field, value in attestation.items() if field != "signature"}
    canonical = json.dumps(unsigned, sort_keys=True, separators=(",", ":")).encode("utf-8")
    expected = hmac.new(key.encode("utf-8"), canonical, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected):
        raise MarketplaceError("attestation signature is invalid")
    data = load_manifest(root)
    config = data["marketplace"].get("resolver_attestation", {})
    if attestation.get("issuer") != config.get("issuer"):
        raise MarketplaceError("attestation issuer is not trusted by this marketplace")
    if attestation.get("audience") != config.get("audience", data["marketplace"]["repository"]):
        raise MarketplaceError("attestation audience does not match this marketplace")
    issued_at = _parse_attestation_time(attestation.get("issued_at"), "issued_at")
    expires_at = _parse_attestation_time(attestation.get("expires_at"), "expires_at")
    now = datetime.now(timezone.utc)
    ttl = (expires_at - issued_at).total_seconds()
    if issued_at > now or expires_at <= now or ttl <= 0 or ttl > int(config.get("max_ttl_seconds", 300)):
        raise MarketplaceError("attestation is expired, not yet valid, or exceeds the configured TTL")
    if not isinstance(attestation.get("nonce"), str) or len(attestation["nonce"]) < 16:
        raise MarketplaceError("attestation nonce must contain at least 16 characters")
    claims = attestation.get("claims")
    device = attestation.get("device")
    if not isinstance(claims, dict) or not isinstance(device, dict):
        raise MarketplaceError("attestation must include claims and device objects")
    required = ("agent", "user", "project", "environment", "platform")
    if any(not isinstance(claims.get(field), str) or not claims[field] for field in required):
        raise MarketplaceError("attestation claims require non-empty agent, user, project, environment, and platform")
    groups = claims.get("groups", [])
    if not isinstance(groups, list) or any(not isinstance(group, str) or not group for group in groups):
        raise MarketplaceError("attestation claims.groups must be a string array")
    if not isinstance(device.get("id"), str) or not device["id"] or device.get("managed") is not True:
        raise MarketplaceError("attestation device must identify a managed device")
    return {"claims": claims, "device": device, "issuer": attestation["issuer"], "expires_at": attestation["expires_at"]}


def resolve_skills(
    root: Path, *, agent: str, user: str, project: str, environment: str,
    platform: str, skill_ids: list[str] | None = None, groups: list[str] | None = None,
) -> dict[str, Any]:
    """Read-only resolver for published, certified, policy-authorized artifacts."""
    data = load_manifest(root)
    canonical_platform = normalize_platform_name(platform)
    rules = _validate_resolver_policies(data["marketplace"].get("resolver_policies", []))
    group_values = sorted(set(groups or []))
    requested = set(skill_ids or [])
    known_ids = {
        f"{entry.get('department', '')}/{entry.get('name', '')}" for entry in data.get("skills", [])
    }
    denied = [
        {"id": skill_id, "code": "NOT_FOUND", "message": "Skill is not in this marketplace."}
        for skill_id in sorted(requested - known_ids)
    ]
    skills: list[dict[str, Any]] = []
    for entry in sorted(data.get("skills", []), key=lambda item: (item.get("department", ""), item.get("name", ""))):
        skill_id = f"{entry.get('department', '')}/{entry.get('name', '')}"
        if requested and skill_id not in requested:
            continue
        if entry.get("lifecycle", entry.get("approval_status")) != "published":
            denied.append({"id": skill_id, "code": "NOT_PUBLISHED", "message": "Skill is not published."})
            continue
        certification = _current_certification(entry, canonical_platform)
        if certification is None:
            denied.append({
                "id": skill_id, "code": "INCOMPATIBLE_PLATFORM",
                "message": f"Skill is not certified for {canonical_platform} at its current version.",
            })
            continue
        permitted, matched_rules = _policy_decision(
            rules, user=user, groups=group_values, agent=agent, project=project,
            environment=environment, platform=canonical_platform, skill_id=skill_id,
        )
        if not permitted:
            denied.append({
                "id": skill_id, "code": "POLICY_DENIED",
                "message": "Skill is not authorized for the current execution context.",
                "matched_rules": matched_rules,
            })
            continue
        location = _contained(root, str(entry["path"]))
        if not location.is_dir():
            denied.append({"id": skill_id, "code": "NOT_FOUND", "message": "Skill artifact is missing."})
            continue
        skills.append({
            "id": skill_id,
            "version": entry["version"],
            "artifact": {
                "path": str(entry["path"]),
                "sha256": _skill_artifact_sha256(location),
                "media_type": "application/vnd.agent-skill+directory",
            },
            "compatibility": {"platform": canonical_platform, "certification": certification},
            "lifecycle": entry["lifecycle"],
        })
    return {
        "resolver": "local-registry-v1",
        "resolved_at": _now(),
        "context": {
            "agent": agent, "user": user, "groups": group_values, "project": project,
            "environment": environment, "platform": canonical_platform,
        },
        "policy": {
            "mode": "deny-by-default", "enforced": True,
            "revision": data["marketplace"].get("resolver_policy_revision", _policy_revision(rules)),
        },
        "marketplace_release": {
            "repository": data["marketplace"]["repository"], "commit_sha": _marketplace_commit(root),
        },
        "skills": skills,
        "denied": denied,
    }


def generate_repository_files(root: Path, data: dict[str, Any]) -> None:
    """Regenerate catalog, bundles, CODEOWNERS, and provider CI files."""
    support_scripts = root / "scripts"
    support_scripts.mkdir(exist_ok=True)
    factory_scripts = Path(__file__).resolve().parent
    for filename in ("team_marketplace.py", "structured_interview.py",
                     "check_pipeline.py", "security_scan.py", "skill_document.py",
                     "validate.py", "marketplace_trust.py", "marketplace_health.py",
                     "marketplace_discovery.py", "marketplace_metrics.py",
                     "marketplace_distribution.py", "platforms.py",
                     "generate_verification.py", "review_staleness.py",
                     "schema_drift.py", "dependency_health.py",
                     "marketplace_reliability.py", "caliper_evidence.py"):
        source = factory_scripts / filename
        if source.is_file():
            shutil.copy2(source, support_scripts / filename)
    (root / ".gitignore").write_text("__pycache__/\n*.py[cod]\n*.pyc\n.marketplace-mutation.lock\n", encoding="utf-8")
    (root / "bundles").mkdir(exist_ok=True)
    for name, paths in sorted(data.get("bundles", {}).items()):
        payload = {"name": name, "skills": sorted(paths)}
        (root / "bundles" / f"{name}.json").write_text(
            json.dumps(payload, indent=2) + "\n", encoding="utf-8"
        )
    lines = [f"# {data['marketplace']['name']}", "", "Generated from `registry.json`. Do not edit by hand.", ""]
    departments: dict[str, list[dict[str, Any]]] = {}
    for item in data["skills"]:
        departments.setdefault(item["department"], []).append(item)
    for department, skills in sorted(departments.items()):
        lines += [f"## {department.replace('-', ' ').title()}", "", "| Skill | Version | Approval | Lifecycle | Owners |", "|---|---:|---|---|---|"]
        for item in sorted(skills, key=lambda value: value["name"]):
            owners = ", ".join(f"@{owner.lstrip('@')}" for owner in item.get("owners", []))
            lifecycle = item.get("lifecycle", item.get("approval_status", "draft"))
            lines.append(f"| [{item['name']}]({item['path']}) | {item['version']} | {item['approval_status']} | {lifecycle} | {owners} |")
        lines.append("")
    (root / "CATALOG.md").write_text("\n".join(lines), encoding="utf-8")
    pages = root / "skill-pages"
    pages.mkdir(exist_ok=True)
    expected_pages: set[str] = set()
    for item in data["skills"]:
        filename = f"{item['department']}--{item['name']}.md"
        expected_pages.add(filename)
        (pages / filename).write_text(render_skill_page(item), encoding="utf-8")
    for existing in pages.glob("*.md"):
        if existing.name not in expected_pages:
            existing.unlink()
    provider = _provider(data)
    governance_path = "/.github/" if provider.name == "github" else "/.gitlab-ci.yml"
    marketplace = data["marketplace"]
    approvers = [str(value).strip().lstrip("@") for value in marketplace.get("approvers", []) if str(value).strip()]
    governance_owners = " ".join(f"@{owner}" for owner in approvers) or "@acme-platform @acme-security"
    owner_lines = [
        "# Generated from registry.json; repository admins own governance files.",
        f"/registry.json {governance_owners}", f"/bundles/ {governance_owners}",
        f"{governance_path} {governance_owners}",
    ]
    for department, owner in sorted(marketplace.get("departments", {}).items()):
        owner_lines.append(f"/skills/{department}/ @{str(owner).lstrip('@')} {governance_owners}")
    for item in sorted(data["skills"], key=lambda value: value["path"]):
        owners = " ".join(f"@{owner.lstrip('@')}" for owner in item.get("owners", []))
        owner_lines.append(f"/{item['path']}/ {owners} {governance_owners}")
    (root / "CODEOWNERS").write_text("\n".join(owner_lines) + "\n", encoding="utf-8")
    governance = _GITHUB_GOVERNANCE if provider.name == "github" else _GITLAB_GOVERNANCE
    governance = governance.replace("ACME", str(marketplace["name"]))
    if marketplace.get("departments") or approvers or marketplace.get("supported_platforms"):
        policy = ["", "## Organization policy", ""]
        for department, owner in sorted(marketplace.get("departments", {}).items()):
            policy.append(f"- `{department}` owner: `@{str(owner).lstrip('@')}`")
        if approvers:
            policy.append("- Required approvers: " + ", ".join(f"`@{owner}`" for owner in approvers))
        if marketplace.get("supported_platforms"):
            policy.append("- Supported platforms: " + ", ".join(f"`{value}`" for value in marketplace["supported_platforms"]))
        governance = governance.rstrip() + "\n" + "\n".join(policy) + "\n"
    (root / "GOVERNANCE.md").write_text(governance, encoding="utf-8")
    provider.generate_files(root)


_CHECK_WORKFLOW = """name: Marketplace checks
on:
  pull_request:
jobs:
  governed-marketplace:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - run: python3 scripts/team_marketplace.py check --marketplace .
      - run: gh skill publish --dry-run
"""

_HEALTH_WORKFLOW = """name: Marketplace health
on:
  schedule:
    - cron: '17 8 * * 1'
  workflow_dispatch:
jobs:
  marketplace-health:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - run: python3 scripts/team_marketplace.py health --marketplace . --output MARKETPLACE_HEALTH.md --json-output marketplace-health.json
      - uses: actions/upload-artifact@v4
        if: always()
        with:
          name: marketplace-health
          path: |
            MARKETPLACE_HEALTH.md
            marketplace-health.json
"""

_RELEASE_WORKFLOW = """name: Marketplace release
on:
  push:
    tags: ['v*.*.*']
jobs:
  release:
    runs-on: ubuntu-latest
    permissions:
      contents: write
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - run: python3 scripts/team_marketplace.py check --marketplace . --release
      - run: gh skill publish --dry-run
      - run: gh release create "${GITHUB_REF_NAME}" --generate-notes --verify-tag
        env:
          GH_TOKEN: ${{ github.token }}
"""

_GITHUB_GOVERNANCE = """# ACME marketplace governance

Configure the default branch ruleset to require pull requests, CODEOWNER review,
the `governed-marketplace` status check, and approval from both department owners
and the ACME platform/security teams. Disable force pushes and branch deletion.

Configure a tag ruleset for `v*.*.*` that restricts tag creation, updates, and
deletion to release administrators. Releases install by immutable semantic-version
tag; advancing or rolling back a team uses a new managed `install --pin` command.

Skills remain unapproved after schema-v1 migration. Review their scripts, update
`approval_status` to `approved`, run `scripts/evolve.py` when corrections are
needed, and merge changes through a pull request. Do not edit installed copies.
"""

_GITLAB_CI = """stages:
  - check
  - release

workflow:
  rules:
    - if: $CI_PIPELINE_SOURCE == "merge_request_event"
    - if: $CI_COMMIT_TAG
    - if: $CI_COMMIT_BRANCH == $CI_DEFAULT_BRANCH

marketplace-check:
  stage: check
  image: python:3.12
  script:
    - python3 scripts/team_marketplace.py check --marketplace .

marketplace-release:
  stage: release
  image: registry.gitlab.com/gitlab-org/cli:latest
  rules:
    - if: $CI_COMMIT_TAG =~ /^v[0-9]+\\.[0-9]+\\.[0-9]+/
  script:
    - python3 scripts/team_marketplace.py check --marketplace . --release
    - echo "Creating governed marketplace release $CI_COMMIT_TAG"
  release:
    tag_name: $CI_COMMIT_TAG
    name: "Release $CI_COMMIT_TAG"
    description: "Governed ACME skill marketplace release $CI_COMMIT_TAG"

marketplace-health:
  stage: check
  image: python:3.12
  rules:
    - if: $CI_PIPELINE_SOURCE == "schedule"
  script:
    - python3 scripts/team_marketplace.py health --marketplace . --output MARKETPLACE_HEALTH.md --json-output marketplace-health.json
  artifacts:
    when: always
    paths: [MARKETPLACE_HEALTH.md, marketplace-health.json]
"""

_GITLAB_GOVERNANCE = """# ACME marketplace governance

Protect the default branch and require merge requests, CODEOWNER approval, a
successful `marketplace-check` pipeline, and approval from both department owners
and the ACME platform/security teams. Disable force pushes.

Protect `v*.*.*` tags so only release administrators can create them. Releases
install by immutable semantic-version tag; advancing or rolling back a team uses
a new managed `install --pin` command.

Skills remain unapproved after schema-v1 migration. Review their scripts, update
`approval_status` to `approved`, run `scripts/evolve.py` when corrections are
needed, and merge changes through a merge request. Do not edit installed copies.
"""


def _install_paths(
    root: Path, data: dict[str, Any], paths: list[str], scope: str, pin: str | None,
    *, force: bool = False, from_local: bool = False,
) -> list[list[str]]:
    """Install governed skill paths through the configured provider."""
    if not from_local and not pin:
        raise MarketplaceError("managed remote installs require --pin vX.Y.Z")
    provider_pin = pin
    if from_local and pin:
        if not SEMVER_TAG_RE.fullmatch(pin):
            raise MarketplaceError("local exact installs require --pin vX.Y.Z")
        head = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"], capture_output=True, text=True,
            check=False,
        )
        tagged = subprocess.run(
            ["git", "-C", str(root), "rev-parse", f"{pin}^{{commit}}"],
            capture_output=True, text=True, check=False,
        )
        if head.returncode or tagged.returncode or head.stdout.strip() != tagged.stdout.strip():
            raise MarketplaceError(
                f"local marketplace must be checked out at exact tag {pin}; refusing an ambiguous pin"
            )
        provider_pin = None
    if scope not in {"user", "project"}:
        raise MarketplaceError("scope must be user or project")
    blocked = [
        item["name"] for item in data["skills"]
        if item.get("path") in paths
        and item.get("lifecycle", item.get("approval_status")) not in {APPROVED, "published"}
    ]
    if blocked:
        raise MarketplaceError("bundle contains non-installable skills: " + ", ".join(blocked))
    commands = _provider(data).install(root, data, paths, scope, provider_pin, force, from_local)
    platform = "github-copilot" if _provider(data).name == "github" else "vscode-copilot"
    for path in paths:
        record_marketplace_event(root, "install", Path(path).name, True, platform=platform)
    return commands


def install_bundle(
    root: Path, bundle: str, scope: str, pin: str | None, *, force: bool = False,
    from_local: bool = False,
) -> list[list[str]]:
    """Install every exact skill path in a governed bundle."""
    data = load_manifest(root)
    paths = data.get("bundles", {}).get(bundle)
    if paths is None:
        raise MarketplaceError(f"bundle not found: {bundle}")
    return _install_paths(root, data, paths, scope, pin, force=force, from_local=from_local)


def install_skill(
    root: Path, department: str, name: str, scope: str, pin: str | None,
    *, force: bool = False, from_local: bool = False,
) -> list[list[str]]:
    """Install one governed skill without installing its whole bundle."""
    data = load_manifest(root)
    entry = _find_skill(data, department, name)
    return _install_paths(
        root, data, [entry["path"]], scope, pin, force=force, from_local=from_local,
    )


def health_marketplace(
    root: Path, *, as_of: date | None = None, active_owners: set[str] | None = None,
) -> dict[str, Any]:
    """Build the marketplace health report using its configured owner directory."""
    data = load_manifest(root)
    configured = data.get("marketplace", {}).get("active_owners", [])
    owners = active_owners if active_owners is not None else {
        str(owner).lstrip("@").strip() for owner in configured if str(owner).strip()
    }
    return build_health_report(data, root, as_of or date.today(), owners)


def search_marketplace(
    root: Path, query: str, *, platform: str | None = None, support_tier: str | None = None,
) -> list[dict[str, Any]]:
    """Search published skills by outcome with optional trust filters."""
    return search_skills(
        load_manifest(root).get("skills", []), query, platform=platform,
        support_tier=support_tier,
    )


def portfolio_report(root: Path) -> dict[str, Any]:
    """Return portfolio-level routing and coexistence evidence."""
    return evaluate_portfolio(load_manifest(root).get("skills", []))


def onboarding_report(root: Path) -> dict[str, Any]:
    """Report whether every department can enter the governed lifecycle."""
    data = load_manifest(root)
    config = data.get("marketplace", {})
    departments = config.get("departments", {})
    departments = departments if isinstance(departments, dict) else {}
    approvers = config.get("approvers", [])
    platforms = config.get("supported_platforms", [])
    skills = data.get("skills", [])
    rows: list[dict[str, Any]] = []
    for department, owner in sorted(departments.items()):
        owned = [item for item in skills if item.get("department") == department]
        published = [item for item in owned if item.get("lifecycle") == "published"]
        rows.append({
            "department": department,
            "owner": owner,
            "skills": len(owned),
            "published": len(published),
            "status": "operating" if published else "ready-to-create",
        })
    missing: list[str] = []
    if len(departments) < 2:
        missing.append("Configure at least two departments to prove cross-team reuse.")
    if not approvers:
        missing.append("Configure at least one independent marketplace approver.")
    if not platforms:
        missing.append("Configure at least one supported delivery platform.")
    if not data.get("bundles"):
        missing.append("Configure at least one governed starter bundle.")
    return {
        "status": "ready" if not missing else "incomplete",
        "marketplace": config.get("name", ""),
        "departments": rows,
        "approvers": sorted(str(item) for item in approvers),
        "supported_platforms": sorted(str(item) for item in platforms),
        "missing": missing,
        "next_gate": (
            "Run the blind cross-department acceptance protocol."
            if not missing and any(row["published"] for row in rows)
            else "Publish one evaluated skill, then run cross-department acceptance."
            if not missing else missing[0]
        ),
    }


def _metrics_paths(root: Path) -> tuple[Path, Path, Path]:
    state = root / ".marketplace-state"
    return root / "metrics-consent.json", state / "metrics-salt", state / "metrics.jsonl"


def configure_metrics_consent(root: Path, expires_at: str, *, approved_at: datetime | None = None) -> Path:
    """Write the explicit, reviewable organizational consent artifact."""
    now = approved_at or datetime.now(timezone.utc)
    artifact = {
        "schema": CONSENT_SCHEMA, "schema_version": 1, "enabled": True,
        "approved_at": now.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "expires_at": expires_at, "allowed_events": sorted(EVENT_TYPES),
    }
    errors = validate_consent(artifact, now=now)
    if errors:
        raise MarketplaceError("invalid metrics consent: " + "; ".join(errors))
    path, _, _ = _metrics_paths(root)
    path.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def record_marketplace_event(
    root: Path, event_name: str, skill_name: str, success: bool, *,
    duration_ms: int | None = None, platform: str | None = None,
) -> bool:
    """Best-effort local recording; absent/invalid consent is a strict no-op."""
    consent_path, salt_path, ledger_path = _metrics_paths(root)
    try:
        consent = json.loads(consent_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return False
    now = datetime.now(timezone.utc)
    if validate_consent(consent, now=now):
        return False
    salt_path.parent.mkdir(parents=True, exist_ok=True)
    if not salt_path.exists():
        salt_path.write_bytes(secrets.token_bytes(32))
        try:
            salt_path.chmod(0o600)
        except OSError:
            pass
    try:
        event = create_event(
            event_name, skill_name=skill_name, salt=salt_path.read_bytes(),
            timestamp=now, success=success, duration_ms=duration_ms, platform=platform,
        )
        return record_event(ledger_path, event, consent, now=now)
    except (MetricsError, OSError):
        return False


def summarize_marketplace_metrics(root: Path) -> dict[str, Any]:
    """Return deterministic aggregate metrics without exposing skill identities."""
    _, _, ledger = _metrics_paths(root)
    try:
        lines = ledger.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        lines = []
    return aggregate_events(lines)


def _find_skill(data: dict[str, Any], department: str, name: str) -> dict[str, Any]:
    entry = next(
        (item for item in data.get("skills", []) if item.get("department") == department and item.get("name") == name),
        None,
    )
    if entry is None:
        raise MarketplaceError(f"skill not found: {department}/{name}")
    return entry


def plan_distribution(
    root: Path, department: str, name: str, platforms: list[str], scope: str,
    release_ref: str | None, *, remote: bool, home: Path, project_root: Path,
) -> dict[str, Any]:
    """Return a non-mutating governed distribution plan for one skill."""
    data = load_manifest(root)
    entry = _find_skill(data, department, name)
    if entry.get("lifecycle", entry.get("approval_status")) != "published" and remote:
        raise MarketplaceError("remote distribution requires a published skill")
    try:
        plan = build_install_plan(
            skill_name=name, skill_version=entry["version"], platforms=platforms,
            scope=scope, source=data["marketplace"]["repository"] if remote else str((root / entry["path"]).resolve()),
            release_ref=release_ref, remote=remote, home=home, project_root=project_root,
        )
    except DistributionError as exc:
        raise MarketplaceError(str(exc)) from exc
    try:
        contract = require_operating_contract(entry)
    except DiscoveryError as exc:
        raise MarketplaceError(f"invalid operating contract: {exc}") from exc
    plan["preflight"] = {
        "environment": contract["environment"],
        "risk": contract["risk"],
        "installation_does_not_imply_readiness": True,
    }
    return plan


def certify_skill(
    root: Path, department: str, name: str, platform: str, evidence: dict[str, Any],
    *, timestamp: datetime | None = None,
) -> dict[str, Any]:
    """Validate and persist current-version compatibility evidence."""
    data = load_manifest(root)
    entry = _find_skill(data, department, name)
    discovery = entry.setdefault("discovery", {})
    compatibility = discovery.setdefault("compatibility", {})
    declared = compatibility.get("declared", [])
    try:
        record = certify_compatibility(
            platform=platform, skill_version=entry["version"], declared_platforms=declared,
            evidence=evidence, timestamp=timestamp or datetime.now(timezone.utc),
        )
    except DistributionError as exc:
        raise MarketplaceError(str(exc)) from exc
    stored = {**record, "version": record["skill_version"]}
    certifications = compatibility.setdefault("certified", [])
    canonical_platform = normalize_platform_name(platform)
    certifications[:] = [
        item for item in certifications
        if normalize_platform_name(str(item.get("platform", ""))) != canonical_platform
    ]
    certifications.append(stored)
    certifications.sort(key=lambda item: item["platform"])
    entry["compatibility"] = {
        "declared": sorted(set(declared)), "certified": certifications,
    }
    save_manifest(root, data)
    generate_repository_files(root, data)
    return stored


def reliability_skill(
    root: Path, department: str, name: str, *, platforms: list[str] | None = None,
    k: int = 3, timeout: int = 180, results_dir: Path | None = None, certify: bool = True,
    thresholds: Any = None, which: Any = None, runner: Any = None,
) -> dict[str, Any]:
    """Run Caliper on the governed copy for each measurable declared platform and certify what passes."""
    data = load_manifest(root)
    entry = _find_skill(data, department, name)
    skill_dir = _contained(root, str(entry["path"]))
    declared = list(
        entry.get("compatibility", {}).get("declared")
        or entry.get("discovery", {}).get("compatibility", {}).get("declared", [])
    )
    if not declared:
        raise MarketplaceError(f"{name}: no declared platforms to measure")
    options: dict[str, Any] = {
        "platforms": platforms, "k": k, "timeout": timeout, "skill_version": str(entry.get("version", "")),
    }
    for key, value in (("thresholds", thresholds), ("which", which), ("runner", runner)):
        if value is not None:
            options[key] = value
    try:
        report = run_reliability(
            skill_dir, declared, results_dir=results_dir or (root / ".caliper" / "runs"), **options,
        )
    except ReliabilityError as exc:
        raise MarketplaceError(str(exc)) from exc
    for row in report["platforms"]:
        if row.get("status") != "certifiable":
            continue
        evidence = row.pop("evidence")
        if certify:
            record = certify_skill(root, department, name, row["platform"], evidence)
            row.update({"status": "certified", "checks": record["checks"]})
        else:
            row["checks"] = [check["name"] for check in evidence["checks"]]
    report["certified"] = sorted(row["platform"] for row in report["platforms"] if row["status"] == "certified")
    return report


def transition_skill(root: Path, department: str, name: str, target: str) -> str:
    """Apply one policy-authorized lifecycle transition and regenerate the catalog."""
    data = load_manifest(root)
    entry = next(
        (item for item in data["skills"] if item.get("department") == department and item.get("name") == name),
        None,
    )
    if entry is None:
        raise MarketplaceError(f"skill not found: {department}/{name}")
    source = entry.get("lifecycle", entry.get("approval_status", "draft"))
    try:
        entry["lifecycle"] = transition_lifecycle(source, target)
    except TrustError as exc:
        raise MarketplaceError(str(exc)) from exc
    save_manifest(root, data)
    generate_repository_files(root, data)
    return target


def release_marketplace(root: Path, tag: str) -> None:
    """Run governance gates and publish a provider-native semantic release."""
    if not SEMVER_TAG_RE.fullmatch(tag):
        raise MarketplaceError("release tag must be a protected semantic version such as v1.2.0")
    errors = check_marketplace(root, require_published=True)
    if errors:
        raise MarketplaceError("release refused:\n- " + "\n- ".join(errors))
    data = load_manifest(root)
    unpublished = [
        f"{item['department']}/{item['name']}"
        for item in data["skills"]
        if item.get("lifecycle", item.get("approval_status")) != "published"
    ]
    if unpublished:
        raise MarketplaceError(
            "release requires the published lifecycle transition to be reviewed and committed: "
            + ", ".join(unpublished)
        )
    remote = subprocess.run(
        ["git", "-C", str(root), "remote", "get-url", "origin"],
        capture_output=True, text=True, check=False,
    )
    remote_url = (remote.stdout or "").strip()
    remote_path = Path(remote_url).expanduser() if remote.returncode == 0 and remote_url else None
    if remote_path is not None and remote_path.exists():
        create = subprocess.run(["git", "-C", str(root), "tag", tag], text=True, check=False)
        if create.returncode:
            raise MarketplaceError(f"failed to create local release tag {tag}")
        push = subprocess.run(
            ["git", "-C", str(root), "push", "origin", f"refs/tags/{tag}"],
            text=True, check=False,
        )
        if push.returncode:
            subprocess.run(["git", "-C", str(root), "tag", "-d", tag], check=False)
            raise MarketplaceError(f"failed to push release tag {tag} to local remote")
        verify = subprocess.run(
            ["git", "-C", str(root), "ls-remote", "--exit-code", "--tags", "origin", f"refs/tags/{tag}"],
            capture_output=True, text=True, check=False,
        )
        if verify.returncode:
            raise MarketplaceError(f"release tag {tag} is absent from origin")
        return
    _provider(data).release(root, tag)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Governed Git-backed Copilot team skill marketplace")
    sub = parser.add_subparsers(dest="command", required=True)
    create = sub.add_parser("create", help="guided marketplace creation")
    create.add_argument("--name")
    create.add_argument("--repository")
    create.add_argument("--provider", choices=tuple(PROVIDERS), default="github")
    create.add_argument("--marketplace")
    create.add_argument("--department")
    create.add_argument("--owner")
    create.add_argument("--bundle")
    init = sub.add_parser("init")
    init.add_argument("--name", required=True)
    init.add_argument("--repository", required=True)
    init.add_argument("--provider", choices=tuple(PROVIDERS), default="github")
    init.add_argument("--host", help="provider hostname; defaults to github.com or gitlab.com")
    init.add_argument("--from-registry")
    init.add_argument(
        "--department", action="append", metavar="SLUG=OWNER",
        help="repeatable department ownership declaration",
    )
    init.add_argument("--approver", action="append", help="repeatable governance approver handle")
    init.add_argument(
        "--supported-platform", action="append",
        help="repeatable canonical platform governed by this marketplace",
    )
    init.add_argument("--starter-bundle", action="append", help="repeatable empty bundle to initialize")
    init.add_argument("--marketplace", default=".")
    add = sub.add_parser("add")
    add.add_argument("skill_path")
    add.add_argument("--department", required=True)
    add.add_argument("--bundle", required=True)
    add.add_argument("--marketplace", default=".")
    update = sub.add_parser("update")
    update.add_argument("skill_path")
    update.add_argument("--department", required=True)
    update.add_argument("--marketplace", default=".")
    recreate = sub.add_parser("recreate")
    recreate.add_argument("skill_path")
    recreate.add_argument("--department", required=True)
    recreate.add_argument("--reason", required=True)
    recreate.add_argument("--marketplace", default=".")
    attest = sub.add_parser("attest")
    attest.add_argument("skill_path")
    attest.add_argument("--run-id", required=True)
    attest.add_argument("--completed-at", required=True)
    attest.add_argument("--marketplace", default=".", help=argparse.SUPPRESS)
    check = sub.add_parser("check")
    check.add_argument("--marketplace", default=".")
    check.add_argument("--release", action="store_true", help="require committed published lifecycle")
    check.add_argument(
        "--require-reliability", action="store_true",
        help="require agent-run (caliper:*) checks behind claude-code and codex certifications",
    )
    release = sub.add_parser("release")
    release.add_argument("--tag", required=True)
    release.add_argument("--marketplace", default=".")
    install = sub.add_parser("install")
    selection = install.add_mutually_exclusive_group(required=True)
    selection.add_argument("--bundle")
    selection.add_argument("--skill")
    install.add_argument("--department", help="required with --skill")
    install.add_argument("--scope", choices=("user", "project"), required=True)
    install.add_argument("--pin")
    install.add_argument("--force", action="store_true")
    install.add_argument(
        "--local", "--from-local", dest="from_local", action="store_true",
        help="install from this local marketplace; with --pin, HEAD must equal that exact tag",
    )
    install.add_argument("--marketplace", default=".")
    lifecycle = sub.add_parser("lifecycle")
    lifecycle.add_argument("skill_name")
    lifecycle.add_argument("--department", required=True)
    lifecycle.add_argument("--to", required=True)
    lifecycle.add_argument("--marketplace", default=".")
    health = sub.add_parser("health")
    health.add_argument("--marketplace", default=".")
    health.add_argument("--as-of", help="YYYY-MM-DD; defaults to today")
    health.add_argument("--active-owners", help="comma-separated override")
    health.add_argument("--output", help="write Markdown report")
    health.add_argument("--json-output", help="write JSON report")
    search = sub.add_parser("search")
    search.add_argument("query")
    search.add_argument("--platform")
    search.add_argument("--support-tier")
    search.add_argument("--json", action="store_true")
    search.add_argument("--marketplace", default=".")
    portfolio = sub.add_parser("portfolio-check")
    portfolio.add_argument("--marketplace", default=".")
    portfolio.add_argument("--json", action="store_true")
    onboarding = sub.add_parser("onboarding-report")
    onboarding.add_argument("--marketplace", default=".")
    onboarding.add_argument("--json", action="store_true")
    consent = sub.add_parser("metrics-consent")
    consent.add_argument("--expires-at", required=True, help="UTC RFC3339 expiry")
    consent.add_argument("--marketplace", default=".")
    metric = sub.add_parser("metrics-record")
    metric.add_argument("event", choices=sorted(EVENT_TYPES))
    metric.add_argument("--skill", required=True)
    metric.add_argument("--success", choices=("true", "false"), default="true")
    metric.add_argument("--duration-ms", type=int)
    metric.add_argument("--platform")
    metric.add_argument("--marketplace", default=".")
    summary = sub.add_parser("metrics-summary")
    summary.add_argument("--marketplace", default=".")
    plan_install = sub.add_parser("plan-install")
    plan_install.add_argument("skill_name")
    plan_install.add_argument("--department", required=True)
    plan_install.add_argument("--platforms", required=True, help="comma-separated canonical platforms")
    plan_install.add_argument("--scope", choices=("user", "project"), required=True)
    plan_install.add_argument("--release-ref")
    plan_install.add_argument("--local", action="store_true")
    # Resolve the home directory only when plan-install actually needs it.
    # Some clean/subprocess environments intentionally omit HOME/USERPROFILE.
    plan_install.add_argument("--home")
    plan_install.add_argument("--project-root", default=str(Path.cwd()))
    plan_install.add_argument("--marketplace", default=".")
    certify = sub.add_parser("certify")
    certify.add_argument("skill_name")
    certify.add_argument("--department", required=True)
    certify.add_argument("--platform", required=True)
    certify.add_argument("--evidence", required=True)
    certify.add_argument("--marketplace", default=".")
    reliability = sub.add_parser(
        "reliability", help="run Caliper per declared platform on the governed copy and certify what passes",
    )
    reliability.add_argument("skill_name")
    reliability.add_argument("--department", required=True)
    reliability.add_argument(
        "--platform", action="append", dest="platforms", help="repeatable; defaults to every declared platform",
    )
    reliability.add_argument("--k", type=int, default=3)
    reliability.add_argument("--timeout", type=int, default=180, help="seconds per attempt")
    reliability.add_argument("--results-dir", help="raw and pruned runs (default <marketplace>/.caliper/runs)")
    reliability.add_argument("--no-certify", action="store_true", help="measure and report without certifying")
    reliability.add_argument("--marketplace", default=".")
    policy_apply = sub.add_parser("policy.apply", help="validate and save resolver policies")
    policy_apply.add_argument("--file", required=True, help="JSON array of policy rules")
    policy_apply.add_argument("--marketplace", default=".")
    resolve = sub.add_parser("skills.resolve", help="resolve read-only skill artifacts from registry.json")
    resolve.add_argument("--attestation", required=True, help="path to a signed execution-attestation JSON document")
    resolve.add_argument("--skill", action="append", dest="skills", help="repeatable department/name skill ID")
    resolve.add_argument("--marketplace", default=".")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = Path(args.marketplace).resolve()
    try:
        if args.command == "create":
            create_marketplace_interactive(args)
        elif args.command == "init":
            init_marketplace(
                root, args.name, args.repository,
                Path(args.from_registry).resolve() if args.from_registry else None,
                provider=args.provider, host=args.host,
                departments=_department_options(args.department), approvers=args.approver,
                supported_platforms=args.supported_platform,
                starter_bundles=args.starter_bundle,
            )
            print(f"Marketplace initialized at {root}")
        elif args.command == "attest":
            path = attest_skill(Path(args.skill_path).resolve(), args.run_id, args.completed_at)
            print(f"Wrote trust attestation to {path}")
        elif args.command == "add":
            entry = add_skill(root, Path(args.skill_path).resolve(), args.department, args.bundle)
            print(f"Added {entry['department']}/{entry['name']} to bundle {args.bundle}")
        elif args.command == "update":
            entry = update_skill(root, Path(args.skill_path).resolve(), args.department)
            print(f"Updated {entry['department']}/{entry['name']} to v{entry['version']}")
        elif args.command == "recreate":
            entry = recreate_skill(
                root, Path(args.skill_path).resolve(), args.department, args.reason,
            )
            print(
                f"Recreated {entry['department']}/{entry['name']} as lineage {entry['lineage_id']}"
            )
        elif args.command == "check":
            errors = check_marketplace(
                root, require_published=args.release, require_reliability=args.require_reliability,
            )
            if errors:
                print("Marketplace checks failed:\n- " + "\n- ".join(errors), file=sys.stderr)
                return 1
            print("Marketplace checks passed")
        elif args.command == "release":
            release_marketplace(root, args.tag)
            print(f"Released {args.tag}")
        elif args.command == "install":
            if args.skill:
                if not args.department:
                    raise MarketplaceError("--department is required with --skill")
                commands = install_skill(
                    root, args.department, args.skill, args.scope, args.pin,
                    force=args.force, from_local=args.from_local,
                )
                print(f"Installed {len(commands)} skill: {args.department}/{args.skill}")
            else:
                commands = install_bundle(
                    root, args.bundle, args.scope, args.pin,
                    force=args.force, from_local=args.from_local,
                )
                print(f"Installed {len(commands)} skill(s) from bundle {args.bundle}")
        elif args.command == "lifecycle":
            state = transition_skill(root, args.department, args.skill_name, args.to)
            print(f"Transitioned {args.department}/{args.skill_name} to {state}")
        elif args.command == "health":
            try:
                as_of = date.fromisoformat(args.as_of) if args.as_of else None
            except ValueError as exc:
                raise MarketplaceError("--as-of must use YYYY-MM-DD") from exc
            owners = None
            if args.active_owners is not None:
                owners = {value.strip().lstrip("@") for value in args.active_owners.split(",") if value.strip()}
            report = health_marketplace(root, as_of=as_of, active_owners=owners)
            markdown = report_markdown(report)
            if args.output:
                Path(args.output).write_text(markdown, encoding="utf-8")
            if args.json_output:
                Path(args.json_output).write_text(report_json(report), encoding="utf-8")
            if not args.output:
                print(markdown, end="")
            if report["summary"]["status"] == "critical":
                return 1
        elif args.command == "search":
            results = search_marketplace(
                root, args.query, platform=args.platform, support_tier=args.support_tier,
            )
            if args.json:
                print(json.dumps(results, indent=2, ensure_ascii=False))
            elif not results:
                print("No matching published skills.")
            else:
                for item in results:
                    platforms = ",".join(item["certified_platforms"]) or "uncertified"
                    print(f"{item['department']}/{item['name']} v{item['version']} [{item['support_tier']}; {platforms}] — {item['question']}")
        elif args.command == "portfolio-check":
            report = portfolio_report(root)
            if args.json:
                print(json.dumps(report, indent=2, sort_keys=True))
            else:
                print(
                    f"Portfolio routing {report['status']}: "
                    f"{report['skills']} skill(s), {report['queries']} query checks"
                )
                for failure in report["failures"]:
                    print(
                        f"- {failure['skill']}: {failure['expectation']} failed for "
                        f"{failure['query']!r}; observed {failure['observed_owner']}"
                    )
            if report["status"] != "passed":
                return 1
        elif args.command == "onboarding-report":
            report = onboarding_report(root)
            if args.json:
                print(json.dumps(report, indent=2, sort_keys=True))
            else:
                print(f"Organizational onboarding: {report['status']}")
                for item in report["departments"]:
                    print(
                        f"- {item['department']}: owner={item['owner']}; "
                        f"skills={item['skills']}; published={item['published']}; "
                        f"status={item['status']}"
                    )
                for missing in report["missing"]:
                    print(f"- Missing: {missing}")
                print(f"Next gate: {report['next_gate']}")
            if report["status"] != "ready":
                return 1
        elif args.command == "metrics-consent":
            path = configure_metrics_consent(root, args.expires_at)
            print(f"Metrics consent enabled until {args.expires_at}: {path}")
        elif args.command == "metrics-record":
            recorded = record_marketplace_event(
                root, args.event, args.skill, args.success == "true",
                duration_ms=args.duration_ms, platform=args.platform,
            )
            print("Metric recorded." if recorded else "Metric not recorded: valid organizational consent is absent.")
        elif args.command == "metrics-summary":
            print(json.dumps(summarize_marketplace_metrics(root), indent=2, sort_keys=True))
        elif args.command == "plan-install":
            plan = plan_distribution(
                root, args.department, args.skill_name,
                [item.strip() for item in args.platforms.split(",") if item.strip()],
                args.scope, args.release_ref, remote=not args.local,
                home=Path(args.home) if args.home else Path.home(),
                project_root=Path(args.project_root),
            )
            print(json.dumps(plan, indent=2, sort_keys=True))
        elif args.command == "certify":
            try:
                evidence = json.loads(Path(args.evidence).read_text(encoding="utf-8"))
            except (FileNotFoundError, json.JSONDecodeError, OSError) as exc:
                raise MarketplaceError(f"cannot read certification evidence: {exc}") from exc
            record = certify_skill(root, args.department, args.skill_name, args.platform, evidence)
            print(json.dumps(record, indent=2, sort_keys=True))
        elif args.command == "reliability":
            report = reliability_skill(
                root, args.department, args.skill_name, platforms=args.platforms, k=args.k,
                timeout=args.timeout, results_dir=Path(args.results_dir) if args.results_dir else None,
                certify=not args.no_certify,
            )
            print(json.dumps(report, indent=2, sort_keys=True))
            if any(row.get("status") in {"refused", "failed"} for row in report["platforms"]):
                return 1
        elif args.command == "policy.apply":
            try:
                policies = json.loads(Path(args.file).read_text(encoding="utf-8"))
            except (FileNotFoundError, json.JSONDecodeError, OSError) as exc:
                raise MarketplaceError(f"cannot read resolver policy file: {exc}") from exc
            print(json.dumps(apply_resolver_policies(root, policies), indent=2, sort_keys=True))
        elif args.command == "skills.resolve":
            try:
                attestation = json.loads(Path(args.attestation).read_text(encoding="utf-8"))
            except (FileNotFoundError, json.JSONDecodeError, OSError) as exc:
                raise MarketplaceError(f"cannot read execution attestation: {exc}") from exc
            verified = verify_execution_attestation(root, attestation)
            claims = verified["claims"]
            result = resolve_skills(
                root, agent=claims["agent"], user=claims["user"], project=claims["project"],
                environment=claims["environment"], platform=claims["platform"], skill_ids=args.skills,
                groups=claims.get("groups", []),
            )
            result["attestation"] = {
                "issuer": verified["issuer"], "device_id": verified["device"]["id"],
                "expires_at": verified["expires_at"],
            }
            print(json.dumps(result, indent=2, sort_keys=True))
    except MarketplaceError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
