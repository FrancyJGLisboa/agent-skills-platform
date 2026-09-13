#!/usr/bin/env python3
"""
Local ledger of installed skills.

Records what ``skill_registry.py install`` put where, so the same CLI can list,
update, enable, disable, uninstall, and restore skills later. The ledger is one
JSON file under the agent-skills home (``~/.agent-skills`` by default, or
``$AGENT_SKILLS_HOME``), next to the ``disabled/`` parking area and the
``trash/`` recycle bin:

    ~/.agent-skills/
      installed.json          one entry per install location
      disabled/<id>/          skill dirs moved out of a tool's tree
      trash/<name>-<stamp>/   uninstalled or removed skills, 30-day default TTL

Entries are keyed by install path: the same skill installed for two platforms
is two entries. Nothing here talks to a network or a registry; callers pass in
what they know.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

LEDGER_VERSION = 1
DEFAULT_TRASH_TTL_DAYS = 30
TRASH_SIDECAR = ".trash.json"


# --- Locations ---

def skills_home() -> Path:
    """Directory holding the ledger, parked disabled skills, and the trash."""
    override = os.environ.get("AGENT_SKILLS_HOME")
    base = Path(override).expanduser() if override else Path.home() / ".agent-skills"
    return base.resolve()


def ledger_path() -> Path:
    return skills_home() / "installed.json"


def disabled_dir() -> Path:
    return skills_home() / "disabled"


def trash_dir() -> Path:
    return skills_home() / "trash"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _stamp(moment: datetime | None = None) -> str:
    return (moment or _now()).strftime("%Y%m%dT%H%M%SZ")


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9._-]+", "-", value.strip().lower()).strip("-.")
    return slug or "unknown"


# --- Ledger I/O ---

def load_ledger() -> dict:
    """Read the ledger; a missing file is an empty ledger, a corrupt one is fatal."""
    path = ledger_path()
    if not path.exists():
        return {"version": LEDGER_VERSION, "skills": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        print(f"Error reading {path}: {exc}", file=sys.stderr)
        sys.exit(1)
    data.setdefault("version", LEDGER_VERSION)
    data.setdefault("skills", [])
    return data


def save_ledger(data: dict) -> None:
    """Atomic write: write to .tmp then rename."""
    path = ledger_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    try:
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        tmp.replace(path)
    except OSError as exc:
        if tmp.exists():
            tmp.unlink()
        print(f"Error writing {path}: {exc}", file=sys.stderr)
        sys.exit(1)


# --- Entries ---

def make_entry(
    *, name: str, author: str, version: str, platform: str, scope: str,
    path: Path, registry: Path, tags: list[str],
) -> dict:
    return {
        "name": name,
        "author": author,
        "version": version,
        "platform": platform,
        "scope": scope,
        "path": str(path),
        "registry": str(registry),
        "tags": list(tags),
        "installed_at": _now().isoformat(timespec="seconds"),
        "enabled": True,
    }


def record_install(entry: dict) -> None:
    """Insert or replace the ledger entry for ``entry['path']``."""
    data = load_ledger()
    data["skills"] = [s for s in data["skills"] if s.get("path") != entry["path"]]
    data["skills"].append(entry)
    save_ledger(data)


def forget(path: str) -> dict | None:
    """Drop the entry for an install path; return it, or None if absent."""
    data = load_ledger()
    found = next((s for s in data["skills"] if s.get("path") == path), None)
    if found is not None:
        data["skills"] = [s for s in data["skills"] if s is not found]
        save_ledger(data)
    return found


def select(
    entries: list[dict], *, name: str | None = None, tag: str | None = None,
    platform: str | None = None, scope: str | None = None,
) -> list[dict]:
    """Filter ledger entries. ``name`` and ``tag`` are the bulk-op selectors."""
    out = entries
    if name is not None:
        out = [s for s in out if s.get("name") == name]
    if tag is not None:
        out = [s for s in out if tag in s.get("tags", [])]
    if platform is not None:
        out = [s for s in out if s.get("platform") == platform]
    if scope is not None:
        out = [s for s in out if s.get("scope") == scope]
    return out


def current_location(entry: dict) -> Path:
    """Where the skill's files are right now: its install path, or its parking spot."""
    if entry.get("enabled", True):
        return Path(entry["path"])
    return Path(entry["parked_path"])


