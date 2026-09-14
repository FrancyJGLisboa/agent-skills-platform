#!/usr/bin/env python3
"""
Git-Based Shared Skill Registry.

Manages a git-friendly skill registry for publishing, discovering, and installing
cross-platform agent skills. The registry is a directory with a registry.json
manifest and a skills/ folder — no servers, no databases, no new dependencies.

Usage:
    python3 scripts/skill_registry.py init     [--name NAME] [--registry PATH]
    python3 scripts/skill_registry.py publish  <skill-path> [--registry PATH] [--tags T1,T2] [--force] [--json]
    python3 scripts/skill_registry.py list     [--registry PATH] [--json]
    python3 scripts/skill_registry.py search   <query> [--registry PATH] [--json]
    python3 scripts/skill_registry.py install  <skill-name> [--registry PATH] [--platform PLATFORM] [--project] [--force] [--json]
    python3 scripts/skill_registry.py info     <skill-name> [--registry PATH] [--json]
    python3 scripts/skill_registry.py remove   <skill-name> [--registry PATH] [--force]
    python3 scripts/skill_registry.py stale    [--registry PATH] [--json]
    python3 scripts/skill_registry.py platforms [--json]

Installed-skill lifecycle (tracked in ~/.agent-skills/installed.json, or
$AGENT_SKILLS_HOME):
    python3 scripts/skill_registry.py installed [--tag TAG] [--platform PLATFORM] [--json]
    python3 scripts/skill_registry.py update    [<skill-name> | --all | --tag TAG] [--check] [--json]
    python3 scripts/skill_registry.py enable    [<skill-name> | --all | --tag TAG] [--platform PLATFORM]
    python3 scripts/skill_registry.py disable   [<skill-name> | --all | --tag TAG] [--platform PLATFORM]
    python3 scripts/skill_registry.py uninstall [<skill-name> | --all | --tag TAG] [--platform PLATFORM] [--force]
    python3 scripts/skill_registry.py trash     [--json]
    python3 scripts/skill_registry.py restore   <skill-name> [--force]
    python3 scripts/skill_registry.py purge     [--older-than DAYS]

`uninstall` and `remove` move files to the recycle bin instead of deleting;
`purge` empties items older than 30 days.

Exit codes:
    0 - Success
    1 - Error
"""

import argparse
import json
import re
import shutil
import sys
from datetime import date, datetime, timezone
from pathlib import Path

# --- Import sibling scripts ---

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from validate import validate_skill  # noqa: E402
from skill_document import SkillDoc  # noqa: E402
from security_scan import security_scan  # noqa: E402
from review_staleness import DEFAULT_REVIEW_INTERVAL_DAYS, classify_staleness  # noqa: E402
from platforms import PLATFORMS, list_supported_platforms, project_paths, user_paths  # noqa: E402
import installed_skills as ledger  # noqa: E402


# --- Constants ---

# Platform tables derive from the canonical scripts/platforms.py registry
# (single source of truth, covers all 17 supported platforms with correct paths).
ALL_PLATFORMS = list_supported_platforms()
PLATFORM_PATHS_USER = user_paths()
PLATFORM_PATHS_PROJECT = project_paths()

# Directories/files to exclude when copying skills
COPY_IGNORE_PATTERNS = shutil.ignore_patterns(
    ".git", "__pycache__", "node_modules", ".venv", "venv", "env",
    ".pytest_cache", ".mypy_cache", "dist", "build", "*.pyc", "*.pyo",
)

# Stop words for auto-tagging
STOP_WORDS = {
    "a", "an", "the", "and", "or", "but", "is", "are", "was", "were", "be",
    "been", "being", "in", "on", "at", "to", "for", "of", "with", "by",
    "from", "as", "into", "through", "during", "before", "after", "above",
    "below", "between", "out", "off", "over", "under", "again", "further",
    "then", "once", "here", "there", "when", "where", "why", "how", "all",
    "each", "every", "both", "few", "more", "most", "other", "some", "such",
    "no", "nor", "not", "only", "own", "same", "so", "than", "too", "very",
    "can", "will", "just", "should", "now", "it", "its", "this", "that",
    "these", "those", "he", "she", "we", "they", "what", "which", "who",
    "whom", "do", "does", "did", "has", "have", "had", "having", "using",
}

MIN_TAG_LENGTH = 3


# --- Namespacing & date parsing helpers ---

def _slug(value: str) -> str:
    """Return a filesystem-safe slug for an author/namespace path segment.

    Edge dots are stripped (internal ones kept, e.g. "j.r.tolkien") so a value
    like ".." can never become a path-traversal segment.
    """
    slug = re.sub(r"[^a-zA-Z0-9._-]+", "-", value.strip().lower()).strip("-.")
    return slug or "unknown"


def skill_storage_path(name: str, author: str) -> str:
    """
    Relative registry path for a skill's files, namespaced by author.

    A skill with an author is stored under ``skills/<author-slug>/<name>`` so
    two authors can publish the same skill name without clobbering each other's
    files. Authorless skills keep the legacy flat ``skills/<name>`` layout for
    backward compatibility with registries created before namespacing.
    """
    if author:
        return f"skills/{_slug(author)}/{name}"
    return f"skills/{name}"


def resolve_skill_entry(
    data: dict, name: str, author: str | None = None
) -> tuple[dict | None, str | None]:
    """
    Find a single skill entry by name, disambiguating by author when needed.

    Returns ``(entry, None)`` on a unique match, or ``(None, error_message)``
    when the skill is missing or the name is shared by multiple authors and no
    ``author`` filter was supplied.
    """
    matches = [s for s in data["skills"] if s.get("name") == name]
    if author is not None:
        matches = [s for s in matches if s.get("author", "") == author]

    if not matches:
        return None, f"skill '{name}' not found in registry."

    authors = sorted({s.get("author", "") for s in matches})
    if len(authors) > 1:
        listed = ", ".join(a or "(no author)" for a in authors)
        return None, (
            f"skill '{name}' is published by multiple authors ({listed}); "
            f"use --author to disambiguate."
        )

    # Unique (name, author); preserve first-published selection across versions.
    return matches[0], None


