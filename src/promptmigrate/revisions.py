"""Source history: revision files, the linear revision graph, and replay of changes from the empty state."""

from __future__ import annotations

import hashlib
import json
import re
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import project, protocol
from .errors import LegacyRevisionWarning, MigrationConflictError, RevisionGraphError, SchemaError

_V0_KEYS = ("revision", "down_revision", "message", "created_at", "changes")
_V1_KEYS = frozenset({"format_version", *_V0_KEYS})
_LEGACY = "revision {rid}: {rule} (accepted for compatibility; create a new revision to fix)"


@dataclass(frozen=True)
class Revision:
    revision: str
    down_revision: str | None
    message: str
    created_at: str
    changes: dict[str, dict[str, Any]]
    checksum: str
    path: Path
    format_version: int = 0
    line_ending_checksums: frozenset[str] = frozenset()  # v0 only: raw-byte digests of the LF and CRLF re-saves


def _hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def line_ending_variants(raw: bytes) -> set[str]:
    """Raw-byte digests of `raw` re-saved with LF and with CRLF line endings (ADR-027). The v0 checksum is unchanged."""
    lf = raw.replace(b"\r\n", b"\n")
    return {_hash(lf), _hash(lf.replace(b"\n", b"\r\n"))}


def _v1_checksum(item: dict[str, Any]) -> str:
    """Protocol v1 (ADR-026): SHA-256 of the canonical JSON of the whole parsed file, tagged so it never equals v0."""
    return "v1:" + _hash(protocol.canonical(item).encode("utf-8"))


def _format_version(item: dict[str, Any], name: str) -> int:
    """0 for a file without `format_version` (frozen, ADR-025), 1 for the JSON integer 1; anything else is tier A."""
    if "format_version" not in item:
        return 0
    if type(item["format_version"]) is not int or item["format_version"] != 1:
        raise SchemaError(f"Unsupported format_version in {name}")
    unknown = sorted(set(item) - _V1_KEYS)
    if unknown:
        raise SchemaError(f"Unknown top-level key in {name}: {', '.join(unknown)}")
    return 1


