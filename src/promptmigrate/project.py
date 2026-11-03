"""The .promptmigrate/ project directory: layout, drafts and the reviewed secret allowlist."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from . import protocol, secretscan
from .errors import InitializationError, SchemaError

ALLOWLIST_FILE = "secret-allowlist.json"


def pretty(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, indent=2) + "\n"


def root_dir(project_dir: Path) -> Path:
    return Path(project_dir).resolve() / ".promptmigrate"


def require_init(project_dir: Path) -> Path:
    """Return the .promptmigrate directory, or raise InitializationError if the project is not initialized."""
    root = root_dir(project_dir)
    if not (root / "versions").is_dir() or not (root / "drafts").is_dir():
        raise InitializationError("Not initialized. Run: promptmigrate init")
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
