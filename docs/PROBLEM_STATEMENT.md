# PROBLEM STATEMENT — Failure modes in production AI configuration

## Problem statement

Production AI systems are affected by configuration changes just as strongly as database schema or application-code changes. Prompt text alone can alter tool selection, output shape, policy compliance, cost, and downstream agent behavior. Yet many teams have no consistent process connecting **change history**, **environment state**, **deployment validation**, and **recovery**.

## Six representative incidents

| Scenario | Immediate failure | Why Git history alone is insufficient | Desired control |
|---|---|---|---|
| A system prompt is hotfixed via provider UI | Production diverges from repository | Git doesn't observe remote mutations | Detect remote drift (future); local drift now |
| SQL agent prompt changed, reviewer schema not updated | Parsing/validation breaks | Two prompts have independent lifecycle | Single compatible bundle/revision |
| Staging passes, production has unexpected prompt | Deployment uncertainty | Different environment active states | Query current environment + provenance |
| Prompt quality regresses after edit | Increased wrong answers/tool calls | Valid JSON is not behavioral validation | Mandatory offline eval gates (future) |
| Emergency rollback changes only one agent | Mixed version behavior | Individual mutable labels can diverge | Atomic release activation (future) |
| Two pipelines deploy simultaneously | Newer release overwritten | File history does not coordinate writers | Shared locks/CAS generation (future) |

## Before / after user story

**Before:** “I merged the prompt PR, but I do not know what production is serving. Should I manually paste the old prompt into the provider UI?”

**After (target):** “The production environment points to immutable release `sha256:…`, prepared from revision `r17`. CI evaluation artifacts are attached. I can view the planned delta and explicitly restore the previous active release reference.”

## Key distinctions

- **Source revision**: an ordered change event, reviewable in Git.
- **Environment applied revision**: what the migration engine has recorded locally or centrally.
- **Release manifest**: immutable bundle containing all compatible artifacts.
- **Active runtime release**: what applications resolve and use (requires SDK/adapter implementation).
- **Drift**: actual environment state disagrees with expected state. In v0.1 only local SQLite state can be checked.

## Risks of overpromising

1. A CLI file named `prod.sqlite3` **does not deploy** to a production AI application.
2. A prompt checksum detects changed bytes, **not** poor answer quality.
3. Reverting configuration does **not** revert already-performed external actions.
4. A single local SQLite transaction does **not** make provider HTTP API calls atomic.
5. Model names/version references alone cannot guarantee deterministic inference.

## Outcome we want

We want AI configuration to become **reviewable, reproducible, environment-aware, reversible where possible, and safe to promote**. The initial product solves the local migration/state consistency foundation. Later releases add real deployment coordination and quality evidence.
