# AGENTS.md — AI coding agent instructions for PromptMigrate

These rules are mandatory for every AI coding agent (Claude Code, Codex, Cursor, Copilot, Gemini or any other) and every change. All rules live here; tool-specific files such as `CLAUDE.md` hold only orientation and never add to or override them.

## Mission

**PromptMigrate** is an open-source, Alembic-inspired CLI for **AI prompt and agent configuration migrations**: safe ordered revisions, environment state tracking, reversible changes, integrity/drift checks, and eventually policy-gated immutable release activation. **Do not redefine it as** a prompt editor, LLM workflow orchestrator, SaaS dashboard, observability tool or generic AI agent system.

## Repository map

- Code: `src/promptmigrate/` (ADR-022); tests: `tests/` (suite map in `docs/TESTING_STRATEGY.md`).
- Docs: start with `README.md` and `docs/HANDOFF.md`. Scope and status: `docs/ROADMAP.md`. Decisions: `docs/DECISIONS.md`. Open questions: `docs/OPEN_QUESTIONS.md`.

## Architecture

Modules by layer (`docs/LOW_LEVEL_DESIGN.md` §1): `protocol/` (limits, strict JSON, `canonical`/`same`, name rules) → `secretscan.py` (secret rules, allowlist, redaction; no I/O) → `project.py` (workspace, drafts) → `revisions.py` (parse, graph, replay) and `store/` (environments, lock, SQLite) → `draftdiff.py`, `plan.py` (target resolution for `upgrade`/`downgrade`/`plan`), `apply.py` (`_verify`, row+ledger writes), `output.py` (`Result`, text/JSON, exit codes) → `commands/<verb>.py` → `cli.py`. `core.py` is the re-export facade.

State under `.promptmigrate/`: `drafts/<name>.json` (desired config); `versions/<12hex>_<slug>.json` (revisions, `changes: {name: {before, after}}` as full snapshots, `null` = absent); `environments.json` (declared envs, Git tracked; legacy projects adopted on first mutation); `states/<env>.sqlite3` (gitignored; `applied_revisions` ledger + `prompts`; missing = base, incomplete = error). Runtime state is not implemented.

Flow: `load_revisions()` enforces one linear chain and replays it from `{}`. `revision()` diffs drafts against the replayed source head, never an env DB. `upgrade`/`downgrade` run `BEGIN IMMEDIATE` → `_verify()` (ledger is an exact (id, checksum) prefix of history and `prompts` equals `replay(prefix)`, else drift) → `_apply_changes()` re-checks preconditions → rows and ledger commit together. Checksums: v0 files (no `format_version`) hash raw bytes; v1 files hash `"v1:" + sha256(canonical(item))` (ADR-026). Downgrade deletes ledger rows; there is no audit log yet.

## Verified baseline (2026-11-13)

- Shipped: `init`, `revision`, `history`, `diff`, `current`, `upgrade`, `downgrade`, `plan`, `check`, `get`, `env add`, `env list`; `--output json`; exit codes 0–5.
- Windows 11 / Python 3.11.9: `python -m pytest -q` → `802 passed, 18 skipped, 33 warnings` (host symlink, case-insensitivity and POSIX-permission skips); unittest → `Ran 7 tests ... OK`. CI: Linux Docker plus native Windows and macOS, Python 3.10/3.12/3.13.
- Not shipped (never claim otherwise): `eval`, `export`, `promote`, `reconcile`, cloud adapters, SDK, Postgres, RBAC, signed revisions, real production activation.

## Process

- **Discussing:** restate the goal, find architecture gaps and differentiators, critique assumptions with alternatives and trade-offs, propose ADRs and milestones. Change no code until asked.
- **Implementing:** inspect the repo and state the test baseline; pick a small scope from `docs/IMPLEMENTATION_PLAN.md` or the active spec; follow TDD below; report **actual** test results only; keep shipped and planned behavior clearly separate.
- **Reviews** use: **Verified / Planned / Risks–contradictions (severity) / Proposed ADR updates / Next 3 steps with test acceptance criteria.**

## Hard rules

- Keep source history and applied env state distinct; fail closed on drift, corrupt history, unexpected state or partial writes.
- Config and ledger change in one local SQLite transaction, with no LLM/provider calls inside it. No remote writes disguised as transactional migration.
- Revisions are JSON only; no executable revision code.
- Never change the revision format or checksum semantics without an explicit format version. Any byte change to an applied revision (including whitespace or CRLF) blocks that env.
- `--env prod` is a local SQLite file; never claim real production deployment or production readiness from a green suite.
- No secrets, credentials or user data in revisions, logs or fixtures. Tests build token-shaped values at runtime from fragments (`"sk-" + "0" * 24`); never commit a token-shaped literal.
- Runtime stays stdlib-only; dev deps go in `[project.optional-dependencies] dev`. No AI-orchestration frameworks in core.
- `check` is an integrity check, not a prompt-behavior evaluation. Downgrade reverts configuration only, not external agent actions. Future activation = immutable release manifest + atomic pointer switch; never claim distributed ACID across remote APIs.
- No wholesale rewrites without regression coverage.

## Code structure

- `core.py` re-exports and defines nothing; keep its exported names and signatures stable.
- Call collaborators through their module (`project.read_drafts(...)`); in tests, patch the defining module, never `core` or `cli`.
- `cli.py` only parses and dispatches; each verb lives in `commands/<verb>.py` and returns an `output.Result`.

## Testing

- **Iron Law:** no production code without a watched-failing test. RED: write a minimal test and see it fail for the expected reason. GREEN: minimal code to pass. REFACTOR: keep it green, then run the **whole** suite. A test written after the code that passes at once proves nothing: delete the code and restart.
- Each PR starts with its full list of failing/characterization tests; earlier PRs' tests stay green. Known unfixed bugs are `@pytest.mark.xfail(strict=True)` with a reason naming the fixing PR.
- Tools: `pytest`, `hypothesis`, `pytest-cov`. The original 7 `unittest` tests in `tests/test_core.py` stay runnable unmodified. Coverage is measured locally with no percentage gate and never quoted as invented numbers.
- **Merge gate:** the whole suite green on this Windows machine with real pasted output. Linux/macOS claims need a passing CI run. Every PR note includes the test command and its output.

## Before every commit

- `CHANGELOG.md`: add an entry under **Unreleased**.
- `docs/ROADMAP.md`: tick finished items and update the status lines and "First next step".
- Behavior changes also update `docs/CLI_SPEC.md`, `docs/MIGRATION_PROTOCOL.md` and `docs/DECISIONS.md` in the same PR.

## Git

- `docs/superpowers/` and `graphify-out/` are local-only; never commit or link to them.
- `.gitattributes` forces LF; byte-exact fixtures need a `-text` rule.
- Branches: `<type>/<short-description>` (feat, fix, refactor, docs, test, chore, perf, build, ci), merged locally into `main` with `--no-ff`. Don't push unless asked.
- Conventional Commits, authored as the repository owner (repo-local git config). No AI attribution in commits or PRs: no AI `Co-Authored-By`, no "Generated by".
