# OPEN QUESTIONS — Topics to discuss with Claude before implementation

These are **questions for review**, not permission to disregard agreed CLI-first scope.

## High priority

1. **Revision schema stability:** freeze existing starter JSON fields as `format_version = 0`, or explicitly introduce a v1 with a tested reader/migration path? **Answered:** v0 frozen as the format without `format_version` (ADR-025); v1 introduced with a tested reader and mixed-history support (ADR-026).
2. **Strong schema vs extensibility:** which config fields must be standardized and which should be provider-specific extension namespaces?
3. **Safe deletion policy:** require explicit `--allow-delete` or human confirmation for migration that removes named configurations?
4. **Source hashing:** continue raw-byte hash for all existing revisions; what precise new canonical-signature format should apply only to later revisions? **Answered:** v0 keeps the raw-byte hash; v1 files use `"v1:" + SHA-256(canonical JSON)` (ADR-026). Signatures remain open.
5. **Concurrency:** how to atomically generate revision files when two developers/pipelines are on same source head; what happens after Git merges?
6. **Strict transaction semantics:** should `upgrade head` be one transaction for entire path, or one per revision; how to surface results after failure?
7. **Local `--env prod`:** warn, rename environment model, or disallow misleading production names until real deployment exists?
8. **Runtime integration MVP bridge:** should the immediate next step after hardening be a simple `export` command and local Python resolver?
9. **Security guardrails:** what secrets/personal data checks and file size limits are safe without unreasonable false positives?
10. **Compatibility testing:** how to compare application code and output/tool schemas to a revision before allowing deployment?

## Later architecture

- Which immutable artifact store and canonical manifest serialization should be used?
- Is the release controller a CLI that talks directly to Postgres, or a small service with auth and auditing?
- How are tenants, regions, and canaries represented without breaking atomic bundle activation?
- How does runtime release pinning work during a multi-hour agent workflow?
- How are external provider changes reconciled without overwriting manual emergency edits?
- Are evaluation suites first-class artifacts with hashes and signed evidence?
- What should a safe downgrade/rollback approval policy be for critical tool-permission changes?

## Discussion output desired

Ask Claude to produce (a) prioritized issues, (b) proposed ADR updates, (c) smallest implementable Phase 1 plan, (d) test matrix, and (e) what must remain unimplemented until the later production release protocol.
