"""Local MVP of an Alembic-like migration engine for prompt configurations.

A migration specifies exact before/after JSON documents. Each environment has an
independent SQLite state. Applying migrations and recording revisions is atomic.
This is deliberately local-only and does not deploy to remote prompt providers.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import re
import sqlite3
import uuid
import warnings
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .errors import (
    DriftError, InitializationError, IntegrityError, LegacyRevisionWarning, MigrationConflictError, MigrationError,
    PendingRevisionsError, RevisionGraphError, SchemaError, SecretDetectedError, SecretInHistoryWarning,
    SecretRedactedWarning, StaleAllowlistWarning, TargetError,
)
from . import protocol
from . import store
from . import secretscan
from .protocol import canonical, same

_LEGACY = "revision {rid}: {rule} (accepted for compatibility; create a new revision to fix)"
ALLOWLIST_FILE = "secret-allowlist.json"
_REDACTED = "{count} secret-like value(s) redacted from this output; detection is heuristic and can miss secrets"


@dataclass(frozen=True)
class Revision:
    revision: str
    down_revision: str | None
    message: str
    created_at: str
    changes: dict[str, dict[str, Any]]
    checksum: str
    path: Path


def pretty(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, indent=2) + "\n"


def _hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def root_dir(project_dir: Path) -> Path:
    return Path(project_dir).resolve() / ".promptmigrate"


def require_init(project_dir: Path) -> Path:
    root = root_dir(project_dir)
    if not (root / "versions").is_dir() or not (root / "drafts").is_dir():
        raise InitializationError("Not initialized. Run: promptmigrate init")
    return root


def init(project_dir: Path) -> Path:
    root = root_dir(project_dir)
    if root.exists():
        raise InitializationError(f"Already exists: {root}")
    (root / "versions").mkdir(parents=True)
    (root / "drafts").mkdir()
    (root / "states").mkdir()
    (root / ".gitignore").write_text("/states/\n", encoding="utf-8")
    (root / "environments.json").write_text(
        json.dumps({"environments": {"dev": {}, "staging": {}}}, indent=2) + "\n", encoding="utf-8"
    )
    starter = {
        "messages": [{"role": "system", "content": "You are a helpful AI assistant."}],
        "model": "provider/model-id",
        "parameters": {"temperature": 0},
        "tools": [],
        "response_schema": None,
    }
    (root / "drafts" / "assistant.json").write_text(pretty(starter), encoding="utf-8")
    return root


def read_drafts(project_dir: Path) -> dict[str, dict[str, Any]]:
    root = require_init(project_dir)
    drafts = {}
    for path in sorted((root / "drafts").iterdir()):
        if path.is_dir() or path.suffix != ".json":
            continue
        name = path.stem
        value, _raw, _rules = protocol.load_json(path, kind="draft", root=root)
        protocol.validate_config(name, value)
        found = protocol.config_violations(name, value)
        if found:
            raise SchemaError(f"Invalid draft {path.name}: {', '.join(found)}")
        drafts[name] = value
    collisions = protocol.case_collisions(drafts)
    if collisions:
        raise SchemaError(f"Invalid drafts: case-collision {collisions[0]}")
    return drafts


def load_allowlist(project_dir: Path) -> list[secretscan.AllowEntry]:
    """The reviewed secret allowlist (.promptmigrate/secret-allowlist.json); empty when the file is absent."""
    root = require_init(project_dir)
    path = root / ALLOWLIST_FILE
    if not path.exists() and not path.is_symlink():
        return []
    value, _raw, _rules = protocol.load_json(path, kind="allowlist", root=root)
    return secretscan.parse_allowlist(value, path.name)


def load_revisions(project_dir: Path) -> list[Revision]:
    root = require_init(project_dir)
    unsorted: dict[str, Revision] = {}
    violations: dict[str, list[str]] = {}
    for path in sorted((root / "versions").glob("*.json")):
        item, raw, file_rules = protocol.load_json(path, kind="revision", root=root)
        if not isinstance(item, dict) or not all(
            k in item for k in ("revision", "down_revision", "message", "created_at", "changes")
        ):
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
            if same(change["before"], change["after"]):
                found.append(f"no-op-change {name}")
            # Only after values: replay makes every before equal an earlier after, so each violation shows once.
            if change["after"] is not None:
                found.extend(protocol.config_violations(name, change["after"]))
        violations[rid] = found
        unsorted[rid] = Revision(
            rid, parent, item["message"], item["created_at"], changes, _hash(raw), path
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
        if not same(state.get(name), expected):
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


def draft_diff(project_dir: Path) -> dict[str, dict[str, Any]]:
    expected = replay_revisions(load_revisions(project_dir))
    wanted = read_drafts(project_dir)
    return {
        name: {"before": expected.get(name), "after": wanted.get(name)}
        for name in sorted(expected.keys() | wanted.keys())
        if not same(expected.get(name), wanted.get(name))
    }


def redacted_diff(project_dir: Path) -> tuple[dict[str, dict[str, Any]], list[dict[str, str]]]:
    """draft_diff() for display: secret-like values replaced by "<redacted:RULE>", plus what was redacted.

    Redacted output is not a config source: never feed it back into a draft or an application.
    """
    allow = load_allowlist(project_dir)
    changes, redacted = {}, []
    for name, change in draft_diff(project_dir).items():
        sides = {}
        for side in ("before", "after"):
            value = change[side]
            if value is not None:
                value, paths = secretscan.redact(name, value, allow)
                redacted += [{"name": name, "side": side, "path": path} for path in paths]
            sides[side] = value
        changes[name] = sides
    if redacted:
        warnings.warn(_REDACTED.format(count=len(redacted)), SecretRedactedWarning, stacklevel=2)
    return changes, redacted


def revision(project_dir: Path, message: str) -> Revision:
    if not message.strip():
        raise SchemaError("Revision message cannot be empty")
    all_revisions = load_revisions(project_dir)
    changes = draft_diff(project_dir)
    if not changes:
        raise SchemaError("No changes between drafts and migration head")
    rid = uuid.uuid4().hex[:12]
    parent = all_revisions[-1].revision if all_revisions else None
    for name, change in changes.items():
        if change["after"] is not None:
            found = protocol.config_violations(name, change["after"])
            if found:
                raise SchemaError(f"New revision would be invalid: {', '.join(found)}")
    allow = load_allowlist(project_dir)
    findings = [finding for name, change in changes.items() if change["after"] is not None
                for finding in secretscan.scan(name, change["after"], allow)]
    findings += secretscan.scan("(message)", {"message": message.strip()}, allow)
    if findings:
        raise SecretDetectedError(findings)
    item = {
        "revision": rid,
        "down_revision": parent,
        "message": message.strip(),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "changes": changes,
    }
    text = pretty(item)
    # write_text translates "\n" to os.linesep, so this is the exact size of the file it writes.
    size = len(text.replace("\n", os.linesep).encode("utf-8"))
    if size > protocol.MAX_REVISION_BYTES:
        raise SchemaError(f"New revision would be {size} bytes; the limit is {protocol.MAX_REVISION_BYTES}")
    for name, change in changes.items():
        if change["before"] is not None:
            carried = protocol.config_violations(name, change["before"])
            if carried:
                warnings.warn(f"revision {rid}: {name} before carries {', '.join(carried)} from history "
                              "(copied for compatibility)", LegacyRevisionWarning, stacklevel=2)
    for name, change in changes.items():
        if change["before"] is not None:
            for finding in secretscan.scan(name, change["before"], allow):
                warnings.warn(f"{finding.name} {finding.path} {finding.rule} copied from history into before; "
                              "the credential must be rotated", SecretInHistoryWarning, stacklevel=2)
    root = require_init(project_dir)
    path = root / "versions" / f"{rid}_{re.sub(r'[^a-z0-9]+', '_', message.lower()).strip('_')[:50] or 'revision'}.json"
    path.write_text(text, encoding="utf-8")
    return load_revisions(project_dir)[-1]


def _applied(db: sqlite3.Connection) -> list[tuple[str, str]]:
    return [(rid, checksum) for rid, checksum in db.execute(
        "SELECT revision, checksum FROM applied_revisions ORDER BY seq"
    ).fetchall()]


def _actual(db: sqlite3.Connection) -> dict[str, dict[str, Any]]:
    return {name: json.loads(config) for name, config in db.execute(
        "SELECT name, config FROM prompts"
    ).fetchall()}


def _verify(db: sqlite3.Connection, revisions: list[Revision]) -> int:
    applied = _applied(db)
    if len(applied) > len(revisions):
        raise IntegrityError("Environment contains more applied revisions than source history")
    for index, (rid, checksum) in enumerate(applied):
        source = revisions[index]
        if rid != source.revision:
            raise IntegrityError(f"Applied revisions diverge from source history at index {index}")
        if checksum != source.checksum:
            raise IntegrityError(f"Migration file was modified after apply: {rid}")
    expected = replay_revisions(revisions[:len(applied)])
    actual = _actual(db)
    names = sorted(name for name in actual.keys() | expected.keys()
                   if not same(actual.get(name), expected.get(name)))
    if names:
        raise DriftError(f"Environment drift detected for prompts: {', '.join(names)}")
    return len(applied)


def check(project_dir: Path, env: str, require_head: bool = False) -> tuple[int, int]:
    env = store.resolve_environment(project_dir, env)
    revisions = load_revisions(project_dir)
    with store.connect_readonly(project_dir, env) as db:
        count = _verify(db, revisions) if db is not None else 0
    if require_head and count != len(revisions):
        raise PendingRevisionsError(f"Environment is behind head: {len(revisions) - count} pending revisions")
    return count, len(revisions)


def audit_secrets(project_dir: Path) -> None:
    """Warn about secret-like values in source history and about allowlist entries that match nothing.

    Warnings only: `check` verifies integrity, not hygiene. Secrets in history stay in Git and must be rotated.
    """
    revisions = load_revisions(project_dir)
    allow = load_allowlist(project_dir)
    used: set[secretscan.AllowEntry] = set()
    for r in revisions:
        seen: list[secretscan.Finding] = []
        seen += [f for f in secretscan.scan("(message)", {"message": r.message}, allow, used) if f not in seen]
        for name, change in r.changes.items():
            for side in ("before", "after"):
                if change[side] is not None:
                    seen += [f for f in secretscan.scan(name, change[side], allow, used) if f not in seen]
        for finding in seen:
            warnings.warn(f"revision {r.revision}: {finding.name} {finding.path} {finding.rule}",
                          SecretInHistoryWarning, stacklevel=2)
    try:
        drafts = read_drafts(project_dir)
    except SchemaError:
        return  # an unreadable draft is reported by diff/revision; without drafts, staleness is unknown
    for name, config in drafts.items():
        secretscan.scan(name, config, allow, used)
    for entry in allow:
        if entry not in used:
            warnings.warn(f"secret allowlist entry {entry.name} {entry.path} {entry.rule} matched nothing in drafts "
                          "or history", StaleAllowlistWarning, stacklevel=2)


def upgrade(project_dir: Path, env: str, target: str = "head") -> list[str]:
    env = store.resolve_environment(project_dir, env, mutating=True)
    revisions = load_revisions(project_dir)
    targets = [r.revision for r in revisions]
    if target != "head" and target not in targets:
        raise TargetError(f"Unknown target revision: {target}")
    target_count = len(revisions) if target == "head" else targets.index(target) + 1
    with store.connect_write(project_dir, env) as db:
        db.execute("BEGIN IMMEDIATE")
        applied_count = _verify(db, revisions)
        if applied_count > target_count:
            raise TargetError("Upgrade target is behind current revision; use downgrade")
        state = _actual(db)
        for r in revisions[applied_count:target_count]:
            _apply_changes(state, r)
            for name, change in r.changes.items():
                after = change["after"]
                if after is None:
                    db.execute("DELETE FROM prompts WHERE name=?", (name,))
                else:
                    db.execute(
                        "INSERT INTO prompts(name, config) VALUES(?, ?) "
                        "ON CONFLICT(name) DO UPDATE SET config=excluded.config",
                        (name, canonical(after)),
                    )
            db.execute(
                "INSERT INTO applied_revisions(revision, checksum, applied_at) VALUES(?, ?, ?)",
                (r.revision, r.checksum, datetime.now(timezone.utc).isoformat()),
            )
    return targets[applied_count:target_count]


def downgrade(project_dir: Path, env: str, target: str = "-1") -> list[str]:
    env = store.resolve_environment(project_dir, env, mutating=True)
    revisions = load_revisions(project_dir)
    targets = [r.revision for r in revisions]
    with store.connect_write(project_dir, env) as db:
        db.execute("BEGIN IMMEDIATE")
        applied_count = _verify(db, revisions)
        if target == "-1":
            target_count = max(0, applied_count - 1)
        elif target == "base":
            target_count = 0
        elif target in targets:
            target_count = targets.index(target) + 1
        else:
            raise TargetError(f"Unknown target revision: {target}")
        if target_count > applied_count:
            raise TargetError("Downgrade target is ahead of current revision; use upgrade")
        state = _actual(db)
        reversed_revisions = list(reversed(revisions[target_count:applied_count]))
        for r in reversed_revisions:
            _apply_changes(state, r, backward=True)
            for name, change in r.changes.items():
                before = change["before"]
                if before is None:
                    db.execute("DELETE FROM prompts WHERE name=?", (name,))
                else:
                    db.execute(
                        "INSERT INTO prompts(name, config) VALUES(?, ?) "
                        "ON CONFLICT(name) DO UPDATE SET config=excluded.config",
                        (name, canonical(before)),
                    )
            db.execute("DELETE FROM applied_revisions WHERE revision=?", (r.revision,))
    return [r.revision for r in reversed_revisions]


def get_config(project_dir: Path, env: str, name: str) -> dict[str, Any]:
    env = store.resolve_environment(project_dir, env)
    revisions = load_revisions(project_dir)
    with store.connect_readonly(project_dir, env) as db:
        if db is None:
            row = None
        else:
            _verify(db, revisions)
            row = db.execute("SELECT config FROM prompts WHERE name=?", (name,)).fetchone()
    if not row:
        raise TargetError(f"No prompt named {name!r} in environment {env!r}")
    return json.loads(row[0])


def env_add(project_dir: Path, name: str) -> Path:
    require_init(project_dir)
    return store.add_environment(project_dir, name)


def env_list(project_dir: Path) -> list[tuple[str, bool]]:
    require_init(project_dir)
    return store.list_environments(project_dir)


def redacted_config(project_dir: Path, env: str, name: str) -> tuple[dict[str, Any], list[str]]:
    """get_config() for display: secret-like values replaced by "<redacted:RULE>", plus the redacted paths."""
    config, paths = secretscan.redact(name, get_config(project_dir, env, name), load_allowlist(project_dir))
    if paths:
        warnings.warn(_REDACTED.format(count=len(paths)), SecretRedactedWarning, stacklevel=2)
    return config, paths


def redacted_history(project_dir: Path, load=None) -> tuple[list[Revision], list[str]]:
    """load_revisions() for display: a secret-like message is replaced by "<redacted:RULE>"; returns the ids redacted."""
    allow = load_allowlist(project_dir)
    shown, redacted = [], []
    for r in (load or load_revisions)(project_dir):
        value, paths = secretscan.redact("(message)", {"message": r.message}, allow)
        if paths:
            r = dataclasses.replace(r, message=value["message"])
            redacted.append(r.revision)
        shown.append(r)
    if redacted:
        warnings.warn(_REDACTED.format(count=len(redacted)), SecretRedactedWarning, stacklevel=2)
    return shown, redacted
