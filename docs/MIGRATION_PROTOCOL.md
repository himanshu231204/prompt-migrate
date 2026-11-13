# MIGRATION PROTOCOL — Source format and semantics

## Purpose and status

This documents the revision file protocol: the frozen v0 format (ADR-025) and protocol v1 (ADR-026). Do **not** silently introduce a breaking format or reinterpret applied checksums: any change to meaning or hashing needs a new `format_version` with its own reader.

## Configuration draft

Named file: `.promptmigrate/drafts/sql_agent.json` (name = `sql_agent`).

```json
{
  "messages": [
    {"role": "system", "content": "Generate read-only SQL. State assumptions."}
  ],
  "model": "provider/model-id",
  "parameters": {"temperature": 0.1, "max_output_tokens": 2048},
  "tools": [{"name": "database_query", "permission": "read_only"}],
  "response_schema": {
    "type": "object",
    "required": ["query", "explanation"]
  }
}
```

Validation: `messages`, when present, must be a list of objects with string `role` and `content` (extra keys allowed).
When present, `model` must be a string, `parameters` an object, `tools` a list and `response_schema` an object or `null`.
All other keys are opaque. `tools` and `response_schema` are still JSON data, not enforced tool contracts.

## Revision artifact

File: `.promptmigrate/versions/b2c3d4e5f6a7_improve_sql_agent.json`

```json
{
  "format_version": 1,
  "revision": "b2c3d4e5f6a7",
  "down_revision": "a1b2c3d4e5f6",
  "message": "Improve SQL agent safety",
  "created_at": "2026-10-29T12:00:00+00:00",
  "changes": {
    "sql_agent": {
      "before": {
        "messages": [{"role": "system", "content": "Generate SQL."}]
      },
      "after": {
        "messages": [{"role": "system", "content": "Generate read-only SQL."}]
      }
    }
  }
}
```

`revision` writes new files as v1 (see "v1 artifact"): keys sorted, two-space indentation, UTF-8, LF line endings on
every OS. Files without `format_version` are v0.

**Snapshot rules:**

- `before: null`, `after: object` => create.
- `before: object`, `after: object` => update.
- `before: object`, `after: null` => delete.
- `before: null`, `after: null`, or any `before` equal to its `after` => no-op. Never generated; an existing revision
  that contains one loads with a `LegacyRevisionWarning`.
- A revision may contain changes for multiple named configurations.
- `down_revision: null` indicates root; later revisions point to immediate predecessor.
- Existing starter revision ID is 12 lowercase hex chars; file slug is cosmetic.
- Revision content is declarative data, **not executable Python**.

## Authoritative state model

```text
Drafts (desired) ──diff vs replay source head──> new revision
Revisions (source history) ──apply──> Local environment state (SQLite)
Local environment state ──get──> Consumer (only if explicitly integrated)
```

## Read-only migration plan

`plan` resolves a requested target and previews the revision steps and config changes without writing state. The pure
`promptmigrate.plan` target resolver is shared by `plan`, `upgrade`, and `downgrade`; accepted targets and direction
rules are specified in [`CLI_SPEC.md`](CLI_SPEC.md). Planning verifies the environment using the same integrity and
drift checks as `check` before producing a preview.

## Replay and change preconditions

Let `S_i` represent the reconstructed state after revision `i`; `S_0 = {}`.

For every config name `n` in revision `i`:

```text
require same(S_(i-1)[n], changes[n].before)
S_i[n] = changes[n].after
if after == null: remove n
```

Backward step:

```text
require same(S_i[n], changes[n].after)
S_(i-1)[n] = changes[n].before
if before == null: remove n
```

`same(a, b)` means `canonical(a) == canonical(b)`, where `canonical` is
`json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))`. So `1`, `1.0` and `true` are pairwise
distinct. The same comparison is used by `diff` and by drift detection.

The executor must check all preconditions before committing any state change. The whole local migration operation uses one SQLite transaction.

## Strict parsing and compatibility tiers

Every draft and revision file is parsed strictly:

- duplicate object keys, `NaN`, `Infinity` and `-Infinity` are rejected; the error names the key or constant and the
  file. This also covers number literals that overflow to infinity, such as `1e400`: the error names the file but
  never the literal
- JSON nested too deep for the parser is rejected
- a file whose resolved path is outside `.promptmigrate/` is rejected. This also applies when `versions/` or
  `drafts/` is itself a symlink pointing outside `.promptmigrate/`: every file in it resolves outside and is
  rejected
