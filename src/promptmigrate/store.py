"""Declared local environments and SQLite connection lifecycle.

Callers resolve environment names before opening connections. Connection helpers
accept the canonical name; the migration layer owns BEGIN IMMEDIATE and replay.
"""
from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
import tempfile
from typing import Any
from urllib.parse import quote
import warnings

from . import protocol
from .errors import (
    EnvironmentAdoptionWarning, EnvironmentNotDeclaredError, InitializationError,
    ProductionNameWarning, SchemaError, StorageError,
)


_NAME = re.compile(r"[A-Za-z][A-Za-z0-9_-]{0,63}")
DEFAULT_ENVIRONMENTS = ("dev", "staging")


def _validate_name(name: str) -> None:
    if not isinstance(name, str) or not _NAME.fullmatch(name):
        raise SchemaError("Environment must be alphanumeric, starting with a letter")
    if re.fullmatch(r"(?i:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])", name):
        raise SchemaError("Environment name is reserved on Windows")


def root_dir(project_dir: Path) -> Path:
    return Path(project_dir).resolve() / ".promptmigrate"


def require_init(project_dir: Path) -> Path:
    """Return the .promptmigrate directory, or raise InitializationError if the project is not initialized."""
    root = root_dir(project_dir)
    if not (root / "versions").is_dir() or not (root / "drafts").is_dir():
        raise InitializationError("Not initialized. Run: promptmigrate init")
    return root


def _is_linklike(path: Path) -> bool:
    if path.is_symlink():
        return True
    if os.name == "nt":
        try:
            return bool(path.stat(follow_symlinks=False).st_file_attributes & 0x400)
        except FileNotFoundError:
            return False
    return False


def _states_dir(project_dir: Path) -> Path:
    path = require_init(project_dir) / "states"
    if _is_linklike(path):
        raise StorageError("Invalid environment state: states directory is a symbolic link or junction")
    if path.exists() and not path.is_dir():
        raise StorageError("Invalid environment state: states path is not a directory")
    return path


def _sqlite_uri(path: Path) -> str:
    """Build a read-only SQLite URI without treating a Windows UNC host as authority."""
    if path.drive.startswith("\\\\"):
        return "file://" + quote(path.as_posix(), safe="/") + "?mode=ro"
    return path.as_uri() + "?mode=ro"


def _wal_mode(path: Path) -> bool:
    try:
        with path.open("rb") as database:
            header = database.read(20)
    except OSError as exc:
        raise StorageError(f"Cannot inspect environment state: {exc}") from exc
    return header.startswith(b"SQLite format 3\0") and len(header) >= 20 and 2 in header[18:20]


def read_environments(project_dir: Path) -> tuple[dict[str, dict[str, Any]], bool]:
    """Read declarations, or infer legacy declarations without writing any files."""
    root = require_init(project_dir)
    path = root / "environments.json"
    if path.exists() or path.is_symlink():
        value, _raw, _rules = protocol.load_json(path, kind="environments", root=root)
        if not isinstance(value, dict) or set(value) != {"environments"} or not isinstance(value["environments"], dict):
            raise SchemaError("Invalid environments file: expected exactly {'environments': object}")
        environments = value["environments"]
        existed = True
    else:
        environments = _infer_environments(project_dir)
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


def _infer_environments(project_dir: Path) -> dict[str, dict[str, Any]]:
    """Legacy declarations: the defaults plus every state file a pre-manifest release could have created.

    Those releases validated names with the same syntax, so a stem that fails it was never PromptMigrate state and is
    ignored. Reserved and case-colliding stems stay in and fail closed later, because they may be real state.
    """
    stems = [p.stem for p in _states_dir(project_dir).glob("*.sqlite3") if p.is_file() and _NAME.fullmatch(p.stem)]
    taken = {stem.lower() for stem in stems}
    names = stems + [name for name in DEFAULT_ENVIRONMENTS if name not in taken]
    return {name: {} for name in sorted(names, key=str.lower)}


