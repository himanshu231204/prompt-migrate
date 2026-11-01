"""Declared local environments and SQLite connection lifecycle.

Callers resolve environment names before opening connections. Connection helpers
accept the canonical name; the migration layer owns BEGIN IMMEDIATE and replay.
"""
from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
import json
import os
from pathlib import Path
import re
import sqlite3
import tempfile
from typing import Any
import warnings

from . import protocol
from .errors import (
    EnvironmentAdoptionWarning, EnvironmentNotDeclaredError, InitializationError,
    ProductionNameWarning, SchemaError, StorageError,
)


def _validate_name(name: str) -> None:
    if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,63}", name):
        raise SchemaError("Environment must be alphanumeric, starting with a letter")
    if re.fullmatch(r"(?i:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])", name):
        raise SchemaError("Environment name is reserved on Windows")


def _root(project_dir: Path) -> Path:
    root = Path(project_dir).resolve() / ".promptmigrate"
    if not (root / "versions").is_dir() or not (root / "drafts").is_dir():
        raise InitializationError("Not initialized. Run: promptmigrate init")
    return root


def read_environments(project_dir: Path) -> tuple[dict[str, dict[str, Any]], bool]:
    """Read declarations, or infer legacy declarations without writing any files."""
    root = _root(project_dir)
    path = root / "environments.json"
    if path.exists() or path.is_symlink():
        value, _raw, _rules = protocol.load_json(path, kind="environments", root=root)
        if not isinstance(value, dict) or set(value) != {"environments"} or not isinstance(value["environments"], dict):
            raise SchemaError("Invalid environments file: expected exactly {'environments': object}")
        environments = value["environments"]
        existed = True
    else:
        states = sorted((p for p in (root / "states").glob("*.sqlite3") if p.is_file()), key=lambda p: p.stem.lower())
        environments = {p.stem: {} for p in states} if states else {"dev": {}, "staging": {}}
        existed = False
    for name, metadata in environments.items():
        _validate_name(name)
        if not isinstance(metadata, dict):
            raise SchemaError(f"Invalid environments file: metadata for {name!r} must be an object")
        if protocol.config_depth(metadata) > protocol.MAX_CONFIG_DEPTH:
            raise SchemaError(f"Invalid environments file: metadata for {name!r} exceeds depth limit")
    collisions = protocol.case_collisions(environments)
    if collisions:
        raise SchemaError(f"Invalid environments file: case-collision {collisions[0]}")
    return environments, existed


def _write_environments(project_dir: Path, environments: dict[str, dict[str, Any]]) -> Path:
    path = _root(project_dir) / "environments.json"
    text = json.dumps({"environments": environments}, ensure_ascii=False, indent=2) + "\n"
    if len(text.encode("utf-8")) > protocol.MAX_CONTROL_FILE_BYTES:
        raise SchemaError(f"Invalid environments file: output exceeds the {protocol.MAX_CONTROL_FILE_BYTES}-byte limit")
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="\n", dir=path.parent,
                                         prefix=".environments-", suffix=".tmp", delete=False) as file:
            temporary = Path(file.name)
            file.write(text)
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return path


