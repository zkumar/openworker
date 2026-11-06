"""Receipt integrity — the emitted JSON must be checkable by whoever receives it.

The fabric's signature binds to the sealed ENVELOPE (its chain sha256). The receipt is a
derived report, so on its own it proves nothing: every field could be edited and the copied
hash would still point at the untouched envelope.

Level 1 (this module) adds a self-digest:
  integrity.content_sha256   sha256 over the canonical receipt bytes (the `integrity` field excluded)
  integrity.envelope_sha256  the fabric envelope hash the human signature covers

A consumer can therefore
  1. recompute the digest and detect ANY local edit, and
  2. take envelope_sha256 to the fabric chain to confirm a human signed that decision.

Level 2 (built against fabric receipt-digest v1.0.0 — CONTRACTS.md §11, RFC 0053): the signing
path computes digest_for_signing over the body, freezes that signed body on the work item, and
posts the digest to the fabric BEFORE the human signs. The fabric seals it into the final decision
envelope's payload, so the signature covers the exact emitted bytes. See
docs/receipt-verification.md.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

INTEGRITY_KEY = "integrity"

# F-012: these four only restate whether the signature exists, so they cannot be inside what the
# signature covers — the body would change under its own signature. The exclusion is recorded in
# the receipt so a consumer can tell exactly what was signed; verification always recomputes with
# THIS constant, never the receipt's own list (a forger must not choose their own excludes).
SIGNED_BODY_EXCLUDES = ("signature", "sealed", "status", "awaiting_signoff")

# F-012: the work-item data key holding the signed body frozen at signing. The signature appends
# the run's final sealed step, which mutates steps/evidence after the digest was computed — so the
# emitted receipt must carry the signed fields exactly as they were digested, not as they are now.
SIGNED_BODY_KEY = "signed_body"


def canonical_bytes(receipt: dict[str, Any]) -> bytes:
    """Deterministic bytes for a receipt: sorted keys, no whitespace drift, UTF-8.

    The integrity field itself is excluded, so a receipt can be re-digested after transport.
    """
    body = {k: v for k, v in receipt.items() if k != INTEGRITY_KEY}
    return json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def content_sha256(receipt: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_bytes(receipt)).hexdigest()


def receipt_body(
    *,
    data: dict[str, Any],
    channel: str | None,
    ref: str | None,
    received_at: str | None,
    session_id: str | None,
    inbox_id: str | None,
) -> dict[str, Any]:
    """The exact bytes a consumer will file, built BEFORE the envelope is sealed.

    Pure: no clock, no I/O, no store lookup. F-012 requires that what we digest and what we emit
    come from one function — two builders would drift, and a drifted receipt is signed evidence
    that says something the human never approved.
    """
    steps = data.get("steps") or []
    sig = data.get("signature") or None
    return {
        "receipt_version": 1,
        "work_item": {"channel": channel, "ref": ref, "received_at": received_at},
        "agent": data.get("agent"),
        "status": ("sealed" if sig else
                   "rejected" if data.get("not_found") else
                   "error" if data.get("error") else
                   "awaiting_signature" if data.get("awaiting_signoff") else "unknown"),
        "decision": data.get("decision"),
        "error": data.get("error") or None,
        "reason": ("request id not found in the pack's records" if data.get("not_found")
                   else None),
        "sealed": bool(sig),
        "awaiting_signoff": bool(data.get("awaiting_signoff")) and not sig,
        "signature": sig,
        "steps": [{"n": i + 1,
                   "from_state": s.get("state_before"),
                   "to_state": s.get("state_after"),
                   "summary": s.get("summary"),
                   "sha256": s.get("sha256")} for i, s in enumerate(steps)],
        "evidence": {"fabric_run": data.get("fabric_run"),
                     "envelopes": len(steps),
                     "chain_head": steps[-1].get("sha256") if steps else None},
        "harness": {"session_id": session_id, "inbox_id": inbox_id},
    }


def signing_body(body: dict[str, Any]) -> dict[str, Any]:
    """The part of the body that cannot change after signing. Everything else is derived."""
    return {k: v for k, v in body.items() if k not in SIGNED_BODY_EXCLUDES}


def digest_for_signing(body: dict[str, Any]) -> str:
    """The value to seal into the decision envelope so the signature covers this body."""
    return content_sha256(signing_body(body))


def emitted_body(live: dict[str, Any], frozen: dict[str, Any] | None) -> dict[str, Any]:
    """The body to emit once a frozen signed body exists: byte-stable under its signature.

    The signed fields come from the snapshot taken at signing, so the digest the fabric sealed
    still covers them after the signature appends the final step. Only the signature-derived
    fields (SIGNED_BODY_EXCLUDES) are read live — a sealed receipt must say it is sealed.
    Without a snapshot (pre-signing, or an item signed before the freeze existed) the live body
    is emitted unchanged.
    """
    if not frozen:
        return live
    out = signing_body(frozen)      # tolerate an over-wide stored snapshot
    for k in SIGNED_BODY_EXCLUDES:
        if k in live:
            out[k] = live[k]
    return out


def seal_receipt(receipt: dict[str, Any]) -> dict[str, Any]:
    """Attach the integrity block. Returns a new dict; the input is not mutated."""
    body = {k: v for k, v in receipt.items() if k != INTEGRITY_KEY}
    sig = body.get("signature") or {}
    body[INTEGRITY_KEY] = {
        "alg": "sha256-canonical-json",
        "content_sha256": content_sha256(body),
        "signed_body_sha256": digest_for_signing(body),
        "signed_body_excludes": list(SIGNED_BODY_EXCLUDES),
        "envelope_sha256": sig.get("sha256"),
    }
    return body


def verify_receipt(receipt: dict[str, Any]) -> dict[str, Any]:
    """Check a received receipt.

    ok          the digest matches → nothing was edited after emission
    signed      the receipt carries an envelope hash a human signature covers
    The caller must still confirm envelope_sha256 against the fabric chain; this function
    deliberately does not fetch anything.
    """
    integrity = receipt.get(INTEGRITY_KEY) or {}
    claimed = integrity.get("content_sha256")
    actual = content_sha256(receipt)
    signed_claimed = integrity.get("signed_body_sha256")
    signed_actual = digest_for_signing(receipt)
    return {
        "ok": bool(claimed) and claimed == actual,
        # F-012: the ONLY check a recomputed-hash forgery cannot defeat. `ok` proves nothing was
        # edited after emission; this proves the human's signature covers these bytes.
        "signed_over_content": bool(signed_claimed) and signed_claimed == signed_actual,
        "signed_body_sha256": signed_actual,
        "signed_body_claimed": signed_claimed,
        "content_sha256": actual,
        "claimed": claimed,
        "sealed": bool(receipt.get("sealed")),
        "envelope_sha256": integrity.get("envelope_sha256"),
        "decision": receipt.get("decision"),
        "ref": (receipt.get("work_item") or {}).get("ref"),
    }
