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

Level 2 (not built, needs a contract change): put this digest INSIDE the envelope payload so the
signature covers the exact emitted bytes. See docs/receipt-verification.md.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

INTEGRITY_KEY = "integrity"


def canonical_bytes(receipt: dict[str, Any]) -> bytes:
    """Deterministic bytes for a receipt: sorted keys, no whitespace drift, UTF-8.

    The integrity field itself is excluded, so a receipt can be re-digested after transport.
    """
    body = {k: v for k, v in receipt.items() if k != INTEGRITY_KEY}
    return json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def content_sha256(receipt: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_bytes(receipt)).hexdigest()


def seal_receipt(receipt: dict[str, Any]) -> dict[str, Any]:
    """Attach the integrity block. Returns a new dict; the input is not mutated."""
    body = {k: v for k, v in receipt.items() if k != INTEGRITY_KEY}
    sig = body.get("signature") or {}
    body[INTEGRITY_KEY] = {
        "alg": "sha256-canonical-json",
        "content_sha256": content_sha256(body),
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
    return {
        "ok": bool(claimed) and claimed == actual,
        "content_sha256": actual,
        "claimed": claimed,
        "sealed": bool(receipt.get("sealed")),
        "envelope_sha256": integrity.get("envelope_sha256"),
        "decision": receipt.get("decision"),
        "ref": (receipt.get("work_item") or {}).get("ref"),
    }