def parse_iso_date(value: str) -> date | None:
    """
    Parse an ISO date or timestamp string into a ``date``.

    Accepts both plain dates ("2026-06-13") and full ISO timestamps
    ("2026-06-13T12:00:00+00:00"). Returns None for empty or unparseable input.
    """
    if not value:
        return None
    try:
        return datetime.fromisoformat(value).date()
    except ValueError:
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None


# --- Registry I/O ---

def load_registry(registry_path: Path) -> dict:
    """Read and parse registry.json from the registry directory."""
    manifest = registry_path / "registry.json"
    if not manifest.exists():
        print(f"Error: registry.json not found in {registry_path}", file=sys.stderr)
        print("Run 'skill_registry.py init' first.", file=sys.stderr)
        sys.exit(1)
    try:
        return json.loads(manifest.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        print(f"Error reading registry.json: {exc}", file=sys.stderr)
        sys.exit(1)


def save_registry(registry_path: Path, data: dict) -> None:
    """Atomic write: write to .tmp then rename."""
    manifest = registry_path / "registry.json"
    tmp = registry_path / "registry.json.tmp"
    try:
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        tmp.replace(manifest)
    except OSError as exc:
        # Clean up tmp on failure
        if tmp.exists():
            tmp.unlink()
        print(f"Error writing registry.json: {exc}", file=sys.stderr)
        sys.exit(1)


# --- Metadata Extraction ---

def extract_skill_metadata(skill_path: Path) -> dict:
    """
    Parse SKILL.md frontmatter into a metadata dict.

    Returns dict with keys: name, description, version, author, license.
    Missing fields default to empty string.
    """
    skill_md = skill_path / "SKILL.md"
    if not skill_md.exists():
        return {"name": "", "description": "", "version": "", "author": "", "license": ""}

    content = skill_md.read_text(encoding="utf-8")
    doc = SkillDoc.from_text(content)
    if doc.frontmatter is None:
        return {"name": "", "description": "", "version": "", "author": "", "license": ""}

    meta = doc.metadata
    # Version: try metadata.version first, then top-level version
    version = meta.get("version") or doc.field("version") or ""

    return {
        "name": (doc.name or "").strip(),
        "description": (doc.description or "").strip(),
        "version": version.strip(),
        "author": meta.get("author", "").strip(),
        "license": (doc.license or "").strip(),
        "created": meta.get("created", "").strip(),
        "last_reviewed": meta.get("last_reviewed", "").strip(),
        "review_interval_days": meta.get("review_interval_days", "").strip(),
    }


def auto_extract_tags(description: str) -> list[str]:
    """
    Extract keyword tags from a description string.

    Splits on non-alphanumeric characters, filters stop words and short words,
    returns up to 10 unique lowercase tags.
    """
    if not description:
        return []
    words = re.split(r"[^a-zA-Z0-9-]+", description.lower())
    seen: set[str] = set()
    tags: list[str] = []
    for word in words:
        word = word.strip("-")
        if len(word) < MIN_TAG_LENGTH:
            continue
        if word in STOP_WORDS:
            continue
        if word not in seen:
            seen.add(word)
            tags.append(word)
        if len(tags) >= 10:
            break
    return tags


# --- Platform Detection ---

def detect_platform() -> str:
    """
    Auto-detect the installed agent platform by checking known directories.

    Returns the platform name or "claude-code" as default.
    """
    checks = [(p.name, p.detect_dir) for p in PLATFORMS if p.detect_dir]
    for platform, path in checks:
        if Path(path).expanduser().exists():
            return platform
    print(
        "Note: no agent platform detected; defaulting to claude-code "
        "(use --platform to override)",
        file=sys.stderr,
    )
    return "claude-code"


def resolve_install_path(name: str, platform: str, project: bool) -> Path:
    """
    Map platform + scope to the filesystem install path for a skill.

    Args:
        name: Skill name (used as subdirectory).
        platform: Platform identifier.
        project: If True, use project-level path; otherwise user-level.

    Returns:
        Absolute path where the skill should be installed.
    """
    if project:
        base = PLATFORM_PATHS_PROJECT.get(platform)
    else:
        base = PLATFORM_PATHS_USER.get(platform)

    if base is None:
        print(f"Error: unknown platform '{platform}'", file=sys.stderr)
        print(f"Supported: {', '.join(ALL_PLATFORMS)}", file=sys.stderr)
        sys.exit(1)

    return Path(base).expanduser().resolve() / name


# --- Table Formatting ---

def _format_table(entries: list[dict]) -> str:
    """Format skill entries as an aligned text table."""
    if not entries:
        return "No skills found."

    headers = ["NAME", "VERSION", "AUTHOR", "TAGS"]
    rows = []
    for entry in entries:
        tags = ", ".join(entry.get("tags", []))
        rows.append([
            entry.get("name", ""),
            entry.get("version", ""),
            entry.get("author", ""),
            tags,
        ])

    # Calculate column widths
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(cell))

    # Build output
    lines = []
    header_line = "  ".join(h.ljust(widths[i]) for i, h in enumerate(headers))
    lines.append(header_line)
    for row in rows:
        lines.append("  ".join(cell.ljust(widths[i]) for i, cell in enumerate(row)))
    return "\n".join(lines)


# --- Subcommands ---

