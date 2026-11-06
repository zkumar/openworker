"""F-012 t02 — the signing path records the digest BEFORE it signs.

A source-level assertion, deliberately: the call site needs a live fabric and a model to exercise,
and a test that cannot run proves nothing. This checks the ordering that actually matters — recording
after signing would seal a digest the signature never covered.
"""

from pathlib import Path

from coworker.receipts import digest_for_signing, receipt_body

SOURCE = Path(__file__).resolve().parents[1] / "coworker" / "server" / "manager.py"


def test_the_signing_path_records_a_digest():
    src = SOURCE.read_text()
    assert "/receipt-digest" in src, "the signing path must record the digest"


def test_the_digest_is_recorded_before_the_signoff_call():
    src = SOURCE.read_text()
    record_at = src.index("/receipt-digest")
    signoff_at = src.index("/signoff")
    assert record_at < signoff_at, "recording after signing seals a digest nothing covered"


def test_the_signed_body_is_frozen_before_the_digest_post():
    """F-012 rebuild: the snapshot must land on the item before the digest leaves the harness,
    or a crash (or the final step append) emits bytes the sealed digest never covered."""
    src = SOURCE.read_text()
    assert "SIGNED_BODY_KEY: frozen" in src, "the signing path must freeze the signed body"
    assert src.index("SIGNED_BODY_KEY: frozen") < src.index("/receipt-digest")


def test_the_digest_comes_from_the_receipt_body():
    body = receipt_body(data={"decision": "denied", "steps": []}, channel="webhook",
                        ref="PA-1", received_at="2026-11-06T10:00:00Z",
                        session_id="ch_1", inbox_id="1")
    d = digest_for_signing(body)
    assert len(d) == 64 and int(d, 16) >= 0
