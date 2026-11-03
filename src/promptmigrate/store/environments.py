"""Declared local environments: the environments.json manifest, legacy inference and adoption, name resolution.

Callers resolve environment names before opening connections (see store.sqlite).
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import stat
import tempfile
from typing import Any
import warnings

from .. import project, protocol
from ..errors import (
    EnvironmentAdoptionWarning, EnvironmentNotDeclaredError, ProductionNameWarning, SchemaError, StorageError,
)
from . import lock, sqlite


# Environment-name syntax lives in protocol.rules, so store.sqlite can validate names without importing this module.
_NAME = protocol.rules._ENV_NAME
_validate_name = protocol.rules.validate_environment_name
DEFAULT_ENVIRONMENTS = ("dev", "staging")


def read_environments(project_dir: Path) -> tuple[dict[str, dict[str, Any]], bool]:
    """Read declarations, or infer legacy declarations without writing any files."""
    root = project.require_init(project_dir)
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
        if protocol.config_depth(metadata) > protocol.limits.MAX_CONFIG_DEPTH:
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
    stems = [p.stem for p in sqlite._states_dir(project_dir).glob("*.sqlite3") if p.is_file() and _NAME.fullmatch(p.stem)]
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
    path = project.require_init(project_dir) / "environments.json"
    text = json.dumps({"environments": environments}, ensure_ascii=False, indent=2) + "\n"
    if len(text.encode("utf-8")) > protocol.limits.MAX_CONTROL_FILE_BYTES:
        raise SchemaError(f"Invalid environments file: output exceeds the {protocol.limits.MAX_CONTROL_FILE_BYTES}-byte limit")
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
        with lock._project_lock(project_dir):
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
    with lock._project_lock(project_dir):
        environments, existed = read_environments(project_dir)
        if not existed:
            _write_environments(project_dir, environments)
            _warn_adoption()


def add_environment(project_dir: Path, name: str) -> Path:
    """Atomically declare a new name, retaining all existing metadata."""
    _validate_name(name)
    with lock._project_lock(project_dir):
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
    states = sqlite._states_dir(project_dir)
    result = []
    for name in sorted(environments, key=str.lower):
        path = states / f"{name}.sqlite3"
        if sqlite._is_linklike(path):
            raise StorageError(f"Invalid environment state {name!r}: database path is a symbolic link")
        result.append((name, path.is_file()))
    return result