def cmd_init(args: argparse.Namespace) -> None:
    """Initialize a new skill registry."""
    registry_path = Path(args.registry).resolve()
    manifest = registry_path / "registry.json"

    if manifest.exists():
        print(f"Error: registry already exists at {registry_path}", file=sys.stderr)
        sys.exit(1)

    registry_path.mkdir(parents=True, exist_ok=True)
    (registry_path / "skills").mkdir(exist_ok=True)

    name = args.name or "Shared Skills"
    data = {
        "registry": {
            "name": name,
            "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "schema_version": "1",
        },
        "skills": [],
    }
    save_registry(registry_path, data)
    print(f"Registry initialized: {registry_path}")
    print(f"  Name: {name}")
    print(f"  Manifest: {manifest}")
    print(f"  Skills dir: {registry_path / 'skills'}")


def enforce_security_gate(skill_path: Path, action: str) -> dict:
    """
    Scan a skill and exit(1) if it carries high-severity findings.

    Shared by publish and install so both sides of the registry enforce the same
    bar. Publishing keeps bad skills out of the catalog; installing protects the
    machine when the catalog is already wrong -- a skill published before a scanner
    rule existed, or a registry.json edited by hand, would otherwise land unchecked.

    Non-high findings are printed as warnings and do not block.

    Args:
        skill_path: Directory holding the skill's SKILL.md.
        action: Verb used in the failure message ("publish" or "install").

    Returns:
        The full scan result, for callers that record it in the registry entry.
    """
    scan = security_scan(str(skill_path))
    high_issues = [i for i in scan["issues"] if i["severity"] == "high"]
    other_issues = [i for i in scan["issues"] if i["severity"] != "high"]

    for issue in other_issues:
        location = issue["file"]
        if issue["line"] > 0:
            location += f":{issue['line']}"
        print(f"  [WARN] {location}: {issue['description']}")

    if high_issues:
        # Hard gate, deliberately NOT bypassable by --force: unreviewed
        # ingestion is the dominant registry risk. --force only overrides
        # duplicate-version entries, never security findings.
        print("Security scan found high-severity issues:", file=sys.stderr)
        for issue in high_issues:
            location = issue["file"]
            if issue["line"] > 0:
                location += f":{issue['line']}"
            print(f"  [HIGH] {location}: {issue['description']}", file=sys.stderr)
        print(
            f"Fix the findings and re-{action}; --force does not bypass the scan.",
            file=sys.stderr,
        )
        sys.exit(1)

    return scan


