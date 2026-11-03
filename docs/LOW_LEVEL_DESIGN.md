# LOW-LEVEL DESIGN (LLD) — Core Python migration engine

## 1. Module layout

Implemented (ADR-022). Each concept has one module; imports point down this order, and `tests/unit/test_module_layout.py`
enforces it:

```text
src/promptmigrate/
  errors.py          error and warning types                                     layer 0
  protocol/          limits, jsonloader (strict JSON), equality, rules           layer 1
  secretscan.py      heuristic secret rules, allowlist parsing, redaction        layer 2
  project.py         .promptmigrate/ layout, drafts, secret allowlist            layer 3
  revisions.py       Revision, load_revisions (parse + graph), replay            layer 4
  store/             environments (manifest, adoption), lock, sqlite (ro/rw)     layer 4
  draftdiff.py       drafts vs replayed source head, redacted diff               layer 5
  apply.py           verify ledger/rows against history; write revisions         layer 5
  commands/          one module per CLI verb: use-case function + run(args)      layer 6
  cli.py             argparse, dispatch, warning capture, error printing         layer 7
  core.py            public facade: re-exports only
```

Reserved for upcoming work: `plan.py` (PR 5, pure target resolution, used by `commands/upgrade.py` and
`commands/downgrade.py`) and `output.py` (PR 6, text/JSON rendering and exit codes). Later phases add their own
modules (evaluation gates, release activation, provider adapters) instead of growing existing ones.

Keep the public command behavior stable during refactor. Refactor in tested increments rather than recreating implementation from scratch.

## 2. Core types

```python
@dataclass(frozen=True)
class Revision:
    revision: str                # 12 lowercase hex chars in starter
    down_revision: str | None   # None means base
    message: str
    created_at: str              # ISO-8601 string
    changes: dict[str, Change]  # name -> before/after config
    checksum: str                # SHA-256 of on-disk raw revision bytes (starter)
    path: Path

@dataclass(frozen=True)
class Change:
    before: dict | None         # None = absent
    after: dict | None          # None = absent
```

Note: `Change` is a proposed typed wrapper; the current starter uses nested dictionaries. Similarly `Plan`, `EnvironmentState`, and `ConfigBundle` are future abstractions.

## 3. Filesystem contract

```text
project/
  .promptmigrate/
    drafts/
      assistant.json
      sql_agent.json
    versions/
      <12hex>_message_slug.json
    states/
      dev.sqlite3
      staging.sqlite3
    .gitignore    # /states/
```

Git should track drafts and versions, not local `states/`. No current central `prod` deployment functionality exists.

## 4. Current storage schema

```sql
CREATE TABLE applied_revisions (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    revision TEXT UNIQUE NOT NULL,
    checksum TEXT NOT NULL,
    applied_at TEXT NOT NULL
);
CREATE TABLE prompts (
    name TEXT PRIMARY KEY,
    config TEXT NOT NULL
);
```

`prompts.config` holds canonical JSON content; SQLite has a `prompts` table shared by all revisions *within that one environment file*. Each environment uses a different file.

## 5. Normalization and hashing

Current starter:

```python
def canonical(obj):
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))

revision_checksum = sha256(path.read_bytes()).hexdigest()
```

- JSON state comparison is **semantic object equality**.
- Applied revision checksum is over **raw revision file bytes**; even whitespace-only edits invalidate an applied revision. This is conservative but important to document.
- A future `format_version` can define canonical artifact hashing and signatures, **without silently changing validation of existing applied history**.

## 6. Revision loading and graph validation

Input: files under `versions/`.  
Output: ordered `list[Revision]` or `MigrationError`.

Validation:

1. JSON parse succeeds, required keys exist with correct types.
2. Revision ID is unique and matches `[a-f0-9]{12}`.
3. `down_revision` is null or a known ID; exactly one root if nonempty.
4. No revision has multiple children (linear-only MVP).
5. No disconnected/cyclic path; each revision is reachable from root.
6. `changes` is nonempty; each operation has exactly `before` and `after`.
7. Each prompt name is legal; each non-null config is JSON object with minimally valid messages.
8. Replay of **all** source revisions from empty state succeeds, validating each precondition.

The current starter does minimal config validation; hardening must add a strict, versioned schema (see [MIGRATION_PROTOCOL.md](MIGRATION_PROTOCOL.md)).

## 7. Draft reading and diff generation

