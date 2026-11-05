# AGENTS.md — AI coding agent instructions for PromptMigrate

These instructions are mandatory for every AI coding agent (Claude Code, Codex, Cursor, Copilot, Gemini or any other) and apply to every change in this repository. Every rule lives here. Tool-specific files such as `CLAUDE.md` hold only orientation (commands, architecture, status) and never add to or override these rules.

## Mission

You are helping design and eventually implement **PromptMigrate**, an open-source Alembic-inspired CLI for **AI prompt and agent configuration migrations**: safe ordered revisions, environment state tracking, reversible changes, integrity/drift checks, and eventually policy-gated immutable release activation.

**Do not redefine it as** a prompt editor, LLM workflow orchestrator, SaaS dashboard, observability tool, or a generic AI agent system.

## Repository map

- Code: `src/promptmigrate/`, split by concept (ADR-022; see Architecture below), tests: `tests/`.
- Design docs: `docs/` — start with `README.md` and `docs/HANDOFF.md`.
- Current scope: Phase 1 cycle 1 (PRs 1–6 + 3b) in `docs/ROADMAP.md`; finishing it does not finish Phase 1.
- Decision record: `docs/DECISIONS.md`; open design questions: `docs/OPEN_QUESTIONS.md`.

## Architecture

Modules under `src/promptmigrate/`, by layer (`docs/LOW_LEVEL_DESIGN.md` §1):

- `protocol/`: limits, strict JSON loading, `canonical`/`same` equality, name rules.
- `secretscan.py`: secret rules, allowlist, redaction (no I/O).
- `project.py`: workspace, drafts, allowlist. `revisions.py`: parsing, graph, replay. `draftdiff.py`: drafts vs. source head.
- `plan.py`: pure target resolution shared by `upgrade`, `downgrade` and `plan`.
- `store/`: declared environments, project lock, SQLite connections. `apply.py`: `_verify` and row+ledger writes.
- `output.py`: `Result`, text/JSON rendering, error-to-exit-code table. `commands/<verb>.py`: one verb each, `execute(args)` → `Result`.
- `cli.py` parses and dispatches; `core.py` is the re-export facade tests import.

State under `.promptmigrate/`:

1. `drafts/<name>.json`: desired config.
2. `versions/<12hex>_<slug>.json`: revisions with `changes: {name: {before, after}}` as full snapshots (`null` = absent).
3. `environments.json`: declared environments (Git tracked); legacy projects are inferred and adopted on first mutation.
4. `states/<env>.sqlite3`: `applied_revisions(seq, revision, checksum, applied_at)` and `prompts(name, config)` (gitignored). Missing = base; incomplete = error.
5. Runtime state: not implemented; `--env prod` is just a local file.

Flow:

- `load_revisions()` (nearly every command) enforces one linear chain and replays it from `{}`; each `before` must match.
- `revision()` diffs drafts against the replayed source head, never an env DB.
- `upgrade`/`downgrade`: `BEGIN IMMEDIATE` → `_verify()` (ledger is an exact (id, checksum) prefix of history and `prompts` equals `replay(prefix)`, else drift) → `_apply_changes()` re-checks preconditions → rows and ledger commit together.
- Checksums are SHA-256 of raw revision bytes. Downgrade deletes ledger rows; there is no audit log yet.

## Verified baseline (2026-11-05)