# --- Enable / disable ---

def _parking_spot(entry: dict) -> Path:
    # One parking spot per install path, so the same skill on two platforms
    # cannot collide when both are disabled.
    digest = hashlib.sha256(entry["path"].encode("utf-8")).hexdigest()[:8]
    return disabled_dir() / f"{entry['name']}-{_slug(entry['platform'])}-{_slug(entry['scope'])}-{digest}"


def disable(entry: dict) -> dict:
    """Move the skill out of its tool's tree. Idempotent."""
    if not entry.get("enabled", True):
        return entry
    source = Path(entry["path"])
    if not source.exists():
        raise FileNotFoundError(f"installed skill files missing at {source}")
    target = _parking_spot(entry)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        shutil.rmtree(target)
    shutil.move(str(source), str(target))
    entry["enabled"] = False
    entry["parked_path"] = str(target)
    record_install(entry)
    return entry


def enable(entry: dict) -> dict:
    """Move a parked skill back into its tool's tree. Idempotent."""
    if entry.get("enabled", True):
        return entry
    source = Path(entry["parked_path"])
    target = Path(entry["path"])
    if not source.exists():
        raise FileNotFoundError(f"parked skill files missing at {source}")
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        shutil.rmtree(target)
    shutil.move(str(source), str(target))
    entry["enabled"] = True
    entry.pop("parked_path", None)
    record_install(entry)
    return entry


# --- Recycle bin ---

def trash_item_dir(name: str, moment: datetime | None = None) -> Path:
    return trash_dir() / f"{name}-{_stamp(moment)}"


def move_to_trash(source: Path, meta: dict, *, kind: str) -> Path:
    """Move ``source`` into the trash with a sidecar describing how to restore it.

    ``kind`` is ``"install"`` (meta is a ledger entry) or ``"registry"`` (meta
    is a registry entry plus the registry path it came from).
    """
    if not source.exists():
        raise FileNotFoundError(f"nothing to trash at {source}")
    item = trash_item_dir(meta["name"])
    # Two trashings within the same second: keep both.
    suffix = 1
    while item.exists():
        item = item.with_name(f"{item.name}-{suffix}")
        suffix += 1
    item.mkdir(parents=True)
    shutil.move(str(source), str(item / "files"))
    sidecar = {
        "kind": kind,
        "name": meta["name"],
        "trashed_at": _now().isoformat(timespec="seconds"),
        "origin": str(source),
        "meta": meta,
    }
    (item / TRASH_SIDECAR).write_text(json.dumps(sidecar, indent=2) + "\n", encoding="utf-8")
    return item


def list_trash() -> list[dict]:
    """Every trash item with a readable sidecar, newest first."""
    root = trash_dir()
    if not root.exists():
        return []
    items: list[dict] = []
    for item in root.iterdir():
        sidecar = item / TRASH_SIDECAR
        if not sidecar.is_file():
            continue
        try:
            data = json.loads(sidecar.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        data["item"] = str(item)
        items.append(data)
    items.sort(key=lambda d: d.get("trashed_at", ""), reverse=True)
    return items


def restore_from_trash(item: dict, *, force: bool = False) -> Path:
    """Move a trash item's files back to their origin and delete the item."""
    origin = Path(item["origin"])
    files = Path(item["item"]) / "files"
    if not files.exists():
        raise FileNotFoundError(f"trash item has no files: {item['item']}")
    if origin.exists():
        if not force:
            raise FileExistsError(f"{origin} already exists; use --force to replace it")
        shutil.rmtree(origin)
    origin.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(files), str(origin))
    shutil.rmtree(item["item"], ignore_errors=True)
    return origin


def purge_trash(older_than_days: int = DEFAULT_TRASH_TTL_DAYS, *, now: datetime | None = None) -> list[dict]:
    """Delete trash items older than the TTL; return what was purged."""
    cutoff = (now or _now()) - timedelta(days=older_than_days)
    purged: list[dict] = []
    for item in list_trash():
        try:
            trashed_at = datetime.fromisoformat(item["trashed_at"])
        except (KeyError, ValueError):
            continue
        if trashed_at <= cutoff:
            shutil.rmtree(item["item"], ignore_errors=True)
            purged.append(item)
    return purged