def canonical_name(environments: dict[str, Any], env: str) -> str | None:
    """Return the declared spelling that matches env case-insensitively, or None."""
    lowered = env.lower()
    return next((name for name in environments if name.lower() == lowered), None)


def display_name(project_dir: Path, env: str) -> str:
    """Return env's declared spelling for status labels, or env unchanged when it is not declared."""
    _validate_name(env)
    environments, _existed = read_environments(project_dir)
    return canonical_name(environments, env) or env


def _new_file_mode(path: Path) -> int:
    """Keep an existing file's permission bits; give a new file the usual umask-derived mode."""
    try:
        return stat.S_IMODE(path.stat().st_mode)
    except FileNotFoundError:
        umask = os.umask(0)
        os.umask(umask)
        return 0o666 & ~umask


def _write_environments(project_dir: Path, environments: dict[str, dict[str, Any]]) -> Path:
    path = require_init(project_dir) / "environments.json"
    text = json.dumps({"environments": environments}, ensure_ascii=False, indent=2) + "\n"
    if len(text.encode("utf-8")) > protocol.MAX_CONTROL_FILE_BYTES:
        raise SchemaError(f"Invalid environments file: output exceeds the {protocol.MAX_CONTROL_FILE_BYTES}-byte limit")
    mode = _new_file_mode(path)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="\n", dir=path.parent,
                                         prefix=".environments-", suffix=".tmp", delete=False) as file:
            temporary = Path(file.name)
            file.write(text)
        # NamedTemporaryFile creates 0600 files; a tracked manifest must stay readable like any other source file.
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return path


@contextmanager
def _project_lock(project_dir: Path) -> Iterator[None]:
    """Serialize project metadata changes and initial environment database setup."""
    root = require_init(project_dir)
    if os.name == "nt":
        import ctypes
        digest = hashlib.sha256(os.fsencode(root)).hexdigest()
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.CreateMutexW.argtypes = (ctypes.c_void_p, ctypes.c_int, ctypes.c_wchar_p)
        kernel.CreateMutexW.restype = ctypes.c_void_p
        kernel.WaitForSingleObject.argtypes = (ctypes.c_void_p, ctypes.c_uint32)
        kernel.WaitForSingleObject.restype = ctypes.c_uint32
        kernel.ReleaseMutex.argtypes = (ctypes.c_void_p,)
        kernel.CloseHandle.argtypes = (ctypes.c_void_p,)
        handle = kernel.CreateMutexW(None, False, f"Global\\PromptMigrate-{digest}")
        if not handle:
            raise OSError(ctypes.get_last_error(), "Could not create environment manifest mutex")
        result = kernel.WaitForSingleObject(handle, 0xFFFFFFFF)
        if result not in (0, 0x80):
            kernel.CloseHandle(handle)
            raise OSError(ctypes.get_last_error(), "Could not acquire environment manifest mutex")
        try:
            yield
        finally:
            kernel.ReleaseMutex(handle)
            kernel.CloseHandle(handle)
    else:
        import fcntl
        descriptor = os.open(root, os.O_RDONLY)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(descriptor)


def _warn_adoption() -> None:
    warnings.warn("Adopted legacy environments into environments.json.", EnvironmentAdoptionWarning, stacklevel=3)


def _warn_production(name: str) -> None:
    if name.lower() in {"prod", "production", "live"}:
        warnings.warn(f"'{name}' is local SQLite state only; PromptMigrate does not deploy anything.",
                      ProductionNameWarning, stacklevel=3)


def resolve_environment(project_dir: Path, env: str, *, mutating: bool = False) -> str:
    """Resolve case-insensitively; with mutating=True, also persist inferred legacy declarations."""
    _validate_name(env)
    if mutating:
        with _project_lock(project_dir):
            name = _resolve_declared(project_dir, env, adopt=True)
    else:
        name = _resolve_declared(project_dir, env, adopt=False)
    _warn_production(name)
    return name


