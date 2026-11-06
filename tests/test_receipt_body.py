"""F-012 t01 — one builder for the bytes we digest and the bytes we emit."""

from coworker.receipts import INTEGRITY_KEY, digest_for_signing, receipt_body, seal_receipt

DATA = {"channel": "webhook", "agent": "payor.demo.prior_auth", "decision": "denied",
        "steps": [{"state_before": "intake", "state_after": "review", "summary": "s1", "sha256": "a" * 64},
                  {"state_before": "review", "state_after": "done", "summary": "s2", "sha256": "b" * 64}]}


def _body(**over):
    kw = dict(data=DATA, channel="webhook", ref="PA-2026-001",
              received_at="2026-11-06T10:00:00Z", session_id="ch_1", inbox_id="42")
    kw.update(over)
    return receipt_body(**kw)


def test_the_body_carries_no_integrity_block():
    assert INTEGRITY_KEY not in _body()


def test_sealing_records_both_digests_and_they_are_different():
    """content_sha256 covers the emitted receipt; signed_body_sha256 covers what the human signed.

    They must not be the same value: the signature dates from before `signature`/`sealed`/`status`
    existed, so signing the emitted bytes is impossible by construction.
    """
    from coworker.receipts import content_sha256

    body = _body()
    sealed = seal_receipt(body)
    integrity = sealed[INTEGRITY_KEY]
    assert integrity["content_sha256"] == content_sha256(body)
    assert integrity["signed_body_sha256"] == digest_for_signing(body)
    assert integrity["content_sha256"] != integrity["signed_body_sha256"]


def test_the_digest_changes_when_any_consumer_visible_field_changes():
    base = digest_for_signing(_body())
    changed = digest_for_signing(_body(data={**DATA, "decision": "approved"}))
    assert base != changed, "a signature over one decision must not verify another"


def test_the_body_is_pure_and_repeatable():
    assert _body() == _body()


def test_steps_are_numbered_and_the_chain_head_is_the_last_hash():
    body = _body()
    assert [s["n"] for s in body["steps"]] == [1, 2]
    assert body["evidence"]["chain_head"] == "b" * 64


# t03 — the forgery the whole exercise exists to stop.
def test_a_clean_receipt_is_signed_over_its_content():
    from coworker.receipts import seal_receipt, verify_receipt

    v = verify_receipt(seal_receipt(_body()))
    assert v["ok"] is True
    assert v["signed_over_content"] is True


def test_editing_a_field_and_recomputing_the_hash_is_still_caught():
    """The attacker's best move: change the decision AND recompute content_sha256."""
    import hashlib
    import json

    from coworker.receipts import INTEGRITY_KEY, seal_receipt, verify_receipt

    forged = seal_receipt(_body())
    forged["decision"] = "approved"                     # flip the decision
    body = {k: v for k, v in forged.items() if k != INTEGRITY_KEY}
    forged[INTEGRITY_KEY] = {
        **forged[INTEGRITY_KEY],
        "content_sha256": hashlib.sha256(
            json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
    }
    v = verify_receipt(forged)
    assert v["ok"] is True, "the attacker recomputed content_sha256 correctly, as expected"
    assert v["signed_over_content"] is False, "but the sealed digest no longer covers these bytes"


def test_the_exclusion_is_stated_in_the_receipt():
    from coworker.receipts import INTEGRITY_KEY, seal_receipt

    integrity = seal_receipt(_body())[INTEGRITY_KEY]
    assert set(integrity["signed_body_excludes"]) == {"signature", "sealed", "status",
                                                      "awaiting_signoff"}
