"""PR 9 (cycle 2): line-ending digests of v0 revisions, and the diagnosis that names `restamp` (ADR-027).

A v0 checksum stays the raw-byte SHA-256 (ADR-025). `load_revisions` also records the digests of the same bytes
re-saved with LF and with CRLF, from the bytes it already read, so a later check never re-reads the file. v1
revisions have none: their checksum already ignores line endings (ADR-026).
"""
import hashlib
import json

import pytest

from pmtest import FIXTURES, install_fixture
from promptmigrate.core import load_revisions, revision
from promptmigrate.revisions import line_ending_variants

PINS = json.loads((FIXTURES / "v0_checksums.json").read_text(encoding="utf-8"))
LF_PIN, CRLF_PIN = PINS["crlf/lf/aaaaaaaaaaaa_create.json"], PINS["crlf/crlf/aaaaaaaaaaaa_create.json"]


def sha(data):
    return hashlib.sha256(data).hexdigest()


@pytest.mark.parametrize("raw", [b"{\n}\n", b"{\r\n}\r\n"])
def test_variants_are_the_lf_and_crlf_digests(raw):
    assert line_ending_variants(raw) == {sha(b"{\n}\n"), sha(b"{\r\n}\r\n")}


def test_variants_normalise_mixed_line_endings():
    assert line_ending_variants(b"{\r\n\n}") == {sha(b"{\n\n}"), sha(b"{\r\n\r\n}")}


def test_variants_keep_the_bom():
    bom = b"\xef\xbb\xbf"
    assert line_ending_variants(bom + b"{\n}") == {sha(bom + b"{\n}"), sha(bom + b"{\r\n}")}


def test_variants_of_the_crlf_fixture_are_both_pins():
    assert line_ending_variants((FIXTURES / "crlf/crlf/aaaaaaaaaaaa_create.json").read_bytes()) == {LF_PIN, CRLF_PIN}


@pytest.mark.parametrize("case", ["lf", "crlf"])
def test_v0_revision_carries_its_line_ending_checksums(project, case):
    install_fixture(project, case, "crlf")
    [r] = load_revisions(project)
    assert r.format_version == 0
    assert r.line_ending_checksums == frozenset({LF_PIN, CRLF_PIN})


def test_v1_revision_has_no_line_ending_checksums(project):
    created = revision(project, "initial")
    assert created.format_version == 1
    assert created.line_ending_checksums == frozenset()
