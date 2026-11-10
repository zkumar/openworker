"""OW-F-015 — a stored declared view never touches the receipt.

The view and its view_sha256 seal into the rfsdk envelope only (adr-view-sha256-seals-declared).
The signed receipt body must stay byte-identical with and without a stored view, so receipt
integrity (F-012) is untouched by presentation.
"""

import json
from types import SimpleNamespace

from coworker.receipts import (
    SIGNED_BODY_KEY,
    canonical_bytes,
    digest_for_signing,
    receipt_body,
    signing_body,
)

VIEW = {"title": "PA view sentinel", "components": [{"type": "gauge", "max": 1,
                                                     "label": "Units against limit"}]}
VIEW_SHA = "c" * 64

DATA = {"channel": "fhir", "agent": "payor.demo.prior_auth", "decision": "approved",
        "fabric_run": "run_1", "record": {"request_id": "PA-1"},
        "steps": [{"state_before": "intake", "state_after": "done", "summary": "s1",
                   "sha256": "a" * 64}]}


def _body(data):
    return receipt_body(data=data, channel="fhir", ref="PA-1",
                        received_at="2026-11-10T10:00:00Z", session_id="ch_1", inbox_id="7")


def _with_view(data):
    return {**data, "view": VIEW, "view_sha256": VIEW_SHA}


def _leaks(body) -> list[str]:
    text = json.dumps(body, ensure_ascii=False)
    return [s for s in ('"view"', "view_sha256", VIEW_SHA, "PA view sentinel") if s in text]


def test_the_signing_body_is_byte_identical_with_and_without_a_stored_view():
    without = signing_body(_body(DATA))
    with_view = signing_body(_body(_with_view(DATA)))
    assert canonical_bytes(with_view) == canonical_bytes(without)
    assert digest_for_signing(_body(_with_view(DATA))) == digest_for_signing(_body(DATA))
    assert _leaks(with_view) == []


def test_the_emitted_receipt_is_byte_identical_with_and_without_a_stored_view(tmp_path):
    """Through the real emission path: the same signed item, before and after a view is stored."""
    from coworker.server.manager import SessionManager

    manager = SessionManager(workspace=tmp_path)
    _, inbox_id = manager.channel_run_start(SimpleNamespace(channel="fhir",
                                                            record={"request_id": "PA-1"}))
    item = manager.inbox.get(inbox_id)
    signed = {**DATA, "signature": {"approver": "dr.md", "signed_at": "2026-11-10T10:05:00Z"}}
    item.data = {**(item.data or {}), **signed,
                 SIGNED_BODY_KEY: signing_body(_body(DATA))}
    without = manager.build_receipt(item)

    item.data = _with_view(item.data)
    with_view = manager.build_receipt(item)

    assert canonical_bytes(with_view) == canonical_bytes(without)
    assert with_view["integrity"] == without["integrity"]
    assert _leaks(with_view) == []


def test_an_unsigned_receipt_carries_no_view_either(tmp_path):
    from coworker.server.manager import SessionManager

    manager = SessionManager(workspace=tmp_path)
    _, inbox_id = manager.channel_run_start(SimpleNamespace(channel="fhir",
                                                            record={"request_id": "PA-1"}))
    item = manager.inbox.get(inbox_id)
    item.data = {**(item.data or {}), **DATA, "awaiting_signoff": True}
    without = manager.build_receipt(item)
    item.data = _with_view(item.data)
    with_view = manager.build_receipt(item)
    assert canonical_bytes(with_view) == canonical_bytes(without)
    assert _leaks(with_view) == []
