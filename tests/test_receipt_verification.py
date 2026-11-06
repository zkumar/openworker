"""A receipt must detect edits made after it left the system."""

from coworker.receipts import content_sha256, seal_receipt, verify_receipt


def _receipt():
    return seal_receipt({
        "receipt_version": 1,
        "work_item": {"channel": "webhook", "ref": "PA-2026-001"},
        "agent": "payor.demo.prior_auth",
        "status": "sealed",
        "decision": "denied",
        "sealed": True,
        "signature": {"approver": "dr.md", "sha256": "e" * 64},
        "steps": [{"n": 1, "summary": "PASS: member eligible"}],
    })


def test_an_untouched_receipt_verifies():
    assert verify_receipt(_receipt())["ok"] is True


def test_the_digest_is_stable_across_re_digestion():
    r = _receipt()
    assert content_sha256(r) == r["integrity"]["content_sha256"]
    # transport round-trip must not change verification
    import json
    assert verify_receipt(json.loads(json.dumps(r)))["ok"] is True


def test_editing_the_decision_is_detected():
    r = _receipt()
    r["decision"] = "approved"
    assert verify_receipt(r)["ok"] is False


def test_editing_a_step_summary_is_detected():
    r = _receipt()
    r["steps"][0]["summary"] = "PASS: member eligible and in coverage (edited)"
    assert verify_receipt(r)["ok"] is False


def test_editing_the_signature_envelope_is_detected():
    r = _receipt()
    r["signature"]["sha256"] = "f" * 64
    assert verify_receipt(r)["ok"] is False


def test_a_receipt_without_integrity_does_not_verify():
    r = _receipt()
    del r["integrity"]
    assert verify_receipt(r)["ok"] is False


def test_verification_reports_the_envelope_to_check():
    info = verify_receipt(_receipt())
    assert info["envelope_sha256"] == "e" * 64
    assert info["sealed"] is True
    assert info["ref"] == "PA-2026-001"


# --- F-012 rebuild: the signed body is frozen at signing (fabric receipt-digest v1.0.0) --------
#
# The signature appends the run's final sealed step, mutating steps, evidence.chain_head,
# evidence.envelopes and awaiting_signoff AFTER the digest was posted. The freeze makes the
# emitted signed fields byte-identical to what the fabric sealed.

import json

from coworker.receipts import (content_sha256, digest_for_signing, emitted_body, receipt_body,
                               signing_body)

_S1 = {"state_before": "intake", "state_after": "review", "summary": "PASS: eligible",
       "sha256": "a" * 64}
_S2 = {"state_before": "review", "state_after": "denied", "summary": "decision", "sha256": "b" * 64}
_FINAL = {"state_before": "denied", "state_after": "denied", "summary": "signoff sealed",
          "sha256": "c" * 64}


def _data_at_signing() -> dict:
    return {"channel": "webhook", "agent": "payor.demo.prior_auth", "decision": "denied",
            "awaiting_signoff": True, "steps": [_S1, _S2]}


def _body(data: dict) -> dict:
    return receipt_body(data=data, channel="webhook", ref="PA-2026-001",
                        received_at="2026-11-06T10:00:00Z", session_id="ch_1", inbox_id="42")


def _signed_lifecycle() -> tuple[str, dict]:
    """What the signing path does, in order: freeze, post the digest, sign, emit."""
    frozen = signing_body(_body(_data_at_signing()))
    posted = content_sha256(frozen)                  # the digest POSTed to /receipt-digest
    frozen = json.loads(json.dumps(frozen))          # the snapshot survives persistence
    live = _body({**_data_at_signing(), "awaiting_signoff": False,
                  "signature": {"approver": "dr.md", "at": "2026-11-06 10:05", "sha256": "e" * 64},
                  "steps": [_S1, _S2, _FINAL]})      # the signature appended the final step
    return posted, seal_receipt(emitted_body(live, frozen))


def test_the_signed_body_is_byte_stable_across_the_final_step_append():
    posted, emitted = _signed_lifecycle()
    assert emitted["integrity"]["signed_body_sha256"] == posted, \
        "the emitted receipt must carry exactly the digest the fabric sealed"


def test_the_emitted_receipt_is_signed_over_its_content():
    _, emitted = _signed_lifecycle()
    v = verify_receipt(emitted)
    assert v["ok"] is True
    assert v["signed_over_content"] is True


def test_the_signature_derived_fields_are_live_not_frozen():
    """A sealed receipt must say it is sealed — only the signed content is frozen."""
    _, emitted = _signed_lifecycle()
    assert emitted["sealed"] is True
    assert emitted["status"] == "sealed"
    assert emitted["awaiting_signoff"] is False
    assert emitted["signature"]["approver"] == "dr.md"


def test_without_the_freeze_the_final_step_append_breaks_the_digest():
    """The gap the freeze closes: recomputing over the post-signature body drifts."""
    posted, _ = _signed_lifecycle()
    live = _body({**_data_at_signing(), "awaiting_signoff": False,
                  "signature": {"approver": "dr.md", "sha256": "e" * 64},
                  "steps": [_S1, _S2, _FINAL]})
    assert digest_for_signing(live) != posted


def test_a_one_byte_edit_to_a_signed_field_flips_verification():
    for edit in (lambda r: r.update(decision="approved"),
                 lambda r: r["steps"][0].update(summary="PASS: eligible."),
                 lambda r: r["evidence"].update(chain_head="d" * 64)):
        _, emitted = _signed_lifecycle()
        edit(emitted)
        assert verify_receipt(emitted)["signed_over_content"] is False


def test_an_item_without_a_frozen_body_emits_the_live_body_unchanged():
    live = _body(_data_at_signing())
    assert emitted_body(live, None) == live
