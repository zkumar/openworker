# Receipt verification (Part 11)

The harness emits a JSON **receipt** per work item. This note records what that receipt proves,
what it does not, and the change that would make it prove more.

## Today (Level 1 — built)

The fabric signature binds to the sealed **envelope**: `Part11SingleSignoff.sign()` signs the
envelope, and the gate exposes `envelope.chain.sha256`. The human signs the *record*.

The receipt is a **derived report**. Historically it copied that envelope hash and nothing else,
so any field could be edited after emission without detection.

Level 1 adds `integrity`:

```json
"integrity": {
  "alg": "sha256-canonical-json",
  "content_sha256": "…",   // sha256 of the canonical receipt, this field excluded
  "envelope_sha256": "…"   // the fabric envelope hash the human signature covers
}
```

Canonicalisation: `json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False)`,
UTF-8, with the `integrity` key removed. Deterministic across languages and transports.

A consumer can therefore:

1. `POST /v1/receipts/verify` with the receipt → `{"ok": true}` means nothing was edited.
2. Take `envelope_sha256` to the fabric chain (`/api/runs/{run}/chain`) to confirm a human signed
   that decision. The verify endpoint deliberately does not fetch — verification of the signature
   itself belongs to the party holding the evidence chain.

### What Level 1 does not prove

The digest is computed by the harness, not signed by an authority. Someone who can rewrite the
receipt **and** recompute `content_sha256` produces a receipt that verifies. The tie to a human is
only as strong as the `envelope_sha256` lookup. So Level 1 detects *accidental or third-party
edits in transit*; it does not prevent a forged receipt from a compromised harness.

## Level 2 (built — fabric receipt-digest v1.0.0)

The digest sits **inside the envelope payload** the human signs. Fabric owns the contract:
`regagentic-fabric/CONTRACTS.md` §11 and RFC 0053 (fabric jobs F-013/F-014/F-015, merged as
`9fa5c92a4e552fbf45886921e331db6cc8799f1c`); the harness side is openworker job F-012.

1. At signing the harness builds the receipt body, takes the **signed body** (the body minus
   `signature`, `sealed`, `status`, `awaiting_signoff` — the fields that only restate whether the
   signature exists), freezes that snapshot on the work item, and POSTs
   `sha256(canonical signed body)` to `POST /api/runs/{run}/receipt-digest` BEFORE `POST /signoff`.
2. Fabric seals `payload.receipt_digest` into the final decision envelope, so `chain.sha256` and
   the Part 11 signature cover it.
3. **The signed body is frozen at signing.** The signature appends the run's final sealed step,
   so every receipt emitted afterwards carries the signed fields from the frozen snapshot,
   byte-identical to what the digest covers; only the signature-derived fields are read live.
4. `integrity.signed_body_sha256` on the emitted receipt therefore equals the sealed
   `receipt_digest`, and a consumer confirms it via `GET /api/runs/{run}/chain` (the sealed final
   envelope exposes `receipt_digest` and its full `sha256_full`). A forger must break the
   signature, not just recompute a hash.

Against an older fabric without the endpoint the digest post fails quietly (never retried on a
4xx) and the receipt stays at Level 1 — locally verifiable, not chain-sealed. The item records
which happened (`receipt_digest_recorded`).