- drafts are read as UTF-8 text, so a UTF-8 BOM is rejected; revision files are read as bytes, so a BOM is accepted
  (unchanged from the starter)

**Limits.** "Config depth" is the nesting depth of one config: a draft's root, or one `before`/`after` value. The root
object counts as 1.

| File | Max size | Max config depth | Symlink inside `.promptmigrate/` |
|---|---|---|---|
| draft | 1 MiB | 64 | rejected |
| revision being generated | 16 MiB, checked before writing | 64 per `after` | n/a |
| existing revision file | 16 MiB | 64 per `after` | accepted |

**Tiers.** Every rule is in exactly one tier.

| Tier | Rules | Drafts and new revisions | Existing revision files |
|---|---|---|---|
| A, ambiguity | invalid JSON, duplicate keys, non-finite numbers, nesting too deep to parse, symlink leaving `.promptmigrate/`, structural rules (keys, `format_version`, v1 unknown keys, ids, `messages`, graph, preconditions) | error | error |
| B, hygiene and limits | the rule ids below | error | `LegacyRevisionWarning`; loading continues |

| Tier-B rule id | Meaning |
|---|---|
| `no-op-change <name>` | a change whose `before` is the same as its `after` |
| `case-collision <A>/<a>` | after the revision, the env holds names equal case-insensitively |
| `reserved-field-type <name>.<field>` | `model`, `parameters`, `tools` or `response_schema` has the wrong type |
| `config-depth <name>` | an `after` value nested deeper than 64 |
| `revision-size` | the revision file is over 16 MiB |
| `symlink` | the revision file is a symlink resolving inside `.promptmigrate/` |

Warning text: `revision <id>: <rule> (accepted for compatibility; create a new revision to fix)`. It contains names and
rule ids, never config values.

Per-config rules are checked on `after` values only. Replay forces every `before` to equal an earlier `after`, so each
violation is reported once, at the revision that introduced it. `before` is never validated as new content: it is a
copy of the replayed head and must match it exactly. When `revision` copies a violating value into a new `before`, it
warns `revision <id>: <name> before carries <rules> from history (copied for compatibility)` and still writes the file,
because the new `after` is what fixes it.

The one deliberate tier-A break: a revision hand-edited to rely on `1 == true` now fails its precondition.

## v0 artifact (frozen)

A revision file without `format_version` is v0. Its semantics are frozen (ADR-025):

- required top-level keys: `revision`, `down_revision`, `message`, `created_at`, `changes`; any other top-level key
  is tolerated and ignored
- `revision` and a non-null `down_revision` are 12 lowercase hex characters; `message` and `created_at` are strings
- `changes` is a non-empty object of `{before, after}` snapshots, with the rules in "Revision artifact" above
- the file is read as bytes, so a UTF-8 BOM is accepted, and the BOM is part of the hashed bytes
- checksum: SHA-256 of the raw file bytes. Any byte change after apply, including line endings or whitespace, blocks
  that environment with "Migration file was modified after apply"

Known risk: before protocol v1 the generator wrote the platform's line ending, so a v0 revision created and applied on
Windows can fail `check` after Git normalises it to LF. New revisions are v1 and are not affected. For such v0 rows,
`promptmigrate restamp --env <env>` is the explicit recovery (ADR-027). It re-stamps the ledger checksum of each
applied v0 revision whose stored digest equals its current file normalised to all-LF or all-CRLF, computed only for
a UTF-8 file, and it fails closed, writing nothing, on any other mismatch, including a non-UTF-8 v0 file. The v0
checksum itself does not change, and no other command accepts a line-ending change.

## v1 artifact

A revision file whose top-level `format_version` is the JSON integer `1` is v1 (ADR-026):

- exactly the top-level keys `format_version`, `revision`, `down_revision`, `message`, `created_at`, `changes`. Any
  other key is a tier-A error: `Unknown top-level key in <file>: <keys>`
- `format_version` must be the integer `1`. `0`, `2`, `true`, `1.0`, `1e0`, `"1"`, `null` or any other value is a
  tier-A error: `Unsupported format_version in <file>`. A file without the key is v0
- every other rule is the v0 rule: ids, metadata types, the `changes` shape, tier-B warnings, BOM accepted
- checksum: `"v1:"` + SHA-256 of `protocol.canonical` of the whole parsed file (sorted keys, `,`/`:` separators, no
  ASCII escaping; the same form used for state equality). Line endings, indentation, key order, whitespace, JSON
  string escapes and a BOM do not change it. Any change to a parsed value does, and so does removing
  `format_version`, because the file then becomes v0
