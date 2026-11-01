# SECURITY MODEL — PromptMigrate

> Design specification. Current starter has limited security checks and is **not certified for live production deployment**.

## Assets to protect

- Revision history and integrity.
- Active environment configuration and release pointers.
- Provider API credentials / secret references.
- Review/evaluation evidence and activation audit logs.
- Names/contents of system instructions, which may be commercially sensitive.
- Runtime compatibility and tool-permission contracts.

## Adversaries / failure sources

Unintentional developer mistakes; malformed or malicious pull requests; someone editing local or remote state directly; compromised CI credentials; concurrent deployment agents; stale runtime caches; external provider failures; insecure logs.

## Current controls (starter)

- Declarative JSON only; no arbitrary migration Python execution.
- Applied raw-revision checksum comparison.
- Local actual-state vs replayed expected-state comparison.
- Basic names/type checks.
- SQLite transaction for atomic local state and ledger update.
- Simple environment name validation to restrict output path forms.
- Heuristic secret safeguard (Phase 1 cycle 1, PR 3b): `revision` refuses secret-like values in new content, and
  `diff`/`get` redact them in output. See "Secret safeguard" below for its limits.

These are **not** sufficient as an end-to-end production security architecture.

## Critical missing controls

1. **Secret scanning / prevention:** **partial (heuristic).** New revision content is scanned and output is redacted,
   but detection can miss secrets, and it does nothing for secrets already in Git history.
2. **Repository trust:** revision files can come from untrusted PRs; reviewed/signed artifacts required for production.
3. **Strict schema validation:** type restrictions, max sizes, deep nesting and ambiguous data.
4. **Filesystem hardening:** symlinks, concurrent revision writes, unsafe workspace permissions and paths.
5. **Central auth/RBAC** and separation of authors vs approvers for production release.
6. **Credential isolation:** provider credentials only in CI/secret stores; no credential plaintext in config.
7. **Audit trail:** append-only event store for publish/promote/rollback, with actor/reason.
8. **Release integrity:** content-addressed immutable manifest, verified by runtime.
9. **Replay/downgrade safeguards:** refuse incompatible or unexpected state; production rollback approval policy.
10. **Supply chain:** pin dependencies, signed distribution/CI provenance where feasible.

## Prompt/agent-specific hazards

- A prompt-injection vulnerability can be introduced by an otherwise syntactically valid prompt.
- A new tool permission may increase impact of a compromised agent.
- A changed output schema can break downstream parsers.
- A changed model identifier may alter accuracy, latency, pricing, and safety behavior.
- Reverting instructions cannot undo already-executed destructive operations.

## Secret safeguard (heuristic)

Rules apply to every string value, including prompt `content`: `openai-anthropic-key` (`sk-…`), `aws-access-key-id`,
`github-token`, `slack-token`, `private-key-pem`, `bearer-token` and `jwt`. A further rule, `secret-key-name`, flags
the value of keys named like `api_key`, `password`, `secret`, `client_secret`, `access_token`, `auth_token`, `token`
or `private_key`, unless it is empty or a `secret://` reference.

Revision commit messages are scanned too, as name `(message)`, path `/message`; allowlist a message finding with
`"name": "(message)", "path": "/message"`.

| Command | On a finding that is not allowlisted |
|---|---|
| `revision` | refuses, writes no file; a value copied into `before` from history only warns |
| `diff`, `get` | shows `<redacted:RULE>` instead of the string |
| `history` | shows `<redacted:RULE>` for a flagged message |
| `check` | warns about history findings (including messages) and stale allowlist entries; exit code unchanged |

**Limits.** Detection is pattern-based, so it misses secrets that don't look like a known token, and can flag text that
only looks like one. It does nothing for secrets already committed: those stay in Git history and must be rotated.
Object keys and config names are not scanned. Messages, warnings and errors carry names, JSON paths and rule ids,
never the values.

**Allowlist.** `.promptmigrate/secret-allowlist.json` is Git-tracked, so changes to it get code review:

```json
{"allow": [{"name": "assistant", "path": "/messages/0/content", "rule": "bearer-token",
            "fingerprint": "sha256:<64 hex>", "reason": "documentation example"}]}
```

All five keys are required and no others are allowed. `rule` must be a known rule id. An entry suppresses a finding
only when `name`, `path`, `rule` and `fingerprint` all match. The fingerprint is `sha256:` plus the hex SHA-256 of the
exact matched text in UTF-8 (for the key-name rule, the whole value). If the value changes, or an array shift moves the
path, the entry stops matching. Compute a fingerprint for an example you have deliberately approved with:

```bash
python -c "import hashlib,sys;print('sha256:'+hashlib.sha256(sys.argv[1].encode()).hexdigest())" "<value>"
```

Only allowlist values that are not secrets. Errors never print fingerprints, because a hash of a weak password can be
brute-forced.

## Policy for secrets

Do **not** commit API keys, user data, credentials, private documents, or production responses into drafts, revisions, fixtures, logs, or evaluation traces. Use references to a secret manager, with secret values resolved only at runtime by an authorized component.

## Production safety gate (future)

- Authorized/approved change origin.
- Revision and manifest signature/content hash verified.
- Mandatory eval/compatibility checks pass.
- No unresolved drift between declared and remote state.
- Prepared artifacts available and verified.
- Atomic pointer activation with concurrency control.
- Traceability from inference to immutable release ID.

## Security disclosure policy (proposal)

Before public release, add a `SECURITY.md` with supported versions and private vulnerability reporting channel chosen by maintainers. **Do not invent a security email address** before it exists.