def load_revisions(project_dir: Path) -> list[Revision]:
    root = project.require_init(project_dir)
    unsorted: dict[str, Revision] = {}
    violations: dict[str, list[str]] = {}
    for path in sorted((root / "versions").glob("*.json")):
        item, raw, file_rules = protocol.load_json(path, kind="revision", root=root)
        if not isinstance(item, dict):
            raise SchemaError(f"Invalid migration format: {path.name}")
        version = _format_version(item, path.name)
        if not all(k in item for k in _V0_KEYS):
            raise SchemaError(f"Invalid migration format: {path.name}")
        rid, parent, changes = item["revision"], item["down_revision"], item["changes"]
        if not isinstance(rid, str) or not re.fullmatch(r"[a-f0-9]{12}", rid):
            raise SchemaError(f"Invalid revision id in {path.name}")
        if parent is not None and (not isinstance(parent, str) or not re.fullmatch(r"[a-f0-9]{12}", parent)):
            raise SchemaError(f"Invalid down_revision in {path.name}")
        if not isinstance(item["message"], str) or not isinstance(item["created_at"], str):
            raise SchemaError(f"Invalid metadata in {path.name}")
        if not isinstance(changes, dict) or not changes:
            raise SchemaError(f"Migration must contain nonempty changes: {path.name}")
        for name, change in changes.items():
            if not isinstance(change, dict) or set(change) != {"before", "after"}:
                raise SchemaError(f"Invalid change operation in {path.name}: {name}")
            for field in ("before", "after"):
                if change[field] is not None:
                    protocol.validate_config(name, change[field])
        if rid in unsorted:
            raise RevisionGraphError(f"Duplicate revision id: {rid}")
        found = list(file_rules)
        for name, change in changes.items():
            if protocol.same(change["before"], change["after"]):
                found.append(f"no-op-change {name}")
            # Only after values: replay makes every before equal an earlier after, so each violation shows once.
            if change["after"] is not None:
                found.extend(protocol.config_violations(name, change["after"]))
        violations[rid] = found
        variants: frozenset[str] = frozenset()
        if version == 0:
            checksum = _hash(raw)
            # CR/LF bytes (b"\r\n") are only ever whitespace in UTF-8 JSON. `json.loads` also auto-detects and
            # accepts UTF-16/32, where a single code unit such as U+0D0A encodes as the same two bytes as a byte-
            # level CR LF; replacing it would treat a real value change as a line-ending-only edit (Finding 1,
            # 2026-11-13 final review). `raw.decode("utf-8")` alone is not a reliable test here: a mostly-ASCII
            # UTF-16 file is full of null bytes, which are themselves valid (if meaningless) UTF-8, so it can
            # decode without error even though `json.loads` did not read it as UTF-8. Ask the same question
            # `json.loads` asks of these bytes (`json.detect_encoding`, the encoding-sniffing it uses for bytes
            # input) instead, so "UTF-8" here means what it means to the loader, with or without a BOM.
            if json.detect_encoding(raw) in ("utf-8", "utf-8-sig"):
                variants = frozenset(line_ending_variants(raw))
        else:
            try:
                checksum = _v1_checksum(item)
            except UnicodeEncodeError as exc:
                raise SchemaError(f"Invalid string in {path.name}: unpaired surrogate") from exc
        unsorted[rid] = Revision(
            rid, parent, item["message"], item["created_at"], changes, checksum, path, version, variants
        )

    if not unsorted:
        return []
    roots = [r for r in unsorted.values() if r.down_revision is None]
    if len(roots) != 1:
        raise RevisionGraphError("MVP requires exactly one root revision (linear history)")
    children: dict[str, list[Revision]] = {}
    for r in unsorted.values():
        if r.down_revision is not None:
            if r.down_revision not in unsorted:
                raise RevisionGraphError(f"Missing parent of revision {r.revision}: {r.down_revision}")
            children.setdefault(r.down_revision, []).append(r)
    if any(len(kids) > 1 for kids in children.values()):
        raise RevisionGraphError("Branching detected. MVP only supports one linear head; resolve in Git before deploying")
    result = []
    current = roots[0]
    while current is not None and current.revision not in {r.revision for r in result}:
        result.append(current)
        current = children.get(current.revision, [None])[0]
    if len(result) != len(unsorted):
        raise RevisionGraphError("Disconnected or cyclic migration history")
    # Validate declarative preconditions across all revisions, independently of environments.
    replay_revisions(result)
    names: set[str] = set()
    for r in result:
        for name, change in r.changes.items():
            if change["after"] is None:
                names.discard(name)
            else:
                names.add(name)
        found = violations[r.revision]
        found.extend(f"case-collision {group}" for group in protocol.case_collisions(names)
                     if any(member in r.changes for member in group.split("/")))
        for rule in found:
            warnings.warn(_LEGACY.format(rid=r.revision, rule=rule), LegacyRevisionWarning, stacklevel=2)
    return result


def _apply_changes(
    state: dict[str, dict[str, Any]],
    revision: Revision,
    *,
    backward: bool = False,
) -> None:
    for name, change in revision.changes.items():
        expected = change["after"] if backward else change["before"]
        replacement = change["before"] if backward else change["after"]
        if not protocol.same(state.get(name), expected):
            direction = "downgrade" if backward else "upgrade"
            raise MigrationConflictError(
                f"{direction} {revision.revision}: unexpected current value for {name!r}; "
                "possible drift or invalid revision dependency"
            )
        if replacement is None:
            state.pop(name, None)
        else:
            state[name] = replacement


def replay_revisions(revisions: list[Revision]) -> dict[str, dict[str, Any]]:
    state: dict[str, dict[str, Any]] = {}
    for r in revisions:
        _apply_changes(state, r)
    return state
