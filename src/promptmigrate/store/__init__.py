"""Declared local environments and SQLite connection lifecycle.

Names are defined in the submodules and re-exported here. Patch a function on the submodule that defines it.
"""

from ..project import require_init, root_dir
from .environments import (
    DEFAULT_ENVIRONMENTS, _infer_environments, _new_file_mode, _resolve_declared, _validate_name, _warn_adoption,
    _warn_production, _write_environments, add_environment, adopt_environments, canonical_name, display_name,
    list_environments, read_environments, resolve_environment,
)
from .lock import _project_lock
from .sqlite import _db_path, _is_linklike, _sqlite_uri, _states_dir, _wal_mode, connect_readonly, connect_write
