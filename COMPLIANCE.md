# Compliance checklist — harness

The harness handles regulated content in transit and at rest, and emits the artefact a consumer
files. Same frame as fabric (`COMPLIANCE.md` there); this repo owns the presentation half.

## Regulated data
- Work items carry member identity and clinical notes in `inbox.sqlite` (mode `0600`, WAL, atomic).
- The receipt carries the **request** reference, never the member id, in any filename or field path
  used as a key (`coworker/receipts.py`, `SessionManager._record_ref`).
- Nothing regulated goes to a log line, a title, or an error message relayed to a user.
- **No personal information in logs or debug statements** — not in application logs, console output, error messages, or test fixtures. Log identifiers, never people.
**Retention:** 5 years, applicable in deployment. Not a development-phase obligation — development state may be discarded freely.

## Controls
| Control | Where | Guarded by |
|---|---|---|
| One receipt per item, always | `manager.channel_run_finish` / `channel_run_fail` | `tests/test_receipt_integrity.py` |
| Receipt self-digest verifies | `coworker/receipts.py` | `tests/test_receipt_verification.py` |
| PHI at rest `0600`, atomic | `coworker/inbox.py` | review + file-mode check |
| Accepted work durable | `coworker/ingress.py`, `channels/spool.py` | `tests/test_ingress.py` |
| Refusals not retried | `dispatch/router.py`, `FabricRefusal` | manual + unit |
| Tenant isolation | `auth/keys.py`, inbox scoping | `tests/test_keys.py` |
| Signature failure surfaced | `RunPanel` + `sign_error` | review |

## Evidence per change
1. Which control it touches and that the control still holds.
2. The test or capture proving it.
3. Whether a receipt, a signature or an evidence chain is affected — if yes, escalate.

## Change classes
- **Escalate:** sign-off path, receipt payload or integrity, key/identity, tenant scope, schema or
  data migration, anything that changes what a consumer receives.
- **No escalation:** UI copy and layout, docs, tests, read-only endpoints.
