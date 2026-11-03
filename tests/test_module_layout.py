"""The package layout: each name lives in one concept-named module and the package facades re-export it."""
import importlib

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