def cmd_publish(args: argparse.Namespace) -> None:
    """Publish a skill to the registry."""
    registry_path = Path(args.registry).resolve()
    skill_path = Path(args.skill_path).resolve()

    if not skill_path.is_dir():
        print(f"Error: skill path is not a directory: {skill_path}", file=sys.stderr)
        sys.exit(1)

    # Step 1: Validate
    validation = validate_skill(str(skill_path))
    if not validation["valid"]:
        print("Validation failed:", file=sys.stderr)
        for err in validation["errors"]:
            print(f"  [ERROR] {err}", file=sys.stderr)
        sys.exit(1)

    # Step 2: Security scan
    scan = enforce_security_gate(skill_path, "publish")

    # Step 3: Extract metadata
    metadata = extract_skill_metadata(skill_path)
    name = metadata["name"]
    version = metadata["version"] or "0.0.0"

    if not name:
        print("Error: could not extract skill name from SKILL.md frontmatter", file=sys.stderr)
        sys.exit(1)

    # Step 4: Tags
    tags = []
    if args.tags:
        tags = [t.strip() for t in args.tags.split(",") if t.strip()]
    if not tags:
        tags = auto_extract_tags(metadata["description"])

    author = metadata["author"]
    discovery = json.loads((skill_path / "discovery.json").read_text(encoding="utf-8"))

    # Step 5: Check duplicates. Identity is (name, author, version) so two
    # authors can publish the same skill name without colliding.
    data = load_registry(registry_path)

    def _same_skill(s: dict) -> bool:
        return (
            s["name"] == name
            and s.get("author", "") == author
            and s["version"] == version
        )

    for existing in data["skills"]:
        if _same_skill(existing):
            if not args.force:
                who = f" by '{author}'" if author else ""
                print(
                    f"Error: skill '{name}' version '{version}'{who} already exists in registry.",
                    file=sys.stderr,
                )
                print("Use --force to overwrite.", file=sys.stderr)
                sys.exit(1)
            # Remove old entry if forcing
            data["skills"] = [s for s in data["skills"] if not _same_skill(s)]

    # Step 6: Copy skill to registry (author-namespaced path)
    rel_path = skill_storage_path(name, author)
    dest = registry_path / rel_path
    # Containment guard: dest must resolve strictly inside skills/ before any
    # destructive operation (defense in depth against traversal via metadata).
    skills_root = (registry_path / "skills").resolve()
    resolved_dest = dest.resolve()
    if resolved_dest == skills_root or not resolved_dest.is_relative_to(skills_root):
        print(
            f"Error: refusing to publish outside the registry skills root: {dest}",
            file=sys.stderr,
        )
        sys.exit(1)
    if dest.exists():
        shutil.rmtree(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(skill_path, dest, ignore=COPY_IGNORE_PATTERNS)

    # Step 7: Add entry (including staleness metadata)
    staleness_data = {}
    if metadata.get("created"):
        staleness_data["created"] = metadata["created"]
    if metadata.get("last_reviewed"):
        staleness_data["last_reviewed"] = metadata["last_reviewed"]
    if metadata.get("review_interval_days"):
        try:
            staleness_data["review_interval_days"] = int(metadata["review_interval_days"])
        except ValueError:
            pass

    entry = {
        "name": name,
        "description": metadata["description"],
        "version": version,
        "author": author,
        "license": metadata["license"],
        "tags": tags,
        "platforms": list(ALL_PLATFORMS),
        "published": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "path": rel_path,
        "discovery": {
            field: discovery[field]
            for field in ("question", "trigger", "decision", "evidence", "success_measure")
        },
        "validation": {
            "valid": validation["valid"],
            "errors": len(validation["errors"]),
            "warnings": len(validation["warnings"]),
        },
        "security": {
            "clean": scan["clean"],
            "issues": len(scan["issues"]),
        },
        "staleness": staleness_data,
    }
    data["skills"].append(entry)
    save_registry(registry_path, data)

    if getattr(args, "json", False):
        print(json.dumps(entry, indent=2))
    else:
        print(f"Published '{name}' v{version} to registry.")
        print(f"  Path: {dest}")
        print(f"  Tags: {', '.join(tags)}")


def cmd_list(args: argparse.Namespace) -> None:
    """List all skills in the registry."""
    registry_path = Path(args.registry).resolve()
    data = load_registry(registry_path)
    skills = _filter_by_tag(data["skills"], getattr(args, "tag", None))

    if getattr(args, "json", False):
        print(json.dumps(skills, indent=2))
        return

    print(_format_table(skills))


def cmd_search(args: argparse.Namespace) -> None:
    """Search for skills matching a query."""
    registry_path = Path(args.registry).resolve()
    data = load_registry(registry_path)
    query = args.query.lower()

    matches = []
    for skill in data["skills"]:
        searchable = " ".join([
            skill.get("name", ""),
            skill.get("description", ""),
            skill.get("author", ""),
            " ".join(skill.get("tags", [])),
        ]).lower()
        if query in searchable:
            matches.append(skill)

    if getattr(args, "json", False):
        print(json.dumps(matches, indent=2))
        return

    if not matches:
        print(f"No skills matching '{args.query}'.")
        return

    print(f"Skills matching '{args.query}':\n")
    print(_format_table(matches))


def _resolve_platform(requested: str | None) -> str:
    platform = requested or detect_platform()
    if platform not in ALL_PLATFORMS:
        print(f"Error: unknown platform '{platform}'", file=sys.stderr)
        print(f"Supported: {', '.join(ALL_PLATFORMS)}", file=sys.stderr)
        sys.exit(1)
    return platform


def _install_entry(
    registry_path: Path, skill_entry: dict, platform: str, project: bool, force: bool,
) -> dict:
    """Copy one registry skill into its platform path and record it in the ledger."""
    name = skill_entry["name"]
    target = resolve_install_path(name, platform, project)

    # Check if already installed
    if target.exists() and not force:
        print(f"Error: skill already installed at {target}", file=sys.stderr)
        print("Use --force to overwrite.", file=sys.stderr)
        sys.exit(1)

    # Copy
    source = registry_path / skill_entry["path"]
    if not source.exists():
        print(f"Error: skill files not found at {source}", file=sys.stderr)
        sys.exit(1)

    # Re-scan at install time. The registry's cached `security.clean` field was
    # written when the skill was published and is never revisited, so it cannot
    # speak for scanner rules added since, or for a registry.json edited by hand.
    # Installing is the moment the code reaches this machine -- scan it here.
    enforce_security_gate(source, "install")

    if target.exists():
        shutil.rmtree(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, target, ignore=COPY_IGNORE_PATTERNS)

    # A reinstall over a disabled skill lands enabled; drop the stale parking spot.
    previous = ledger.forget(str(target))
    if previous is not None and not previous.get("enabled", True):
        shutil.rmtree(previous.get("parked_path", ""), ignore_errors=True)

    record = ledger.make_entry(
        name=name,
        author=skill_entry.get("author", ""),
        version=skill_entry.get("version", ""),
        platform=platform,
        scope="project" if project else "user",
        path=target,
        registry=registry_path,
        tags=skill_entry.get("tags", []),
    )
    ledger.record_install(record)
    return record


def cmd_install(args: argparse.Namespace) -> None:
    """Install a skill (or every skill carrying a tag) from the registry."""
    registry_path = Path(args.registry).resolve()
    data = load_registry(registry_path)
    platform = _resolve_platform(args.platform)
    project = getattr(args, "project", False)
    tag = getattr(args, "tag", None)

    if tag is not None:
        entries = _filter_by_tag(data["skills"], tag)
        if not entries:
            print(f"Error: no registry skills carry tag '{tag}'.", file=sys.stderr)
            sys.exit(1)
    else:
        # Find skill (disambiguating by author when the name is shared)
        skill_entry, error = resolve_skill_entry(data, args.skill_name, getattr(args, "author", None))
        if skill_entry is None:
            print(f"Error: {error}", file=sys.stderr)
            sys.exit(1)
        entries = [skill_entry]

    records = [_install_entry(registry_path, e, platform, project, args.force) for e in entries]

    if getattr(args, "json", False):
        print(json.dumps([
            {"installed": True, "skill": r["name"], "platform": platform, "path": r["path"]}
            for r in records
        ] if tag is not None else {
            "installed": True, "skill": records[0]["name"], "platform": platform, "path": records[0]["path"],
        }, indent=2))
        return

    scope = "project" if project else "user"
    for record in records:
        print(f"Installed '{record['name']}' v{record['version']} for {platform} ({scope}-level).")
        print(f"  Path: {record['path']}")

    # Platform-specific activation tips
    tips = {
        "claude-code": "Skill is auto-loaded. Start a new conversation to activate.",
        "github-copilot": "Skill is auto-loaded by Copilot Chat.",
        "cursor":      "Skill is loaded alongside .mdc rules.",
        "windsurf":    "Skill is auto-loaded by Windsurf.",
        "cline":       "Skill is loaded from .clinerules.",
        "codex":       "Skill is auto-loaded by Codex CLI.",
        "gemini":      "Skill is auto-loaded by Gemini CLI.",
    }
    tip = tips.get(platform)
    if tip:
        print(f"  Tip: {tip}")


def cmd_info(args: argparse.Namespace) -> None:
    """Show detailed info about a skill."""
    registry_path = Path(args.registry).resolve()
    data = load_registry(registry_path)

    skill_entry, error = resolve_skill_entry(data, args.skill_name, getattr(args, "author", None))
    if skill_entry is None:
        print(f"Error: {error}", file=sys.stderr)
        sys.exit(1)

    if getattr(args, "json", False):
        print(json.dumps(skill_entry, indent=2))
        return

    print(f"Skill: {skill_entry['name']}")
    print(f"{'=' * 50}")
    print(f"  Version:     {skill_entry.get('version', 'N/A')}")
    print(f"  Author:      {skill_entry.get('author', 'N/A')}")
    print(f"  License:     {skill_entry.get('license', 'N/A')}")
    print(f"  Description: {skill_entry.get('description', 'N/A')}")
    print(f"  Tags:        {', '.join(skill_entry.get('tags', []))}")
    print(f"  Platforms:   {', '.join(skill_entry.get('platforms', []))}")
    print(f"  Published:   {skill_entry.get('published', 'N/A')}")
    print(f"  Path:        {skill_entry.get('path', 'N/A')}")

    validation = skill_entry.get("validation", {})
    if validation:
        status = "valid" if validation.get("valid") else "invalid"
        print(f"  Validation:  {status} ({validation.get('errors', 0)} errors, {validation.get('warnings', 0)} warnings)")

    security = skill_entry.get("security", {})
    if security:
        status = "clean" if security.get("clean") else f"{security.get('issues', 0)} issues"
        print(f"  Security:    {status}")

    print(f"{'=' * 50}")


def cmd_remove(args: argparse.Namespace) -> None:
    """Remove a skill from the registry."""
    registry_path = Path(args.registry).resolve()
    data = load_registry(registry_path)

    # Find skill (disambiguating by author when the name is shared)
    skill_entry, error = resolve_skill_entry(data, args.skill_name, getattr(args, "author", None))
    if skill_entry is None:
        print(f"Error: {error}", file=sys.stderr)
        sys.exit(1)

    if not args.force:
        print(f"Remove '{args.skill_name}' from registry? Use --force to confirm.", file=sys.stderr)
        sys.exit(1)

    # Remove only the resolved author's entries for this name (all versions).
    target_author = skill_entry.get("author", "")
    removed = [
        s for s in data["skills"]
        if s["name"] == args.skill_name and s.get("author", "") == target_author
    ]
    data["skills"] = [s for s in data["skills"] if s not in removed]

    # Files go to the recycle bin, with the entries needed to put them back.
    skill_dir = registry_path / skill_entry["path"]
    item = None
    if skill_dir.exists():
        item = ledger.move_to_trash(
            skill_dir,
            {"name": args.skill_name, "registry": str(registry_path), "entries": removed},
            kind="registry",
        )
    save_registry(registry_path, data)

    print(f"Removed '{args.skill_name}' from registry.")
    if item is not None:
        print(f"  Recycle bin: {item} (restore with 'skill_registry.py restore {args.skill_name}')")


def cmd_stale(args: argparse.Namespace) -> None:
    """Report skills that are overdue for review."""
    registry_path = Path(args.registry).resolve()
    data = load_registry(registry_path)
    today = date.today()

    results: list[dict] = []
    for skill in data["skills"]:
        staleness = skill.get("staleness", {})
        published = skill.get("published", "")

        # Determine reference date: last_reviewed > created > published
        ref_date = None
        date_source = "none"

        for value, source in (
            (staleness.get("last_reviewed", ""), "last_reviewed"),
            (staleness.get("created", ""), "created"),
            (published, "published"),
        ):
            ref_date = parse_iso_date(value)
            if ref_date is not None:
                date_source = source
                break

        interval = staleness.get("review_interval_days", DEFAULT_REVIEW_INTERVAL_DAYS)
        if not isinstance(interval, int):
            try:
                interval = int(interval)
            except (ValueError, TypeError):
                interval = DEFAULT_REVIEW_INTERVAL_DAYS

        days_since = None
        status = "unknown"
        if ref_date:
            status, days_since, _deadline = classify_staleness(ref_date, interval, today)

        results.append({
            "name": skill.get("name", ""),
            "version": skill.get("version", ""),
            "status": status,
            "days_since_review": days_since,
            "date_source": date_source,
            "review_interval_days": interval,
        })

    if getattr(args, "json", False):
        print(json.dumps(results, indent=2))
        return

    # Text table output
    if not results:
        print("No skills in registry.")
        return

    headers = ["NAME", "VERSION", "STATUS", "DAYS SINCE", "SOURCE", "INTERVAL"]
    rows = []
    for r in results:
        rows.append([
            r["name"],
            r["version"],
            r["status"].upper(),
            str(r["days_since_review"]) if r["days_since_review"] is not None else "N/A",
            r["date_source"],
            str(r["review_interval_days"]),
        ])

    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(cell))

    header_line = "  ".join(h.ljust(widths[i]) for i, h in enumerate(headers))
    print(header_line)
    for row in rows:
        print("  ".join(cell.ljust(widths[i]) for i, cell in enumerate(row)))

    # Summary
    overdue = sum(1 for r in results if r["status"] == "overdue")
    due_soon = sum(1 for r in results if r["status"] == "due_soon")
    if overdue or due_soon:
        print(f"\nSummary: {overdue} overdue, {due_soon} due soon, {len(results)} total")


