"""Shared helpers for the PromptMigrate test suite (imported directly by test modules)."""
import json
import shutil
import warnings
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


def install_fixture(project, name, group="legacy") -> None:
    """Copy tests/fixtures/<group>/<name>/*.json into the project's versions/ directory."""
    sources = sorted((FIXTURES / group / name).glob("*.json"))
    assert sources, f"no fixture files for {group}/{name!r}"
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


def symlink_or_skip(link: Path, target: Path) -> None:
    try:
        link.symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip("creating symlinks is not permitted for this user/platform")


def sized_draft(project, size, name="assistant") -> Path:
    """Write a valid draft whose file is exactly `size` bytes."""
    skeleton = '{"messages": [{"role": "system", "content": ""}]}'
    padding = size - len(skeleton)
    assert padding >= 0, size
    path = pm_dir(project) / "drafts" / f"{name}.json"
    path.write_bytes(skeleton.replace('""', '"' + "x" * padding + '"').encode("utf-8"))
    assert path.stat().st_size == size
    return path


def nested_config(depth) -> dict:
    """A config whose nesting depth is exactly `depth` (the root object counts as 1)."""
    config: dict = {}
    for _ in range(depth - 1):
        config = {"n": config}
    return config


LEGACY_SUFFIX = " (accepted for compatibility; create a new revision to fix)"

LEGACY_WARNINGS = {
    "case_collision": [f"revision {LEGACY_ID}: case-collision Assistant/assistant"],
    "deep_config": [f"revision {LEGACY_ID}: config-depth assistant"],
    "large_revision": [f"revision {LEGACY_ID}: revision-size"],
    "noop_equal": [f"revision {'b' * 12}: no-op-change assistant"],
    "noop_null": [f"revision {LEGACY_ID}: no-op-change ghost"],
    "reserved_types": [
        f"revision {LEGACY_ID}: reserved-field-type assistant.model",
        f"revision {LEGACY_ID}: reserved-field-type assistant.tools",
    ],
    "secret_in_history": [],
    "symlinked_revision": [f"revision {LEGACY_ID}: symlink"],
}
"""LegacyRevisionWarning messages (without LEGACY_SUFFIX) that loading each legacy fixture emits, in order."""

LEGACY_NAMES = sorted(LEGACY_WARNINGS)


def install_legacy(project, monkeypatch, name) -> None:
    """Install one legacy fixture. For large_revision only, patch the revision-size limit below its size."""
    if name == "large_revision":
        from promptmigrate import protocol
        # Between deep_config (~12 KB) and large_revision (~66 KB), so only large_revision is over the limit.
        monkeypatch.setattr(protocol, "MAX_REVISION_BYTES", 32768)
    if name in GENERATED:
        GENERATED[name](project)
    else:
        install_fixture(project, name)


def pm_warnings(fn, *args):
    """Call fn(*args); return (result, messages of the PromptMigrateWarnings it emitted, in order)."""
    from promptmigrate.errors import PromptMigrateWarning
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        result = fn(*args)
    return result, [str(w.message) for w in caught if issubclass(w.category, PromptMigrateWarning)]
