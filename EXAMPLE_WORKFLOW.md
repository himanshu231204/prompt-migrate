# WORKED EXAMPLE — Multi-agent AI application

## Scenario

An AI application uses:

- `planner` — decides the steps for a data engineering task.
- `sql_agent` — produces only read-only SQL queries.
- `reviewer` — evaluates the SQL and emits a structured decision.

A developer wants to tighten SQL safety instructions and adjust reviewer output-contract compatibility. Changes should be applied/reverted together.

## Step 1 — Initialize

```bash
promptmigrate init
```

The starter creates `.promptmigrate/drafts/assistant.json`. Replace or supplement it with `planner.json`, `sql_agent.json`, and `reviewer.json`. If `assistant.json` is not needed, remove it before the initial revision.

Example `drafts/planner.json`:

```json
{
  "messages": [{"role": "system", "content": "Plan data engineering tasks in ordered steps."}],
  "model": "provider/model-id",
  "parameters": {"temperature": 0.2}
}
```

Example `drafts/sql_agent.json`:

```json
{
  "messages": [{"role": "system", "content": "Generate SQL and describe assumptions."}],
  "model": "provider/model-id",
  "tools": [{"name": "database_query", "permission": "read_only"}]
}
```

Example `drafts/reviewer.json`:

```json
{
  "messages": [{"role": "system", "content": "Review the generated SQL and return a decision."}],
  "response_schema": {"type": "object", "required": ["approved", "reason"]}
}
```

## Step 2 — Initial revision

```bash
promptmigrate revision -m "initial multi-agent configuration"
promptmigrate history
promptmigrate upgrade head --env dev
promptmigrate check --env dev --require-head
```

The CLI creates a single revision containing all named configs; the local `dev.sqlite3` records that revision as applied.

## Step 3 — Introduce a compatible change

Edit `sql_agent.json` system content to say: “Generate only read-only SELECT statements. Never create, update, delete, or alter records. Explain assumptions.”

Edit `reviewer.json` `response_schema` to include a new required field, for example `risk_level`. (Real client compatibility checks are future work.)

```bash
promptmigrate diff
promptmigrate revision -m "tighten SQL safety and reviewer contract"
promptmigrate upgrade head --env dev
```

Both config changes belong to one revision and apply within the same local SQLite transaction. This **does not automatically alter any live AI agent** until the application is explicitly integrated with the resulting applied config.

## Step 4 — Validate environment state

```bash
promptmigrate current --env dev
promptmigrate get sql_agent --env dev
promptmigrate check --env dev
promptmigrate current --env staging
```

A `staging` DB can be behind source head; `check` still succeeds if its own applied history is internally consistent. Use `--require-head` to require up-to-date migration state.

## Step 5 — Roll back the latest revision

```bash
promptmigrate downgrade -1 --env dev
promptmigrate get sql_agent --env dev
```

The previous `sql_agent` and `reviewer` snapshots are restored together; the migration ledger is updated in the same SQLite transaction. Past inference outputs or tool actions are not undone.

## Step 6 — Show drift blocking

An unauthorized/manual modification of the `prompts` SQLite table would cause:

```bash
promptmigrate check --env dev
# Error: Environment drift detected for prompts: ...
```

No automated overwrite should occur until drift is understood and resolved.

## Future real deployment scenario (not executable today)

1. CI builds a release manifest from a validated revision chain.
2. Evals compare candidate behavior to a baseline.
3. Required approvals and policies pass.
4. Assets are prepared in remote providers, then verified.
5. Shared release pointer switches once.
6. Runtime SDK pins a verified release for an agent workflow.
7. Observability records the release ID.
8. Incident rollback reactivates last known-good release.

## Practical limitation

The full snapshot approach guarantees a **config state transition**, not compatibility with all application code or external tool APIs. Add integration tests as soon as a runtime SDK exists.