def cmd_platforms(args: argparse.Namespace) -> None:
    """List supported install platforms with their user and project paths."""
    rows = [
        {"name": p.name, "user_path": p.user_path, "project_path": p.project_path,
         "detected": bool(p.detect_dir) and Path(p.detect_dir).expanduser().exists()}
        for p in PLATFORMS
    ]
    if getattr(args, "json", False):
        print(json.dumps(rows, indent=2))
        return
    width = max(len(r["name"]) for r in rows)
    for r in rows:
        mark = "*" if r["detected"] else " "
        print(f"{mark} {r['name'].ljust(width)}  {r['user_path']}")
    print("\n* = detected on this machine")


# --- Installed-skill lifecycle ---

def _filter_by_tag(entries: list[dict], tag: str | None) -> list[dict]:
    if tag is None:
        return entries
    return [e for e in entries if tag in e.get("tags", [])]


def _select_installed(args: argparse.Namespace, *, verb: str) -> list[dict]:
    """Resolve the ledger entries a lifecycle command should act on.

    Exactly one of ``skill_name``, ``--tag``, ``--all`` selects; ``--platform``
    narrows. Exits with a message when the selection is empty or ambiguous.
    """
    name = getattr(args, "skill_name", None)
    tag = getattr(args, "tag", None)
    everything = getattr(args, "all", False)
    selectors = sum(x is not None and x is not False for x in (name, tag, everything))
    if selectors != 1:
        print(f"Error: {verb} needs exactly one of <skill-name>, --tag, or --all.", file=sys.stderr)
        sys.exit(1)

    entries = ledger.select(
        ledger.load_ledger()["skills"],
        name=name, tag=tag, platform=getattr(args, "platform", None),
    )
    if not entries:
        if name is not None:
            print(f"Error: '{name}' is not recorded as installed.", file=sys.stderr)
            print("Run 'skill_registry.py installed' to see what is.", file=sys.stderr)
        elif tag is not None:
            print(f"Error: no installed skills carry tag '{tag}'.", file=sys.stderr)
        else:
            print("No installed skills recorded.", file=sys.stderr)
        sys.exit(1)
    return entries


