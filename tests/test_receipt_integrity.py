"""Regulated data hygiene: the right reference, and no two receipts overwriting each other."""

import json
import pathlib
import stat

from coworker.channels.egress import FileEgress
from coworker.server.manager import SessionManager


def _ref():
    return SessionManager._record_ref


def test_the_reference_is_the_request_not_the_patient():
    """member_id used to win by dict order, naming receipts after the patient."""
    assert _ref()({"member_id": "MEM001", "request_id": "PA-2026-001"}) == "PA-2026-001"
    assert _ref()({"patient_id": "P1", "slr_id": "SLR-2026-001"}) == "SLR-2026-001"
    assert _ref()({"capa_id": "CAPA-2026-101", "provider_npi": "123"}) == "CAPA-2026-101"


def test_a_subject_id_never_becomes_the_reference():
    assert _ref()({"member_id": "MEM001"}) == ""
    assert _ref()({"provider_npi": "1234567890"}) == ""
    assert _ref()({}) == ""


def _receipt(ref: str, inbox_id: str) -> dict:
    return {"work_item": {"ref": ref}, "harness": {"inbox_id": inbox_id}, "decision": "denied"}


def test_two_requests_for_one_member_do_not_overwrite(tmp_path):
    sink = FileEgress(tmp_path)
    sink.deliver(_receipt("PA-2026-001", "aaaaaaaa1111"))
    sink.deliver(_receipt("PA-2026-001", "bbbbbbbb2222"))   # different item, same ref

    files = sorted(p.name for p in pathlib.Path(tmp_path).glob("*.json"))
    assert len(files) == 2, f"one receipt would have been lost: {files}"
    kept = {json.loads((pathlib.Path(tmp_path) / f).read_text())["harness"]["inbox_id"] for f in files}
    assert kept == {"aaaaaaaa1111", "bbbbbbbb2222"}


def test_re_emitting_the_same_item_replaces_its_own_file(tmp_path):
    sink = FileEgress(tmp_path)
    first = _receipt("PA-2026-001", "aaaa1111")
    sink.deliver(first)
    sink.deliver({**first, "sealed": True})                 # e.g. after the signature
    files = list(pathlib.Path(tmp_path).glob("*.json"))
    assert len(files) == 1, "re-emitting one item must not duplicate it"
    assert json.loads(files[0].read_text())["sealed"] is True


def test_the_receipt_log_keeps_every_delivery(tmp_path):
    sink = FileEgress(tmp_path)
    sink.deliver(_receipt("PA-2026-001", "aaaa1111"))
    sink.deliver(_receipt("PA-2026-001", "bbbb2222"))
    lines = (pathlib.Path(tmp_path) / "receipts.jsonl").read_text().strip().split("\n")
    assert len(lines) == 2
