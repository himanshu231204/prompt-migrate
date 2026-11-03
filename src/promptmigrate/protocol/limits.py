"""Size and depth limits for source files and configs.

Module globals, read at call time (as `limits.NAME`) so tests can patch them here.
"""

MAX_DRAFT_BYTES = 1 << 20  # 1 MiB per draft file
MAX_REVISION_BYTES = 16 << 20  # 16 MiB per revision file
MAX_CONFIG_DEPTH = 64  # nesting depth of one config: a draft's root, or one before/after value
MAX_CONTROL_FILE_BYTES = 1 << 20  # 1 MiB for secret-allowlist.json and environments.json
