# Example: two agents, one migration history

A planner agent and a researcher agent, each one JSON config in `drafts/`. `run.py` takes them through the whole
lifecycle in a fresh project:

1. `init`, then replace the starter draft with `planner.json` and `researcher.json`.
2. `diff` → `revision` → `upgrade --env dev` → `check`: both agents are created in one revision.
3. Raise the researcher's temperature from 0 to 0.2, then `diff` → `revision` → `upgrade` → `check` → `get researcher`.
4. `downgrade` → `check` → `current`: dev is back at the first revision.

```bash
python -m pip install -e .                  # from the repository root
python examples/multi-agent-basic/run.py    # uses a temporary project, removed afterwards
python examples/multi-agent-basic/run.py ./demo-project   # or keep the project to inspect it
```

The script runs the real CLI (`python -m promptmigrate`) and prints every command with its output. It stops with
that command's exit code if one fails. It never writes inside this folder.

Things to notice:

- Both agents change in one revision and one SQLite transaction; there is no state where only one is applied.
- `dev` is local SQLite state under `.promptmigrate/states/`. Nothing is deployed anywhere.
- `downgrade` reverts configuration only. It cannot undo anything an agent already did with the old configuration.
- `model` is the placeholder `provider/model-id`; PromptMigrate never calls a model.

`tests/contract/test_examples.py` runs this script on every test run.
