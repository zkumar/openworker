# Production readiness

Written after closing the gaps identified in review. Every claim below was exercised against a
running system; the evidence lives in `docs/loop-evidence/` and in the test suites.

## Closed

| Gap | What changed | Verified |
|---|---|---|
| **Durable ingress** | `ingress_event` table committed before dispatch; a consumer re-dispatches accepted-but-unstarted work on restart; a file spool accepts records while the harness is down | killed the harness, dropped 2 records, restarted — both processed |
| **PHI at rest** | inbox moved to SQLite at `0600`; atomic commit (no truncated file) | `inbox.json` was `0644` with clinical notes |
| **Receipt integrity** | receipts carry `content_sha256` + `envelope_sha256`; `POST /v1/receipts/verify` | edited decision/step/signature → all detected |
| **Transactional storage** | inbox + run journal + ingress + keys all SQLite (WAL) | 140 items migrated, none lost |
| **Auth / tenancy** | per-tenant hashed API keys, revocable, rotatable, with roles and expiry; env token adopted on upgrade | see `tests/test_keys.py` |
| **Tenant isolation** | inbox list, receipt read and resolve are scoped; cross-tenant reads return 404 | agent saw 1 item, admin 58, other tenant 0 |
| **Multi-writer safety** | writes touch only changed rows; deletions are explicit; no blanket delete | a stale writer no longer erases another's item |
| **Observability** | `GET /v1/metrics` — queue depth, run states, decision mix, ages, named alerts | surfaced 22 signatures waiting >4h |
| **Record source** | `REGAGENTIC_RECORD_SOURCE` seam: fixtures \| directory \| dotted path; payor/QMS/evidence loaders consult it | external record adjudicated; unknown id still refuses |

## Decisions taken without the owner present

1. **The env token becomes an admin key on upgrade.** Anything else leaves a deployed system with
   no one able to manage credentials.
2. **Cross-tenant access returns 404, not 403.** A 403 confirms the record exists.
3. **An unknown record stays a refusal** (not-found → rejected, no signature). The record *source*
   became configurable; the *semantics* did not.
4. **No bootstrap-with-open-access.** If no key exists, one is minted and logged once, rather than
   running unauthenticated as the old code did.
5. **Receipts are derived, never stored as a snapshot.** A signature can arrive while the last step
   is still being appended; a stored copy went stale in exactly that window.

## Still open — honestly

| Gap | Why it is not closed | Recommended next step |
|---|---|---|
| **Receipt signature (level 2)** | The digest is computed by the harness, not signed. A compromised harness could forge a receipt that verifies. | Put `receipt_digest` inside the envelope payload — see `docs/receipt-verification.md` for the three consequences. |
| **Single-writer assumption** | WAL keeps the database consistent, but two processes editing the SAME item are last-write-wins. | Run one sidecar per state directory, or add per-item optimistic locking (version column + compare-and-set). |
| **Connector to a real system of record** | A directory adapter exists; no claims/QMS/EDC SDK integration, no id mapping, no sync. | Implement a `RecordSource` for the customer's API and schedule a sync. |
| **Alert delivery** | Alerts are computed and exposed; nothing pages anyone. | Scrape `/v1/metrics` and route `alerts` to the operator's channel. |
| **Hard-coded demo settings** | The running instance uses `REGAGENTIC_STEP_DELAY=0.8` (pacing, for demos) and a fixed dev token. | Remove both in any real deployment; pacing is opt-in via the env var only. |
| **The harness as a second ledger** | Decisions are persisted here *and* in the domain system. Two sources of truth for a legally consequential outcome. | Decide ownership: harness emits, domain records — or make the harness the record and stop writing to the other. |
| **Not merged** | 10 fabric PRs and 1 openworker PR are open. | Owner review and merge; nothing here is on main. |

## The one-sentence summary

The hard part (resumable, gated, evidence-sealed agentic execution) was already built; what changed
in this pass is that the unglamorous half — ingest, storage, auth, integrity, visibility — now has
the same properties: durable, scoped, verifiable and observable.