- Implemented commands: `init`, `revision`, `history`, `diff`, `current`, `upgrade`, `downgrade`, `plan` (read-only preview), `check`, `get`, `env add`, and `env list`; global `--output json` and typed exit codes are supported.
- State: per-environment local SQLite files under `.promptmigrate/states/`; revisions are declarative JSON in `.promptmigrate/versions/`.
- Test status after PR 6 on Windows 11 / Python 3.11.9: `python -m pytest -q` → `713 passed, 18 skipped, 33 warnings` (skips are this host's symlink, case-insensitive filesystem and POSIX-permission limits); the original unittest suite → `Ran 7 tests ... OK`. GitHub Actions also runs native Windows and macOS jobs for Python 3.10, 3.12, and 3.13, plus Linux Docker jobs. See `docs/TESTING_STRATEGY.md` for dated results.
- Do not claim `eval`, `export`, `promote`, `reconcile`, cloud adapters, SDK, Postgres, RBAC, signed revisions, or real production activation already work.

## Engineering process

### Discussing the project

1. Restate the goal accurately.
2. Identify architecture gaps and product differentiators.
3. Critique assumptions; list alternatives and trade-offs.
4. Propose ADRs and incremental milestones.
5. Do **not** write or change code until explicitly requested.

### Implementing

1. Inspect the repository and current tests; state the baseline.
2. Choose a small scope from `docs/IMPLEMENTATION_PLAN.md` / the active spec.
3. Follow the TDD workflow in this file.
4. Run the tests and report **actual** results — never invented ones.
5. Update specs/docs in the same PR as the behavior change.
6. Clearly separate shipped behavior from planned capabilities.

## Hard rules

- Preserve source → applied environment state distinction; fail closed on drift, corrupt history, unexpected state, or partial writes.
- Keep config/ledger updates in one local SQLite transaction; no LLM/provider calls inside it.
- No arbitrary executable revision code; JSON only.
- Never change the revision artifact format or checksum semantics without an explicit format version (cycle 1 changes none). Checksums cover raw file bytes, so any byte change to an applied revision, including whitespace or CRLF, blocks that env.
- `--env prod` is local SQLite only; never claim real production deployment.
- Keep secrets out of revisions, logs, and test fixtures. Tests that need token-shaped values build fake ones at runtime from fragments (e.g. `"sk-" + "0" * 24`). Never commit a token-shaped literal.
- No unnecessary dependencies; runtime stays stdlib-only (dev extras are allowed).
- Migration **integrity** checks (`check`) are not prompt-behavior **evaluations**; never present one as the other.
- Rollback/downgrade reverts configuration only; never claim it undoes external agent actions.
- Future production activation = immutable release manifest + atomic pointer switch; never claim distributed ACID across remote APIs.

## Code structure rules

- `core.py` is the public facade that tests import: it re-exports and defines nothing. Keep its exported names and signatures stable.
- Inside the package, call collaborators through their module (`project.read_drafts(...)`), not through imported names.
- In tests, patch the defining module, never `core` or `cli`.
- `cli.py` only parses and dispatches; each verb lives in `commands/<verb>.py` and returns an `output.Result`.

## Repository and Git rules

- `docs/superpowers/` and `graphify-out/` are local-only and gitignored. Never commit them or link to them from tracked files.
- `.gitattributes` forces LF. Fixtures that must keep exact bytes need a `-text` rule.
- Record decisions in `docs/DECISIONS.md`.
- Branches are `<type>/<short-description>` (types: feat, fix, refactor, docs, test, chore, perf, build, ci), merged locally into `main` with `--no-ff`. Don't push unless asked.
- Commits use Conventional Commits and are authored as the repository owner (repo-local git config).
- Commits and PRs carry no AI attribution: no `Co-Authored-By` trailer for an AI, no "Generated by" line.

# Testing strategy (agreed 2026-10-30)

## TDD discipline — the Iron Law

**No production code without a watched-failing test first.** Red → Green → Refactor:

1. **RED:** write a minimal test for the behavior; run it; confirm it fails for the expected reason (missing feature, not a typo). Under the per-PR red-test spike below, the PR's whole test list is written red first; then each test is turned green one at a time.
2. **GREEN:** write the minimal code to pass; rerun; confirm pass.
3. **REFACTOR:** clean up keeping the suite green; then run the **whole** suite, not just the new file — a green single file is not a green suite.
4. A test that passes immediately while written after the code proves nothing: delete the code, start over.

## Test runner and tooling

- **Runner:** `pytest` (+ `hypothesis`, `pytest-cov`).
- Dev deps go in `[project.optional-dependencies] dev`; runtime stays standard-library-only.
- The existing 7 `unittest` tests run unmodified under pytest until refactored.
- **Coverage:** measure locally with `pytest-cov`, **no percentage gate**, no invented coverage numbers in public docs.

## Test-writing flow per cycle — red-test spike per PR

At the start of each PR (1–6, including 3b), write that PR's complete set of failing/characterization tests and watch them fail for the right reasons **before** implementing. Prior PRs' tests stay green all cycle.

- Known-but-unfixed bugs are pinned as `@pytest.mark.xfail(strict=True)` with a reason naming the PR that will fix them (e.g., PR 2 pins: undeclared env reports OK → PR 4; reads create files → PR 4; `1 == True` equality → PR 3; duplicate keys/NaN accepted → PR 3).

## Suite map (per docs/TESTING_STRATEGY.md)

| Suite | Scope | Where it lands |
|---|---|---|
| A — Unit (parser, graph, diff, strict loader) | invalid JSON, duplicate keys, NaN, >1 MiB, depth > 64, two roots, missing parent, cycles, dup/case-colliding names, unicode | PRs 2–3 |
| B — State-machine / property (`hypothesis`, `max_examples=50`, core-only) | plan == apply; post-state == replay; upgrade→downgrade restores prior state; idempotent `upgrade head`; error path leaves DB unchanged; `plan` mutates no file bytes | PR 5 |
| C — SQLite integration / fault injection | connection closed after every command; `states/<env>.sqlite3` deletable post-command | PR 1 |
| C (cont.) | atomic multi-revision apply under injected faults; interrupted write rolls back; parallel `upgrade` processes | Phase 1 cycle 2 |
| D — CLI contract | exit codes, stdout/stderr, README examples as smoke tests, read commands never mutate files, JSON `result` shape snapshots | PRs 2, 4, 6 |
| E — Security and limits | secret scanner rules, `revision` blocking, `diff`/`get` redaction, allowlist; no secret values in output/logs/fixtures; symlinks (skipped where `os.symlink` is unsupported); path traversal; case-colliding names | PRs 3, 3b, 4 |
| F — Future provider tests | out of scope until Phase 3 | — |

## Gates and reporting

- **Merge gate:** the whole suite green on this Windows machine with real pasted output; Linux/macOS claims only after a CI remote exists.
- Every PR note includes the actual test command and output.
- Behavior changes update `docs/CLI_SPEC.md`, `docs/MIGRATION_PROTOCOL.md`, `docs/DECISIONS.md`, and `CHANGELOG.md` in the same PR.
- Report format for design/code reviews: **Verified / Planned / Risks–contradictions (severity) / Proposed ADR updates / Next 3 steps with test acceptance criteria.**

## Do-not list

- No wholesale rewrites without regression coverage.
- No remote writes disguised as transactional migration.
- No unrelated AI-orchestration frameworks in core.
- No runtime credentials or user data in migrations or tests.
- No claiming production readiness from a green suite alone.
