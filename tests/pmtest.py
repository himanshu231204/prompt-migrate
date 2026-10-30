"""Shared helpers for the PromptMigrate test suite (imported directly by test modules)."""
import json
import shutil
from pathlib import Path

CFG = {"messages": [{"role": "system", "content": "A"}]}
FIXTURES = Path(__file__).parent / "fixtures"


def pm_dir(project: Path) -> Path:
    return project / ".promptmigrate"


def create(config=CFG) -> dict:
    """A change that creates a config."""
    return {"before": None, "after": config}


def write_revision(project, rid, parent, changes, *, filename=None, message="m") -> Path:
    """Write a revision file in the starter's v0 format, bypassing the generator."""
    item = {
        "revision": rid,
        "down_revision": parent,
        "message": message,
        "created_at": "2026-10-30T00:00:00+00:00",
        "changes": changes,
    }
    path = pm_dir(project) / "versions" / f"{filename or rid}.json"
    path.write_text(json.dumps(item, indent=2), encoding="utf-8")
    return path


def set_draft(project, name, config) -> Path:
    path = pm_dir(project) / "drafts" / f"{name}.json"
    path.write_text(json.dumps(config), encoding="utf-8")
    return path


def install_fixture(project, name) -> None:
    """Copy tests/fixtures/legacy/<name>/*.json into the project's versions/ directory."""
    sources = sorted((FIXTURES / "legacy" / name).glob("*.json"))
    assert sources, f"no fixture files for {name!r}"
    for source in sources:
        shutil.copyfile(source, pm_dir(project) / "versions" / source.name)


def tree_snapshot(root) -> dict:
    """Map every file under root to its bytes, for 'nothing changed' assertions."""
    root = Path(root)
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file()}
