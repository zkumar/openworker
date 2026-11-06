# Gate ledger

One row per job per gate. "checked by" is honest: **agent (self)** is not independent review.
A job may not be `building` until `spec` says `approved(<name>, <date>)`.

| job | gate | date | checked by | evidence |
|---|---|---|---|---|
| F-001 | spec | — | — | withdrawn as a bug: the gate renders (verified with no navigation) |
| F-010 | spec | 2026-11-06 | vijay | approved(vijay, 2026-11-06) |
| F-010 | code t01 | 2026-11-06 | agent (self) | connector_bridge.py — 6 tests |
| F-010 | code t02 | 2026-11-06 | agent (self) | bindings.py — 5 tests, backoff + dead letter |
| F-010 | verify | 2026-11-06 | agent (self) | 52 local tests + live loop (denied → gate → sealed → verify True) |
| F-011 | spec | 2026-11-06 | vijay | approved(vijay, 2026-11-06) |
| F-012 | spec | 2026-11-06 | vijay | approved(vijay, 2026-11-06); freeze-at-signing accepted |
| F-012 | code t01 | 2026-11-06 | agent (self) | receipt_body + digest_for_signing; one builder |
| F-012 | code t03 | 2026-11-06 | agent (self) | signing_body + signed_over_content; recomputed-hash forgery now detected |
| F-012 | code t02 | 2026-11-06 | agent (self) | call site records the digest before signoff; best-effort by design |
| F-012 | verify | 2026-11-06 | agent (self) | REVERSED — joined run FAILED: the digest is not in the evidence store, so signed_over_content was local arithmetic. Job back to building. |
| F-012 | re-verify | 2026-11-06 | agent (self) | Rebuilt against fabric receipt-digest v1.0.0 (CONTRACTS.md §11, RFC 0053, merged 9fa5c92a4e552fbf45886921e331db6cc8799f1c). Joined run vs that fabric (run_4a2ea8682cc4): posted digest 376fa90f042358e1a9036e7d963e01a32380df970f9e3625b016658cf6982a82 came back sealed in the final envelope payload (only envelope carrying it; sha256_full c2d2df4b24a385a764442dee1028a9198ea8eb5610c47bb1cd95299db16359aa), verify_receipt → ok + signed_over_content true, one-byte edits to decision / step summary / evidence.chain_head / work_item.ref each flip it false even with content_sha256 recomputed. Local gate 47 passed (41 baseline + 6 freeze tests, fabric-backed tests executed); surfaces/gui npm run build clean. |
| F-011 | diagnose | 2026-11-06 | agent (self) | cause named: `switchAgent` reassigns sessionId after a row click |
| F-011 | code | 2026-11-06 | agent (self) | guard on `switchAgent`; verified by evidence/switch-check.txt |
| F-011 | test | 2026-11-06 | vijay | NOT REQUIRED — owner decision: leave it. The fix is verified (evidence/switch-check.txt); the failing-first proof was attempted 4x and failed on harness flakiness, not on the product. Residual risk accepted. |

## Rules
- `python3 factory/gate.py` must pass before any commit that touches product code.
- A gap listed here stays listed until a row records the evidence that closes it.
- Anything marked "agent (self)" is author-check, never an independent lens.
