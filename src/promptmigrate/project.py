"""The .promptmigrate/ project directory."""

from __future__ import annotations

from pathlib import Path

from .errors import InitializationError


def root_dir(project_dir: Path) -> Path:
    return Path(project_dir).resolve() / ".promptmigrate"


def require_init(project_dir: Path) -> Path:
    """Return the .promptmigrate directory, or raise InitializationError if the project is not initialized."""
    root = root_dir(project_dir)
    if not (root / "versions").is_dir() or not (root / "drafts").is_dir():
        raise InitializationError("Not initialized. Run: promptmigrate init")
    return root
