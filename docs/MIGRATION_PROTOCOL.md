# MIGRATION PROTOCOL — Source format and semantics

## Purpose and status

This is the proposed **v0.x file protocol**. It documents today's starter file shape and explicitly calls out possible future protocol upgrades. Do **not** silently introduce a breaking format or reinterpret applied checksums.

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
| A, ambiguity | invalid JSON, duplicate keys, non-finite numbers, nesting too deep to parse, symlink leaving `.promptmigrate/`, structural rules (keys, ids, `messages`, graph, preconditions) | error | error |
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

## Integrity checks

The current implementation stores `SHA-256(raw revision file bytes)` in the `applied_revisions` ledger. A later change to the file — including whitespace-only modification — will be rejected for environments where that revision was applied.

- This is **tamper detection relative to that environment ledger**, not cryptographic proof of author identity.
- A future `format_version` field, canonical artifact hashing, manifest signatures, and transparency/audit trail need an explicit migration/compatibility design.
- Preexisting revisions must remain readable after schema evolution.

## Environment names

`.promptmigrate/environments.json` declares the allowed local environments:

```json
{"environments": {"dev": {}, "staging": {}}}
```

The root object has exactly one `environments` object. Names match `[A-Za-z][A-Za-z0-9_-]{0,63}`, are unique case-insensitively, and cannot be Windows device names. Metadata values are JSON objects, limited by the existing control-file byte and nesting limits. Unknown metadata is retained when adding an environment. Case-insensitive lookup always uses the manifest's canonical spelling for the SQLite filename.

Without a manifest, the store infers declarations from valid `states/*.sqlite3` stems in memory; if none exist, it infers `dev` and `staging`. Reads do not write this inferred manifest. The first successful mutating operation atomically writes it and emits one adoption warning. Invalid/colliding legacy stems fail closed. New manifest additions serialize their read-modify-replace operation.

`check`, `current`, and `get` open existing state with SQLite `mode=ro`; `env list` checks filenames only. Missing DB means the empty base state. Existing DBs must contain both `applied_revisions` and `prompts`; missing tables, corrupt files, or state symlinks are storage errors and are not repaired. `upgrade` and `downgrade` initialize only an absent DB and perform state plus ledger changes in one SQLite transaction. **`--env prod` means only local `prod.sqlite3`; it does not mean actual production.** Names `prod`, `production`, and `live` produce an explicit local-only warning.

## Revision-graph guarantees

For MVP: at most one root and one child per revision. No merge branches, disconnected history, cycles, or missing parent allowed. If there is no version file, `head` is the empty base state.

## Snapshot/storage limits to discuss

- Duplicated full configs increase repository size for frequent revisions.
- Very large prompts or templates may warrant separate content-addressed assets later.
- Raw string prompts and runtime-resolved user content must never be conflated.
- Never serialize secrets; use references like `secret://provider/credential` where needed. `revision` refuses secret-like values in new content (heuristic; see `SECURITY.md`).
- Client code and tool schema may need compatibility constraints recorded alongside config.

## Future `format_version` proposal (not implemented)

Potential fields: `format_version: 1`, `artifact_sha256`, `dependencies`, `metadata`, and `compatibility`. Define canonical serialization bytes, validation, and migration rules before shipping a public stable protocol. Do not add them experimentally without migration tests.
