"""PR 7 (cycle 2): v0 revision semantics are frozen (ADR-025).

Characterization only: these pass on today's code. A file without `format_version` is v0, and its checksum is the
SHA-256 of its raw bytes. The pins below make any later change to v0 meaning or hashing fail here first. The fixtures
are byte-exact (`-text` in .gitattributes); regenerate them only by deliberate decision, never to make a test pass.
"""
import hashlib
import json

import pytest

from pmtest import FIXTURES, install_fixture, pm_dir, pm_warnings
from promptmigrate.core import SchemaError, check, downgrade, get_config, load_revisions, upgrade

PINS = json.loads((FIXTURES / "v0_checksums.json").read_text(encoding="utf-8"))
CASES = [("v0_frozen", "basic"), ("v0_frozen", "extra_key"), ("v0_frozen", "bom"), ("crlf", "lf"), ("crlf", "crlf")]
BOM = b"\xef\xbb\xbf"


def _pins_for(group, case):
    prefix = f"{group}/{case}/"
    return {key[len(prefix):]: digest for key, digest in PINS.items() if key.startswith(prefix)}


def test_every_fixture_file_is_pinned():
    on_disk = {p.relative_to(FIXTURES).as_posix()
               for group in ("v0_frozen", "crlf") for p in (FIXTURES / group).rglob("*.json")}
    assert on_disk == set(PINS)


@pytest.mark.parametrize("rel", sorted(PINS))
def test_fixture_bytes_match_pin(rel):
    assert hashlib.sha256((FIXTURES / rel).read_bytes()).hexdigest() == PINS[rel]


@pytest.mark.parametrize("group,case", CASES)
def test_v0_checksum_is_sha256_of_raw_bytes(project, group, case):
    install_fixture(project, case, group)
    revisions, warned = pm_warnings(load_revisions, project)
    assert warned == []
    assert {r.path.name: r.checksum for r in revisions} == _pins_for(group, case)


@pytest.mark.parametrize("group,case", CASES)
def test_v0_lifecycle(project, group, case):
    install_fixture(project, case, group)
    total = len(load_revisions(project))
    assert upgrade(project, "dev")
    assert check(project, "dev", require_head=True) == (total, total)
    assert get_config(project, "dev", "assistant")["messages"][0]["role"] == "system"
    assert len(downgrade(project, "dev", "base")) == total
    assert check(project, "dev") == (0, total)


def test_basic_history_replays_to_last_after(project):
    install_fixture(project, "basic", "v0_frozen")
    upgrade(project, "dev")
    assert get_config(project, "dev", "assistant") == {
        "messages": [{"role": "system", "content": "Answer briefly and cite sources."}]
    }


def test_extra_top_level_key_is_tolerated_and_ignored(project):
    install_fixture(project, "extra_key", "v0_frozen")
    raw = json.loads((FIXTURES / "v0_frozen/extra_key/aaaaaaaaaaaa_extra_key.json").read_bytes())
    assert raw["author"] == "fixture"
    upgrade(project, "dev")
    assert get_config(project, "dev", "assistant") == {"messages": [{"role": "system", "content": "Answer briefly."}]}


def test_bom_revision_is_accepted_and_hashed_with_its_bom(project):
    data = (FIXTURES / "v0_frozen/bom/aaaaaaaaaaaa_bom.json").read_bytes()
    assert data.startswith(BOM)
    install_fixture(project, "bom", "v0_frozen")
    [revision] = load_revisions(project)
    assert revision.checksum == hashlib.sha256(data).hexdigest()
    assert revision.checksum != hashlib.sha256(data[len(BOM):]).hexdigest()


@pytest.mark.parametrize("key", ["revision", "down_revision", "message", "created_at", "changes"])
def test_each_required_key_is_required(project, key):
    item = json.loads((FIXTURES / "v0_frozen/basic/aaaaaaaaaaaa_create.json").read_bytes())
    del item[key]
    (pm_dir(project) / "versions" / "aaaaaaaaaaaa_create.json").write_text(json.dumps(item), encoding="utf-8")
    with pytest.raises(SchemaError, match="Invalid migration format: aaaaaaaaaaaa_create.json"):
        load_revisions(project)
