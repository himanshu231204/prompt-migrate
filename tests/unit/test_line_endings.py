"""PR 9 (cycle 2): line-ending digests of v0 revisions, and the diagnosis that names `restamp` (ADR-027).

A v0 checksum stays the raw-byte SHA-256 (ADR-025). `load_revisions` also records the digests of the same bytes
re-saved with LF and with CRLF, from the bytes it already read, so a later check never re-reads the file. v1
revisions have none: their checksum already ignores line endings (ADR-026).
"""
import hashlib
import json

import pytest

from pmtest import CFG, FIXTURES, install_fixture, manifest, pm_dir, run_cli, swap_line_endings
from promptmigrate import apply, store
from promptmigrate.core import check, load_revisions, revision, upgrade
from promptmigrate.errors import IntegrityError
from promptmigrate.revisions import line_ending_variants

PINS = json.loads((FIXTURES / "v0_checksums.json").read_text(encoding="utf-8"))
LF_PIN, CRLF_PIN = PINS["crlf/lf/aaaaaaaaaaaa_create.json"], PINS["crlf/crlf/aaaaaaaaaaaa_create.json"]

TAMPER = "Migration file was modified after apply: aaaaaaaaaaaa"
HINT = TAMPER + " (line endings only; run `promptmigrate restamp --env {env}` to accept)"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def target(project):
    return pm_dir(project) / "versions" / "aaaaaaaaaaaa_create.json"


def applied_then_swapped(project, applied="crlf"):
    install_fixture(project, applied, "crlf")
    upgrade(project, "dev")
    swap_line_endings(target(project))


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


def _v0_item(message="m"):
    return {
        "revision": "a" * 12,
        "down_revision": None,
        "message": message,
        "created_at": "2026-10-30T00:00:00+00:00",
        "changes": {"assistant": {"before": None, "after": CFG}},
    }


def test_utf16_v0_revision_has_no_line_ending_checksums(project):
    """A v0 file `json.loads` parses as UTF-16BE (no BOM) is not UTF-8, so no CR/LF variants are computed (Finding 1)."""
    raw = json.dumps(_v0_item(), ensure_ascii=False, sort_keys=True).encode("utf-16-be")
    target(project).write_bytes(raw)
    [r] = load_revisions(project)
    assert r.format_version == 0
    assert r.line_ending_checksums == frozenset()


def test_utf16_value_change_is_not_mistaken_for_line_endings(project):
    """Reviewer's reproduction: a UTF-16BE v0 file whose message changed can hash-collide with the raw-byte LF
    variant of a byte-level CR/LF swap, because U+0D0A encodes as the same two bytes as CR LF. `check` must still
    report the plain tamper message, with no line-ending hint, because the file never decodes as UTF-8."""
    applied_item = _v0_item("ਊ")
    applied_raw = json.dumps(applied_item, ensure_ascii=False, sort_keys=True).encode("utf-16-be")
    target(project).write_bytes(applied_raw)
    upgrade(project, "dev")

    disk_item = {**applied_item, "message": "ഊഊ"}
    disk_raw = json.dumps(disk_item, ensure_ascii=False, sort_keys=True).encode("utf-16-be")
    # Confirm the collision is genuine before relying on it: the LF-variant digest of the new bytes equals the
    # applied digest, purely from byte-level CR/LF substitution, with no decoding involved.
    lf_variant = disk_raw.replace(b"\r\n", b"\n")
    assert sha(lf_variant) == sha(applied_raw)
    assert disk_raw != applied_raw

    target(project).write_bytes(disk_raw)
    with pytest.raises(IntegrityError) as caught:
        check(project, "dev")
    assert str(caught.value) == TAMPER


# --- Task 2: the diagnosis in the IntegrityError message ----------------------------------------

@pytest.mark.parametrize("applied", ["crlf", "lf"])
def test_line_ending_only_change_names_restamp(project, applied):
    applied_then_swapped(project, applied)
    with pytest.raises(IntegrityError) as caught:
        check(project, "dev")
    assert str(caught.value) == HINT.format(env="dev")


def test_hint_names_the_canonical_env_spelling(project):
    manifest(project, {"QA": {}})
    install_fixture(project, "crlf", "crlf")
    upgrade(project, "qa")
    swap_line_endings(target(project))
    with pytest.raises(IntegrityError) as caught:
        check(project, "qa")
    assert str(caught.value) == HINT.format(env="QA")


def test_value_edit_with_line_ending_change_has_no_hint(project):
    install_fixture(project, "crlf", "crlf")
    upgrade(project, "dev")
    lf = (FIXTURES / "crlf/lf/aaaaaaaaaaaa_create.json").read_bytes()
    target(project).write_bytes(lf.replace(b"Answer briefly.", b"Answer at length."))
    with pytest.raises(IntegrityError) as caught:
        check(project, "dev")
    assert str(caught.value) == TAMPER


def test_v1_ledger_row_is_never_diagnosed_as_line_endings(project):
    """A v1 file has no line-ending digests, even when its ledger row holds one (e.g. written by a pre-v1 tool)."""
    created = revision(project, "initial")
    upgrade(project, "dev")
    crlf_digest = sha(created.path.read_bytes().replace(b"\n", b"\r\n"))
    with store.connect_write(project, "dev") as db:
        db.execute("UPDATE applied_revisions SET checksum=?", (crlf_digest,))
    with pytest.raises(IntegrityError) as caught:
        check(project, "dev")
    assert str(caught.value) == f"Migration file was modified after apply: {created.revision}"


def test_verify_uses_the_bytes_already_loaded(project):
    """Swapping the file after load does not change the verdict: _verify never re-reads it."""
    install_fixture(project, "crlf", "crlf")
    upgrade(project, "dev")
    loaded = load_revisions(project)
    swap_line_endings(target(project))
    with store.connect_readonly(project, "dev") as db:
        assert apply._verify(db, loaded, "dev") == 1


def test_verify_without_env_uses_a_placeholder(project):
    applied_then_swapped(project)
    with store.connect_readonly(project, "dev") as db, pytest.raises(IntegrityError) as caught:
        apply._verify(db, load_revisions(project))
    assert str(caught.value) == HINT.format(env="<env>")


@pytest.mark.parametrize("argv", [
    ["check", "--env", "dev"], ["current", "--env", "dev"], ["get", "assistant", "--env", "dev"],
    ["plan", "--env", "dev"], ["upgrade", "--env", "dev"], ["downgrade", "--env", "dev"],
])
def test_every_verifying_command_reports_the_hint(project, capsys, argv):
    applied_then_swapped(project)
    code, out, err = run_cli(capsys, project, *argv)
    assert (code, out) == (4, "")
    assert err.strip() == "Error: " + HINT.format(env="dev")