- generator: `revision` writes v1, UTF-8 with LF line endings on every OS; the 16 MiB size check counts those exact
  bytes
- a string containing an unpaired UTF-16 surrogate escape (for example `"\udc80"`) cannot be canonicalised and is a
  tier-A error: `Invalid string in <file>: unpaired surrogate`

## Integrity checks

`upgrade` and `downgrade` store each applied revision's checksum in the environment's `applied_revisions` ledger.
Every command that verifies an environment compares the ledger, row by row, with the checksums of the current source
files. A mismatch is `IntegrityError` "Migration file was modified after apply: <id>" (exit 4).

When a v0 row's stored digest equals the current file re-saved with LF or with CRLF, the error and exit code are the
same and the message ends `` (line endings only; run `promptmigrate restamp --env <env>` to accept)``. Nothing is
accepted until `restamp` runs (see "v0 artifact (frozen)").

| Format | Ledger value | A mismatch after apply means |
|---|---|---|
| v0 | 64 hex digits: SHA-256 of the raw file bytes | any byte changed, whitespace and line endings included |
| v1 | `v1:` + 64 hex digits: SHA-256 of the canonical parsed object | some parsed value changed |

- The two forms can never be equal, so changing a file's format after apply is always a mismatch.
- The ledger schema is the same for both; one history may mix v0 and v1 revisions.
- A PromptMigrate version without v1 support loads a v1 file as v0 (it ignores the unknown key) and stores a raw-byte
  checksum. Use one PromptMigrate version per environment: mixing them fails closed with the error above.
- This is **tamper detection relative to that environment ledger**, not cryptographic proof of author identity.
  Signatures and a transparency/audit trail need their own design.
- Preexisting revisions must remain readable after schema evolution.

## Environment names

`.promptmigrate/environments.json` declares the allowed local environments:

```json
{"environments": {"dev": {}, "staging": {}}}
```

The root object has exactly one `environments` object. Names match `[A-Za-z][A-Za-z0-9_-]{0,63}`, are unique case-insensitively, and cannot be Windows device names. Metadata values are JSON objects, limited by the existing control-file byte and nesting limits. Unknown metadata is retained when adding an environment. Case-insensitive lookup always uses the manifest's canonical spelling for the SQLite filename.

Without a manifest, the store infers `dev`, `staging` and every `states/*.sqlite3` stem matching the environment-name syntax, in memory. Stems that fail the syntax could not have been created by any release and are ignored; reserved and case-colliding stems may be real state and fail closed. Reads do not write this inferred manifest. A successful `upgrade` or `downgrade` writes it after its transaction commits and emits one adoption warning; a rejected command writes nothing. Read-only verification runs in one SQLite read transaction, so the ledger and configs come from the same snapshot. New manifest additions serialize their read-modify-replace operation.

`check`, `current`, and `get` open existing state with SQLite `mode=ro`; `env list` checks filenames only. WAL-mode databases are rejected because SQLite read-only WAL access can create sidecar files. Missing DB means the empty base state. Existing DBs must contain both `applied_revisions` and `prompts`; missing tables, corrupt files, or state symlinks are storage errors and are not repaired. `upgrade` and `downgrade` initialize only an absent DB and perform state plus ledger changes in one SQLite transaction. CLI status labels use the canonical manifest spelling. **`--env prod` means only local `prod.sqlite3`; it does not mean actual production.** Names `prod`, `production`, and `live` produce an explicit local-only warning.

## Revision-graph guarantees

For MVP: at most one root and one child per revision. No merge branches, disconnected history, cycles, or missing parent allowed. If there is no version file, `head` is the empty base state.

## Snapshot/storage limits to discuss

- Duplicated full configs increase repository size for frequent revisions.
- Very large prompts or templates may warrant separate content-addressed assets later.
- Raw string prompts and runtime-resolved user content must never be conflated.
- Never serialize secrets; use references like `secret://provider/credential` where needed. `revision` refuses secret-like values in new content (heuristic; see `SECURITY.md`).
- Client code and tool schema may need compatibility constraints recorded alongside config.

## Protocol versions

Shipped: v0 (ADR-025) and v1 (ADR-026). v1 adds only `format_version`. `artifact_sha256`, `dependencies`,
`metadata`, `compatibility` and signatures are not implemented; each needs a new format version with its own reader,
validation and migration tests.