def _format_installed(entries: list[dict]) -> str:
    if not entries:
        return "No installed skills recorded."
    headers = ["NAME", "VERSION", "PLATFORM", "SCOPE", "STATE", "PATH"]
    rows = [[
        e.get("name", ""), e.get("version", ""), e.get("platform", ""), e.get("scope", ""),
        "enabled" if e.get("enabled", True) else "disabled", e.get("path", ""),
    ] for e in entries]
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(cell))
    lines = ["  ".join(h.ljust(widths[i]) for i, h in enumerate(headers))]
    lines.extend("  ".join(cell.ljust(widths[i]) for i, cell in enumerate(row)) for row in rows)
    return "\n".join(lines)


def cmd_installed(args: argparse.Namespace) -> None:
    """List skills recorded as installed on this machine."""
    entries = ledger.select(
        ledger.load_ledger()["skills"],
        tag=getattr(args, "tag", None), platform=getattr(args, "platform", None),
    )
    if getattr(args, "json", False):
        # `present` tells a caller whether the files are still where the
        # ledger says (a user may have deleted the directory by hand).
        print(json.dumps(
            [{**e, "present": ledger.current_location(e).is_dir()} for e in entries], indent=2,
        ))
        return
    print(_format_installed(entries))


def _registry_version(entry: dict) -> tuple[dict | None, str | None]:
    """Look up the registry entry an installed skill came from."""
    registry_path = Path(entry.get("registry", ""))
    if not (registry_path / "registry.json").exists():
        return None, f"registry not found at {registry_path}"
    data = load_registry(registry_path)
    skill_entry, error = resolve_skill_entry(data, entry["name"], entry.get("author") or None)
    if skill_entry is None:
        return None, error
    return skill_entry, None


def cmd_update(args: argparse.Namespace) -> None:
    """Reinstall installed skills whose registry version has moved on."""
    entries = _select_installed(args, verb="update")
    results: list[dict] = []
    for entry in entries:
        skill_entry, error = _registry_version(entry)
        result = {
            "name": entry["name"], "platform": entry["platform"], "path": entry["path"],
            "installed": entry.get("version", ""), "available": None, "status": "",
        }
        if skill_entry is None:
            result["status"] = f"error: {error}"
        else:
            result["available"] = skill_entry.get("version", "")
            if result["available"] == result["installed"] and not args.force:
                result["status"] = "current"
            elif args.check:
                result["status"] = "outdated"
            else:
                # _install_entry discards a parked copy; re-park the new one so
                # an update never silently re-enables a disabled skill.
                record = _install_entry(
                    Path(entry["registry"]), skill_entry, entry["platform"],
                    entry["scope"] == "project", force=True,
                )
                if not entry.get("enabled", True):
                    ledger.disable(record)
                result["status"] = "updated"
        results.append(result)

    if getattr(args, "json", False):
        print(json.dumps(results, indent=2))
    else:
        for r in results:
            available = r["available"] if r["available"] is not None else "?"
            print(f"{r['status']:<9} {r['name']} ({r['platform']}) {r['installed']} -> {available}")

    if args.check and any(r["status"] == "outdated" for r in results):
        sys.exit(2)
    if any(r["status"].startswith("error") for r in results):
        sys.exit(1)


