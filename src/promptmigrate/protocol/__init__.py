"""Source-file protocol: strict JSON loading, limits, canonical equality and config validation.

Names are defined in the submodules and re-exported here. Patch a limit on `protocol.limits`, not on this package.
"""

from .equality import canonical, same
from .jsonloader import _PREFIX, _StrictJSONError, _finite_float, _reject_constant, _unique_pairs, load_json
from .limits import MAX_CONFIG_DEPTH, MAX_CONTROL_FILE_BYTES, MAX_DRAFT_BYTES, MAX_REVISION_BYTES
from .rules import _NAME, RESERVED_TYPES, case_collisions, config_depth, config_violations, validate_config
