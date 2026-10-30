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

These are **not** sufficient as an end-to-end production security architecture.

## Critical missing controls

1. **Secret scanning / prevention** before writing or logging revision content. Git history retains secrets even after deletion.
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