def _toggle(args: argparse.Namespace, *, enable: bool) -> None:
    verb = "enable" if enable else "disable"
    entries = _select_installed(args, verb=verb)
    changed: list[dict] = []
    for entry in entries:
        if entry.get("enabled", True) == enable:
            continue
        try:
            changed.append(ledger.enable(entry) if enable else ledger.disable(entry))
        except FileNotFoundError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            sys.exit(1)
    if getattr(args, "json", False):
        print(json.dumps(changed, indent=2))
        return
    if not changed:
        print(f"Nothing to {verb}: already {verb}d.")
        return
    for entry in changed:
        print(f"{verb.capitalize()}d '{entry['name']}' for {entry['platform']} ({entry['scope']}-level).")
    if not enable:
        print(f"  Files parked under {ledger.disabled_dir()}; 'enable' puts them back.")


def cmd_enable(args: argparse.Namespace) -> None:
    """Move a disabled skill back into its tool's skills directory."""
    _toggle(args, enable=True)


def cmd_disable(args: argparse.Namespace) -> None:
    """Move an installed skill out of its tool's skills directory without deleting it."""
    _toggle(args, enable=False)


def cmd_uninstall(args: argparse.Namespace) -> None:
    """Move installed skills to the recycle bin and forget them."""
    entries = _select_installed(args, verb="uninstall")
    if not args.force:
        names = ", ".join(f"{e['name']} ({e['platform']})" for e in entries)
        print(f"Uninstall {names}? Use --force to confirm.", file=sys.stderr)
        sys.exit(1)
    removed: list[dict] = []
    for entry in entries:
        location = ledger.current_location(entry)
        item = None
        if location.exists():
            # Trash records the enabled path as origin so restore lands it live.
            item = ledger.move_to_trash(location, entry, kind="install")
            sidecar = Path(item) / ledger.TRASH_SIDECAR
            data = json.loads(sidecar.read_text(encoding="utf-8"))
            data["origin"] = entry["path"]
            sidecar.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        ledger.forget(entry["path"])
        removed.append({"name": entry["name"], "platform": entry["platform"],
                        "path": entry["path"], "trash": str(item) if item else None})
    if getattr(args, "json", False):
        print(json.dumps(removed, indent=2))
        return
    for r in removed:
        print(f"Uninstalled '{r['name']}' from {r['platform']}.")
        if r["trash"]:
            print(f"  Recycle bin: {r['trash']}")
    print(f"Restore with 'skill_registry.py restore <skill-name>'; 'purge' empties items older than {ledger.DEFAULT_TRASH_TTL_DAYS} days.")


def cmd_trash(args: argparse.Namespace) -> None:
    """List recycle-bin contents."""
    items = ledger.list_trash()
    if getattr(args, "json", False):
        print(json.dumps(items, indent=2))
        return
    if not items:
        print("Recycle bin is empty.")
        return
    headers = ["NAME", "KIND", "TRASHED", "ORIGIN"]
    rows = [[i.get("name", ""), i.get("kind", ""), i.get("trashed_at", "")[:19], i.get("origin", "")] for i in items]
    widths = [max(len(h), *(len(r[c]) for r in rows)) for c, h in enumerate(headers)]
    print("  ".join(h.ljust(widths[i]) for i, h in enumerate(headers)))
    for row in rows:
        print("  ".join(cell.ljust(widths[i]) for i, cell in enumerate(row)))


