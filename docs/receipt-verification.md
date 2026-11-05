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

## Level 2 (designed, not built — pending a decision)

Put the digest **inside the envelope payload** the human signs:

1. Build the receipt body (excluding `integrity`) before the final decision envelope is sealed.
2. Seal the envelope with `payload.receipt_digest = sha256(canonical body)`.
3. The emitted receipt then carries `integrity.envelope_sha256`, and the signature covers the
   digest — so a forger must break the signature, not just recompute a hash.

Consequences to decide before building:

- **The receipt freezes at signing time.** Adding a field later invalidates the digest, so any
  post-signature enrichment needs a new envelope (amendment), not a new field.
- The receipt body must be computable *before* the run terminates — it cannot include anything
  learned after the decision (wall-clock finish time, delivery outcome).
- Amendment/revocation flows (RFC 0001 `revokes_sha256`) must reference the frozen digest.

That is a genuine compliance improvement and a real constraint. It is not a drop-in change.
