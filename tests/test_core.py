"""Integration tests for the deterministic, local SQLite migration engine."""

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from promptmigrate.core import (
    MigrationError, check, downgrade, draft_diff, get_config, init,
    load_revisions, revision, upgrade,
)


class PromptMigrateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        init(self.base)
        self.file = self.base / ".promptmigrate" / "drafts" / "assistant.json"

    def write(self, *, content="Version 2"):
        doc = json.loads(self.file.read_text(encoding="utf-8"))
        doc["messages"][0]["content"] = content
        self.file.write_text(json.dumps(doc), encoding="utf-8")

    def test_revision_upgrade_downgrade_separate_environments(self):
        first = revision(self.base, "initial")
        self.assertIsNone(first.down_revision)
        self.assertEqual(len(draft_diff(self.base)), 0)
        self.assertEqual(check(self.base, "staging"), (0, 1))
        self.assertEqual(upgrade(self.base, "dev"), [first.revision])
        self.assertEqual(get_config(self.base, "dev", "assistant")["messages"][0]["content"],
                         "You are a helpful AI assistant.")
        self.write()
        second = revision(self.base, "better system prompt")
        self.assertEqual(second.down_revision, first.revision)
        self.assertEqual(upgrade(self.base, "dev"), [second.revision])
        self.assertEqual(get_config(self.base, "dev", "assistant")["messages"][0]["content"], "Version 2")
        self.assertEqual(downgrade(self.base, "dev", "-1"), [second.revision])
        self.assertEqual(get_config(self.base, "dev", "assistant")["messages"][0]["content"],
                         "You are a helpful AI assistant.")
        self.assertEqual(check(self.base, "dev"), (1, 2))
        self.assertEqual(check(self.base, "staging"), (0, 2))
        with self.assertRaises(MigrationError):
            check(self.base, "dev", require_head=True)
        self.assertEqual(downgrade(self.base, "dev", "base"), [first.revision])
        self.assertEqual(check(self.base, "dev"), (0, 2))

    def test_migration_tampering_detected(self):
        first = revision(self.base, "initial")
        upgrade(self.base, "dev")
        contents = json.loads(first.path.read_text(encoding="utf-8"))
        contents["message"] = "changed after apply"
        first.path.write_text(json.dumps(contents), encoding="utf-8")
        with self.assertRaisesRegex(MigrationError, "modified after apply"):
            check(self.base, "dev")

    def test_state_drift_detected(self):
        revision(self.base, "initial")
        upgrade(self.base, "dev")
        db_file = self.base / ".promptmigrate" / "states" / "dev.sqlite3"
        with sqlite3.connect(db_file) as conn:
            conn.execute("UPDATE prompts SET config=? WHERE name='assistant'", ('{}',))
        with self.assertRaisesRegex(MigrationError, "drift detected"):
            check(self.base, "dev")
        with self.assertRaises(MigrationError):
            upgrade(self.base, "dev")

    def test_revision_precondition_validation(self):
        revision(self.base, "initial")
        self.write()
        latest = revision(self.base, "update")
        doc = json.loads(latest.path.read_text(encoding="utf-8"))
        doc["changes"]["assistant"]["before"] = {"unexpected": "prior"}
        latest.path.write_text(json.dumps(doc), encoding="utf-8")
        with self.assertRaisesRegex(MigrationError, "unexpected current value"):
            load_revisions(self.base)

    def test_prompt_deletion_and_rollback(self):
        revision(self.base, "initial")
        upgrade(self.base, "dev")
        self.file.unlink()
        revision(self.base, "delete assistant")
        upgrade(self.base, "dev")
        with self.assertRaisesRegex(MigrationError, "No prompt named"):
            get_config(self.base, "dev", "assistant")
        downgrade(self.base, "dev", "-1")
        self.assertIn("messages", get_config(self.base, "dev", "assistant"))

    def test_invalid_env_and_no_changes(self):
        revision(self.base, "initial")
        with self.assertRaisesRegex(MigrationError, "No changes"):
            revision(self.base, "repeat")
        with self.assertRaisesRegex(MigrationError, "Environment"):
            check(self.base, "../escape")

    def test_multi_prompt_revision_is_atomic(self):
        revision(self.base, "initial")
        upgrade(self.base, "dev")
        self.write(content="New wording")
        (self.base / ".promptmigrate" / "drafts" / "classifier.json").write_text(
            json.dumps({"messages": [{"role": "system", "content": "Classify."}]}), encoding="utf-8"
        )
        change = revision(self.base, "update two prompts")
        self.assertEqual(len(change.changes), 2)
        upgrade(self.base, "dev")
        self.assertEqual(get_config(self.base, "dev", "assistant")["messages"][0]["content"],
                         "New wording")
        self.assertEqual(get_config(self.base, "dev", "classifier")["messages"][0]["content"],
                         "Classify.")
        downgrade(self.base, "dev")
        with self.assertRaises(MigrationError):
            get_config(self.base, "dev", "classifier")


if __name__ == "__main__":
    unittest.main()