def cmd_restore(args: argparse.Namespace) -> None:
    """Put the most recently trashed copy of a skill back where it came from."""
    matches = [i for i in ledger.list_trash() if i.get("name") == args.skill_name]
    if not matches:
        print(f"Error: '{args.skill_name}' is not in the recycle bin.", file=sys.stderr)
        sys.exit(1)
    item = matches[0]
    try:
        origin = ledger.restore_from_trash(item, force=args.force)
    except (FileNotFoundError, FileExistsError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    meta = item.get("meta", {})
    if item.get("kind") == "install":
        meta["enabled"] = True
        meta.pop("parked_path", None)
        ledger.record_install(meta)
    elif item.get("kind") == "registry":
        registry_path = Path(meta.get("registry", ""))
        if (registry_path / "registry.json").exists():
            data = load_registry(registry_path)
            data["skills"].extend(meta.get("entries", []))
            save_registry(registry_path, data)

    if getattr(args, "json", False):
        print(json.dumps({"restored": True, "skill": args.skill_name, "path": str(origin)}, indent=2))
        return
    print(f"Restored '{args.skill_name}' to {origin}.")


def cmd_purge(args: argparse.Namespace) -> None:
    """Delete recycle-bin items older than the TTL."""
    purged = ledger.purge_trash(args.older_than)
    if getattr(args, "json", False):
        print(json.dumps(purged, indent=2))
        return
    if not purged:
        print(f"Nothing older than {args.older_than} days in the recycle bin.")
        return
    for item in purged:
        print(f"Purged {item.get('name', '')} (trashed {item.get('trashed_at', '')[:10]})")


# --- CLI ---

def _add_registry_arg(parser: argparse.ArgumentParser) -> None:
    """Add the --registry argument to a subparser."""
    parser.add_argument(
        "--registry", default="./registry",
        help="Path to the registry directory (default: ./registry)",
    )


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser with all subcommands."""
    parser = argparse.ArgumentParser(
        prog="skill_registry",
        description="Git-based shared skill registry for cross-platform agent skills.",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # init
    p_init = subparsers.add_parser("init", help="Initialize a new skill registry")
    _add_registry_arg(p_init)
    p_init.add_argument("--name", help="Registry name (default: 'Shared Skills')")

    # publish
    p_publish = subparsers.add_parser("publish", help="Publish a skill to the registry")
    p_publish.add_argument("skill_path", help="Path to the skill directory")
    _add_registry_arg(p_publish)
    p_publish.add_argument("--tags", help="Comma-separated tags (auto-extracted if omitted)")
    p_publish.add_argument("--force", action="store_true", help="Overwrite existing or ignore high-severity issues")
    p_publish.add_argument("--json", action="store_true", help="Output as JSON")

    # list
    p_list = subparsers.add_parser("list", help="List all skills in the registry")
    _add_registry_arg(p_list)
    p_list.add_argument("--tag", help="Only skills carrying this tag")
    p_list.add_argument("--json", action="store_true", help="Output as JSON")

    # search
    p_search = subparsers.add_parser("search", help="Search for skills")
    p_search.add_argument("query", help="Search query (matches name, description, author, tags)")
    _add_registry_arg(p_search)
    p_search.add_argument("--json", action="store_true", help="Output as JSON")

    # install
    p_install = subparsers.add_parser("install", help="Install a skill from the registry")
    p_install.add_argument("skill_name", nargs="?", help="Name of the skill to install")
    _add_registry_arg(p_install)
    p_install.add_argument("--tag", help="Install every registry skill carrying this tag instead of one by name")
    p_install.add_argument("--author", help="Disambiguate when the name is shared by multiple authors")
    p_install.add_argument("--platform", choices=ALL_PLATFORMS, help="Target platform (auto-detected if omitted)")
    p_install.add_argument("--project", action="store_true", help="Install at project level instead of user level")
    p_install.add_argument("--force", action="store_true", help="Overwrite existing installation")
    p_install.add_argument("--json", action="store_true", help="Output as JSON")

    # info
    p_info = subparsers.add_parser("info", help="Show detailed info about a skill")
    p_info.add_argument("skill_name", help="Name of the skill")
    _add_registry_arg(p_info)
    p_info.add_argument("--author", help="Disambiguate when the name is shared by multiple authors")
    p_info.add_argument("--json", action="store_true", help="Output as JSON")

    # remove
    p_remove = subparsers.add_parser("remove", help="Remove a skill from the registry")
    p_remove.add_argument("skill_name", help="Name of the skill to remove")
    _add_registry_arg(p_remove)
    p_remove.add_argument("--author", help="Disambiguate when the name is shared by multiple authors")
    p_remove.add_argument("--force", action="store_true", help="Confirm removal")

    # stale
    p_stale = subparsers.add_parser("stale", help="Report skills overdue for review")
    _add_registry_arg(p_stale)
    p_stale.add_argument("--json", action="store_true", help="Output as JSON")

    # platforms
    p_platforms = subparsers.add_parser("platforms", help="List supported install platforms")
    p_platforms.add_argument("--json", action="store_true", help="Output as JSON")

    # installed
    p_installed = subparsers.add_parser("installed", help="List skills installed on this machine")
    p_installed.add_argument("--tag", help="Only skills carrying this tag")
    p_installed.add_argument("--platform", choices=ALL_PLATFORMS, help="Only this platform")
    p_installed.add_argument("--json", action="store_true", help="Output as JSON")

    def _lifecycle(name: str, help_text: str) -> argparse.ArgumentParser:
        p = subparsers.add_parser(name, help=help_text)
        p.add_argument("skill_name", nargs="?", help="Name of one installed skill")
        p.add_argument("--tag", help="Every installed skill carrying this tag")
        p.add_argument("--all", action="store_true", help="Every installed skill")
        p.add_argument("--platform", choices=ALL_PLATFORMS, help="Narrow to this platform")
        p.add_argument("--json", action="store_true", help="Output as JSON")
        return p

    p_update = _lifecycle("update", "Reinstall skills whose registry version changed")
    p_update.add_argument("--check", action="store_true", help="Report only; exit 2 if anything is outdated")
    p_update.add_argument("--force", action="store_true", help="Reinstall even when the version matches")
    _lifecycle("enable", "Put a disabled skill back into its tool's skills directory")
    _lifecycle("disable", "Move a skill out of its tool's skills directory without deleting it")
    p_uninstall = _lifecycle("uninstall", "Move installed skills to the recycle bin")
    p_uninstall.add_argument("--force", action="store_true", help="Confirm uninstall")

    # trash / restore / purge
    p_trash = subparsers.add_parser("trash", help="List the recycle bin")
    p_trash.add_argument("--json", action="store_true", help="Output as JSON")
    p_restore = subparsers.add_parser("restore", help="Restore the latest trashed copy of a skill")
    p_restore.add_argument("skill_name", help="Name of the skill to restore")
    p_restore.add_argument("--force", action="store_true", help="Replace files already at the original path")
    p_restore.add_argument("--json", action="store_true", help="Output as JSON")
    p_purge = subparsers.add_parser("purge", help="Delete recycle-bin items older than a TTL")
    p_purge.add_argument("--older-than", type=int, default=ledger.DEFAULT_TRASH_TTL_DAYS, metavar="DAYS",
                         help=f"Age threshold in days (default: {ledger.DEFAULT_TRASH_TTL_DAYS})")
    p_purge.add_argument("--json", action="store_true", help="Output as JSON")

    return parser


def main() -> None:
    """CLI entry point."""
    parser = build_parser()
    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(1)
    if args.command == "install" and not args.skill_name and not args.tag:
        parser.error("install needs a <skill-name> or --tag")

    commands = {
        "init":    cmd_init,
        "publish": cmd_publish,
        "list":    cmd_list,
        "search":  cmd_search,
        "install": cmd_install,
        "info":    cmd_info,
        "remove":  cmd_remove,
        "stale":   cmd_stale,
        "platforms": cmd_platforms,
        "installed": cmd_installed,
        "update":    cmd_update,
        "enable":    cmd_enable,
        "disable":   cmd_disable,
        "uninstall": cmd_uninstall,
        "trash":     cmd_trash,
        "restore":   cmd_restore,
        "purge":     cmd_purge,
    }

    cmd_func = commands.get(args.command)
    if cmd_func is None:
        parser.print_help()
        sys.exit(1)

    cmd_func(args)


if __name__ == "__main__":
    main()