@contextmanager
def _manifest_lock(project_dir: Path) -> Iterator[None]:
    """Serialize manifest read-modify-write operations across threads and processes."""
    path = _root(project_dir) / "states" / ".environments.lock"
    path.parent.mkdir(exist_ok=True)
    with path.open("a+b") as lock:
        lock.seek(0, os.SEEK_END)
        if lock.tell() == 0:
            lock.write(b"\0")
            lock.flush()
        lock.seek(0)
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(lock.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            if os.name == "nt":
                msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def _warn_adoption() -> None:
    warnings.warn("Adopted legacy environments into environments.json.", EnvironmentAdoptionWarning, stacklevel=3)


def _warn_production(name: str) -> None:
    if name.lower() in {"prod", "production", "live"}:
        warnings.warn(f"'{name}' is local SQLite state only; PromptMigrate does not deploy anything.",
                      ProductionNameWarning, stacklevel=3)


def resolve_environment(project_dir: Path, env: str, *, mutating: bool = False) -> str:
    """Resolve case-insensitively, persisting legacy declarations only on mutation."""
    _validate_name(env)
    if mutating:
        with _manifest_lock(project_dir):
            environments, existed = read_environments(project_dir)
            name = next((name for name in environments if name.lower() == env.lower()), None)
            if name is None:
                raise EnvironmentNotDeclaredError(env)
            if not existed:
                _write_environments(project_dir, environments)
                _warn_adoption()
    else:
        environments, _existed = read_environments(project_dir)
        name = next((name for name in environments if name.lower() == env.lower()), None)
        if name is None:
            raise EnvironmentNotDeclaredError(env)
    _warn_production(name)
    return name


def add_environment(project_dir: Path, name: str) -> Path:
    """Atomically declare a new name, retaining all existing metadata."""
    _validate_name(name)
    with _manifest_lock(project_dir):
        environments, existed = read_environments(project_dir)
        if any(existing.lower() == name.lower() for existing in environments):
            raise SchemaError(f"Environment {name!r} is already declared")
        environments[name] = {}
        path = _write_environments(project_dir, environments)
        if not existed:
            _warn_adoption()
    _warn_production(name)
    return path


def list_environments(project_dir: Path) -> list[tuple[str, bool]]:
    """List canonical declarations and state-file presence without opening SQLite."""
    environments, _existed = read_environments(project_dir)
    states = _root(project_dir) / "states"
    return [(name, (states / f"{name}.sqlite3").is_file()) for name in sorted(environments, key=str.lower)]


def _db_path(project_dir: Path, env: str) -> Path:
    _validate_name(env)
    path = _root(project_dir) / "states" / f"{env}.sqlite3"
    if path.is_symlink():
        raise StorageError(f"Invalid environment state {env!r}: database path is a symbolic link")
    return path


@contextmanager
def connect_readonly(project_dir: Path, env: str) -> Iterator[sqlite3.Connection | None]:
    """Yield base state for an absent DB, otherwise a checked, read-only connection."""
    path = _db_path(project_dir, env)
    if not path.exists():
        if path.is_symlink():
            raise StorageError(f"Invalid environment state {env!r}: database path is a dangling symbolic link")
        yield None
        return
    connection = None
    try:
        try:
            connection = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=10)
            tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if not {"applied_revisions", "prompts"} <= tables:
                raise StorageError(f"Invalid environment state {env!r}: missing required tables")
        except sqlite3.Error as exc:
            raise StorageError(f"Cannot read environment state {env!r}: {exc}") from exc
        yield connection
    finally:
        if connection is not None:
            connection.close()


@contextmanager
def connect_write(project_dir: Path, env: str) -> Iterator[sqlite3.Connection]:
    """Initialize writable storage, commit on success, roll back on error, always close."""
    path = _db_path(project_dir, env)
    path.parent.mkdir(exist_ok=True)
    existed = path.exists()
    connection = sqlite3.connect(path, timeout=10)
    try:
        connection.execute("PRAGMA busy_timeout=10000")
        connection.execute("PRAGMA synchronous=FULL")
        connection.execute("PRAGMA foreign_keys=ON")
        if existed:
            tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if not {"applied_revisions", "prompts"} <= tables:
                raise StorageError(f"Invalid environment state {env!r}: missing required tables")
        else:
            connection.execute("""
                CREATE TABLE applied_revisions (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT,
                    revision TEXT UNIQUE NOT NULL,
                    checksum TEXT NOT NULL,
                    applied_at TEXT NOT NULL
                )
            """)
            connection.execute("""
                CREATE TABLE prompts (
                    name TEXT PRIMARY KEY,
                    config TEXT NOT NULL
                )
            """)
        connection.commit()
        yield connection
        connection.commit()
    except BaseException:
        connection.rollback()
        raise
    finally:
        connection.close()
