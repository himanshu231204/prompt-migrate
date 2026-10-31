"""Shared helpers for the PromptMigrate test suite (imported directly by test modules)."""
import json
import shutil
from pathlib import Path

import pytest

from promptmigrate.core import pretty

CFG = {"messages": [{"role": "system", "content": "A"}]}
FIXTURES = Path(__file__).parent / "fixtures"
LEGACY_ID = "a" * 12


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
    path.write_text(pretty(item), encoding="utf-8")
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


def tree_snapshot(root) -> dict[str, bytes]:
    """Map every file under root to its bytes, for 'nothing changed' assertions."""
    root = Path(root)
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file()}


LARGE_CONTENT_BYTES = 65536  # PR 3 patches the revision-size limit below this value for the large_revision case only


def secret_in_history(project):
    token = "sk-" + "0" * 24  # built at runtime: never commit a token-shaped literal
    write_revision(project, LEGACY_ID, None, {"assistant": create({**CFG, "note": token})})


def large_revision(project):
    big = {"messages": [{"role": "system", "content": "x" * LARGE_CONTENT_BYTES}]}
    write_revision(project, LEGACY_ID, None, {"assistant": create(big)})


def deep_config(project):
    nested = {"leaf": 1}
    for _ in range(69):  # 70 nested objects below the config root
        nested = {"n": nested}
    write_revision(project, LEGACY_ID, None, {"assistant": create({**CFG, "deep": nested})})


def symlinked_revision(project):
    shared = pm_dir(project) / "shared"
    shared.mkdir()
    link = write_revision(project, LEGACY_ID, None, {"assistant": create()})
    target = shared / link.name
    link.replace(target)
    try:
        link.symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip("creating symlinks is not permitted for this user/platform")


GENERATED = {
    "secret_in_history": secret_in_history,
    "large_revision": large_revision,
    "deep_config": deep_config,
    "symlinked_revision": symlinked_revision,
}