```python
head_state = replay_revisions(load_revisions())
desired_state = read_drafts()
changes = {
    name: {"before": head_state.get(name), "after": desired_state.get(name)}
    for name in sorted(head_state.keys() | desired_state.keys())
    if head_state.get(name) != desired_state.get(name)
}
```

The diff compares Git source head to drafts, **never** a random local developer's applied SQLite state. Deleting a draft means desired deletion and must produce a deliberate reversible migration.

## 8. Migration planning (target module; current logic embedded in executor)

Input: `target`, source revisions, verified environment applied prefix.  
Output: deterministic `MigrationPlan(direction, start, target, ordered_steps, expected_changes)`.

Target resolution:

- `upgrade head` => every missing revision in source chain.
- `upgrade <revision>` => advance to that exact revision.
- `downgrade -1` => reverse most recently applied revision.
- `downgrade base` => remove all applied revisions.
- `downgrade <revision>` => reverse until that exact revision remains current.
- Unsupported targets => nonzero error.

Refuse to call `upgrade` when requested target is behind the current applied revision; refuse `downgrade` toward a target ahead of current.

## 9. Environment verification

```python
applied = SELECT revision, checksum FROM applied_revisions ORDER BY seq
assert applied == prefix(source_revisions, len(applied))  # IDs + checksums
expected = replay(source_revisions[:len(applied)])
actual = SELECT name, JSON(config) FROM prompts
assert expected == actual  # otherwise drift
```

This checks **local** state only. Remote drift requires provider-specific read/reconciliation later.

## 10. Transactional upgrade/downgrade

```python
with sqlite_connection as db:
    db.execute("BEGIN IMMEDIATE")
    verify_graph_applied_prefix_checksum_and_drift(db)
    for revision in ordered_plan:
        for config_name, operation in revision.changes.items():
            assert actual[config_name] == operation.before   # forward
            upsert_or_delete(operation.after)
        insert_applied_revision(revision.id, revision.checksum)
    # COMMIT on success, ROLLBACK on exception
```

Downgrade reverses revision order; asserts `after` and restores `before`. The ledger is updated in the same SQLite transaction. Make no HTTP calls or eval calls inside this transaction.

## 11. Error taxonomy (target)

| Error | Example | Behavior |
|---|---|---|
| InitializationError | workspace missing | fail; suggest `init` |
| SchemaError | wrong message content type | fail before state write |
| RevisionGraphError | missing parent/branch | fail closed |
| MigrationConflictError | before snapshot mismatch | fail closed |
| DriftError | actual config differs | fail closed, identify names |
| IntegrityError | applied file checksum changed | fail closed |
| TargetError | unknown revision/invalid direction | fail closed |
| StorageError | SQLite busy/corrupt | preserve transaction guarantees |

Current starter raises a single `MigrationError` in most domain cases; more granular types are a *proposed* API improvement.

## 12. Determinism and idempotence

- `upgrade head` when already current is a no-op.
- `downgrade -1` at base is a no-op in the starter.
- Every revision must apply only at its declared expected before state.
- Local environment files are independent.
- Replaying the revision chain should reconstruct exactly the state expected at a revision.
- Reapplying after a failed transaction should work without partial effects.

## 13. Common edge cases

- First root revision and empty history.
- No-op draft diff.
- Add and delete configurations in same revision.
- Unicode and escaped content in prompts.
- Unexpected keys in JSON config (strict schema pending).
- Whitespace-only tampering of applied migration file.
- Duplicate IDs, missing roots, multiple roots, branching, cycles.
- SQLite busy/transaction conflicts; process interrupted after write but before commit.
- Malformed/corrupted SQLite, missing migration source history.
- Multi-developer merge conflicts and concurrent revision generation (no automatic merge in MVP).
- Symlink/path traversal and oversized JSON files (hardening pending).

## 14. Public interfaces (target)

```python
class RevisionRepository(Protocol):
    def load_ordered(self) -> list[Revision]: ...
    def replay(self, until: str | None = None) -> dict: ...

class EnvironmentStore(Protocol):
    def verify(self, revisions: list[Revision]) -> EnvironmentState: ...
    def apply(self, plan: MigrationPlan) -> None: ...
    def read(self, name: str) -> dict: ...
```

These are design sketches, not implemented public APIs. Keep internals dependency-light; interfaces should emerge after behavior is tested.

## 15. Production extension boundary

Do **not** reuse local `upgrade` to naïvely call several remote providers in sequence while claiming atomicity. Implement a separate release-controller abstraction with immutable manifests, provider preparation, and one activation pointer. See [EVALUATION_AND_RELEASES.md](EVALUATION_AND_RELEASES.md).
