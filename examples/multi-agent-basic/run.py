"""Walk a two-agent project through the full PromptMigrate lifecycle.

    python examples/multi-agent-basic/run.py [PROJECT_DIR]

PROJECT_DIR must not exist yet; without it, a temporary directory is used and removed afterwards. This script only
reads its own drafts/ folder, and it works the same on Windows, Linux and macOS. It needs promptmigrate importable,
for example after `pip install -e .` from the repository root.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent


def pm(project: Path, *args: str) -> None:
    """Run one promptmigrate command, echo it and its output, and stop the walkthrough if it fails."""
    print(f"$ promptmigrate {' '.join(args)}", flush=True)
    result = subprocess.run([sys.executable, "-m", "promptmigrate", "--project", str(project), *args],
                            capture_output=True, text=True)
    print(result.stdout, end="", flush=True)
    print(result.stderr, end="", file=sys.stderr, flush=True)
    if result.returncode != 0:
        sys.exit(result.returncode)


def walkthrough(project: Path) -> None:
    drafts = project / ".promptmigrate" / "drafts"

    pm(project, "init")
    # Replace the starter draft with the two agents of this example.
    (drafts / "assistant.json").unlink()
    for draft in sorted((HERE / "drafts").glob("*.json")):
        shutil.copyfile(draft, drafts / draft.name)
    pm(project, "diff")
    pm(project, "revision", "-m", "add planner and researcher agents")
    pm(project, "upgrade", "--env", "dev")
    pm(project, "check", "--env", "dev")

    # Change one agent: the researcher gets a little more creative.
    researcher = drafts / "researcher.json"
    config = json.loads(researcher.read_text(encoding="utf-8"))
    config["parameters"]["temperature"] = 0.2
    researcher.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    pm(project, "diff")
    pm(project, "revision", "-m", "raise researcher temperature")
    pm(project, "upgrade", "--env", "dev")
    pm(project, "check", "--env", "dev")
    pm(project, "get", "researcher", "--env", "dev")
    pm(project, "history")

    # Roll the change back. This reverts configuration only; it does not undo anything an agent already did.
    pm(project, "downgrade", "--env", "dev")
    pm(project, "check", "--env", "dev")
    pm(project, "current", "--env", "dev")


def main(argv: list[str]) -> None:
    if len(argv) > 1:
        project = Path(argv[1])
        project.mkdir(parents=True)
        walkthrough(project)
    else:
        with tempfile.TemporaryDirectory() as tmp:
            walkthrough(Path(tmp))


if __name__ == "__main__":
    main(sys.argv)
