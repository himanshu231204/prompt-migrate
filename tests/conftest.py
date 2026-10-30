"""Shared pytest fixtures."""
import pytest

from promptmigrate.core import init


@pytest.fixture
def project(tmp_path):
    """A freshly initialized PromptMigrate project (contains drafts/assistant.json, no revisions)."""
    init(tmp_path)
    return tmp_path
