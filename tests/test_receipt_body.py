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


def test_sealing_the_body_reproduces_the_emitted_receipt():
    body = _body()
    sealed = seal_receipt(body)
    assert sealed[INTEGRITY_KEY]["content_sha256"] == digest_for_signing(body)


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