def _resolve_declared(project_dir: Path, env: str, *, adopt: bool) -> str:
    environments, existed = read_environments(project_dir)
    name = canonical_name(environments, env)
    if name is None:
        raise EnvironmentNotDeclaredError(env)
    if adopt and not existed:
        _write_environments(project_dir, environments)
        _warn_adoption()
    return name


def adopt_environments(project_dir: Path) -> None:
    """Persist inferred legacy declarations once; a no-op when the manifest already exists.

    Migration commands call this only after their transaction commits, so a rejected command writes nothing.
    """
    with _project_lock(project_dir):
        environments, existed = read_environments(project_dir)
        if not existed:
            _write_environments(project_dir, environments)
            _warn_adoption()


def add_environment(project_dir: Path, name: str) -> Path:
    """Atomically declare a new name, retaining all existing metadata."""
    _validate_name(name)
    with _project_lock(project_dir):
        environments, existed = read_environments(project_dir)
        if canonical_name(environments, name) is not None:
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
    states = _states_dir(project_dir)
    result = []
    for name in sorted(environments, key=str.lower):
        path = states / f"{name}.sqlite3"
        if _is_linklike(path):
            raise StorageError(f"Invalid environment state {name!r}: database path is a symbolic link")
        result.append((name, path.is_file()))
    return result


def _db_path(project_dir: Path, env: str) -> Path:
    _validate_name(env)
    path = _states_dir(project_dir) / f"{env}.sqlite3"
    if _is_linklike(path):
        raise StorageError(f"Invalid environment state {env!r}: database path is a symbolic link")
    return path


@contextmanager
def connect_readonly(project_dir: Path, env: str) -> Iterator[sqlite3.Connection | None]:
    """Yield base state for an absent DB, otherwise a checked, read-only connection."""
    path = _db_path(project_dir, env)
    if not path.exists():
        if _is_linklike(path):
            raise StorageError(f"Invalid environment state {env!r}: database path is a dangling symbolic link")
        yield None
        return
    connection = None
    try:
        try:
            if _wal_mode(path):
                raise StorageError(f"Invalid environment state {env!r}: WAL journal mode is unsupported for read-only inspection")
            connection = sqlite3.connect(_sqlite_uri(path), uri=True, timeout=10)
            # One read transaction for the whole inspection: the ledger and prompts must come from the same snapshot,
            # or a concurrent upgrade committing between the two reads would look like drift.
            connection.execute("BEGIN")
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
    connection = None
    with _project_lock(project_dir):
        path = _db_path(project_dir, env)
        path.parent.mkdir(exist_ok=True)
        existed = path.exists()
        connection = None
        try:
            connection = sqlite3.connect(path, timeout=10)
            connection.execute("PRAGMA busy_timeout=10000")
            connection.execute("PRAGMA synchronous=FULL")
            connection.execute("PRAGMA foreign_keys=ON")
            if existed:
                tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                if not {"applied_revisions", "prompts"} <= tables:
                    raise StorageError(f"Invalid environment state {env!r}: missing required tables")
            else:
                connection.execute("""
                    CREATE TABLE IF NOT EXISTS applied_revisions (
                        seq INTEGER PRIMARY KEY AUTOINCREMENT,
                        revision TEXT UNIQUE NOT NULL,
                        checksum TEXT NOT NULL,
                        applied_at TEXT NOT NULL
                    )
                """)
                connection.execute("""
                    CREATE TABLE IF NOT EXISTS prompts (
                        name TEXT PRIMARY KEY,
                        config TEXT NOT NULL
                    )
                """)
            connection.commit()
        except BaseException:
            try:
                if connection is not None:
                    try:
                        connection.rollback()
                    finally:
                        connection.close()
            finally:
                if not existed:
                    for suffix in ("", "-wal", "-shm"):
                        Path(f"{path}{suffix}").unlink(missing_ok=True)
            raise
        assert connection is not None
    try:
        yield connection
        connection.commit()
    except BaseException:
        connection.rollback()
        raise
    finally:
        connection.close()
