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
