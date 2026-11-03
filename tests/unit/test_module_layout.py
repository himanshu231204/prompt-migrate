"""The package layout: each name lives in one concept-named module and the package facades re-export it."""
import ast
import importlib
from pathlib import Path

import pytest

# Every name the flat protocol.py and store.py modules exposed, mapped to the submodule that now defines it.
PROTOCOL_NAMES = {
    "limits": ["MAX_DRAFT_BYTES", "MAX_REVISION_BYTES", "MAX_CONFIG_DEPTH", "MAX_CONTROL_FILE_BYTES"],
    "jsonloader": ["_PREFIX", "_StrictJSONError", "_unique_pairs", "_reject_constant", "_finite_float", "load_json"],
    "equality": ["canonical", "same"],
    "rules": ["RESERVED_TYPES", "_NAME", "validate_config", "config_depth", "config_violations", "case_collisions"],
}
STORE_NAMES = {
    "environments": [
        "DEFAULT_ENVIRONMENTS", "_validate_name", "read_environments", "_infer_environments", "canonical_name",
        "display_name", "_new_file_mode", "_write_environments", "_warn_adoption", "_warn_production",
        "resolve_environment", "_resolve_declared", "adopt_environments", "add_environment", "list_environments",
    ],
    "lock": ["_project_lock"],
    "sqlite": ["_is_linklike", "_states_dir", "_sqlite_uri", "_wal_mode", "_db_path", "connect_readonly",
               "connect_write"],
}


def _pairs(package, layout):
    return [(package, sub, name) for sub, names in layout.items() for name in names]


@pytest.mark.parametrize("package, sub, name", _pairs("protocol", PROTOCOL_NAMES) + _pairs("store", STORE_NAMES))
def test_package_reexports_the_defining_submodule(package, sub, name):
    facade = importlib.import_module(f"promptmigrate.{package}")
    module = importlib.import_module(f"promptmigrate.{package}.{sub}")
    assert getattr(facade, name) is getattr(module, name)


@pytest.mark.parametrize("package", ["protocol", "store"])
def test_package_is_a_directory(package):
    assert importlib.import_module(f"promptmigrate.{package}").__path__


@pytest.mark.parametrize("name", ["root_dir", "require_init"])
def test_store_reexports_the_project_root_helpers(name):
    from promptmigrate import project, store
    assert getattr(store, name) is getattr(project, name)


# The core facade: every name core exposed before the split, mapped to the module that now defines it.
CORE_NAMES = {
    "errors": [
        "DriftError", "InitializationError", "IntegrityError", "LegacyRevisionWarning", "MigrationConflictError",
        "MigrationError", "PendingRevisionsError", "RevisionGraphError", "SchemaError", "SecretDetectedError",
        "SecretInHistoryWarning", "SecretRedactedWarning", "StaleAllowlistWarning", "StorageError", "TargetError",
    ],
    "protocol.equality": ["canonical", "same"],
    "secretscan": ["_REDACTED"],
    "project": ["ALLOWLIST_FILE", "pretty", "root_dir", "require_init", "read_drafts", "load_allowlist"],
    "revisions": ["Revision", "_LEGACY", "_hash", "load_revisions", "_apply_changes", "replay_revisions"],
    "draftdiff": ["draft_diff", "redacted_diff"],
    "apply": ["_applied", "_actual", "_verify"],
    "commands.init": ["init"],
    "commands.revision": ["revision"],
    "commands.history": ["redacted_history"],
    "commands.check": ["check", "audit_secrets"],
    "commands.upgrade": ["upgrade"],
    "commands.downgrade": ["downgrade"],
    "commands.get": ["get_config", "redacted_config"],
    "commands.env": ["env_add", "env_list"],
}
PUBLIC = sorted(name for names in CORE_NAMES.values() for name in names if not name.startswith("_"))

# Layer of each top-level module or package. A module imports only from strictly lower layers or its own package.
# core, __init__ and __main__ are re-export or entry layers and are not ranked.
LAYERS = {
    "errors": 0, "protocol": 1, "secretscan": 2, "project": 3, "revisions": 4, "store": 4,
    "draftdiff": 5, "apply": 5, "commands": 6, "cli": 7,
}
SRC = Path(importlib.import_module("promptmigrate").__file__).resolve().parent


@pytest.mark.parametrize("module, name", [(m, n) for m, names in CORE_NAMES.items() for n in names])
def test_core_reexports_the_defining_module(module, name):
    from promptmigrate import core
    assert getattr(core, name) is getattr(importlib.import_module(f"promptmigrate.{module}"), name)


def test_core_defines_nothing_itself():
    from promptmigrate import core
    tree = ast.parse(Path(core.__file__).read_text(encoding="utf-8"))
    assert all(isinstance(node, (ast.Expr, ast.ImportFrom, ast.Import)) for node in tree.body)


def test_package_all_is_the_public_facade():
    import promptmigrate
    from promptmigrate import core
    assert sorted(promptmigrate.__all__) == PUBLIC
    assert all(getattr(promptmigrate, name) is getattr(core, name) for name in PUBLIC)


def _imports(path: Path) -> set[str]:
    """Top-level promptmigrate components that one source file imports."""
    parts = path.relative_to(SRC).with_suffix("").parts
    package = parts[:-1] if parts[-1] != "__init__" else parts[:-1]
    found = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.ImportFrom) and node.level:
            base = package[: len(package) - (node.level - 1)]
            targets = [(*base, *node.module.split("."))] if node.module else [(*base, a.name) for a in node.names]
            found.update(t[0] for t in targets if t)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            names = [a.name for a in node.names] if isinstance(node, ast.Import) else [node.module or ""]
            found.update(n.split(".")[1] for n in names if n.startswith("promptmigrate."))
    return found


@pytest.mark.parametrize("path", sorted(SRC.rglob("*.py")), ids=lambda p: p.relative_to(SRC).as_posix())
def test_imports_point_down_the_layers(path):
    own = path.relative_to(SRC).parts[0].removesuffix(".py")
    if own not in LAYERS:
        return
    bad = sorted(t for t in _imports(path) if t != own and LAYERS.get(t, -1) >= LAYERS[own])
    assert bad == [], f"{own} (layer {LAYERS[own]}) imports {bad}"


def test_cli_only_parses_and_dispatches():
    source = (SRC / "cli.py").read_text(encoding="utf-8")
    assert "args.command ==" not in source
    assert "from .core" not in source
