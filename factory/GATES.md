# Gate ledger

One row per job per gate. "checked by" is honest: **agent (self)** is not independent review.
A job may not be `building` until `spec` says `approved(<name>, <date>)`.

| job | gate | date | checked by | evidence |
|---|---|---|---|---|
| F-001 | spec | — | — | withdrawn as a bug: the gate renders (verified with no navigation) |
| F-010 | spec | — | — | awaiting human read |
| F-011 | spec | 2026-11-06 | vijay | approved(vijay, 2026-11-06) |
| F-011 | diagnose | 2026-11-06 | agent (self) | cause named: `switchAgent` reassigns sessionId after a row click |
| F-011 | code | 2026-11-06 | agent (self) | guard on `switchAgent`; verified by evidence/switch-check.txt |
| F-011 | test | — | — | OUTSTANDING: failing-first proof not demonstrated |

## Rules
- `python3 factory/gate.py` must pass before any commit that touches product code.
- A gap listed here stays listed until a row records the evidence that closes it.
- Anything marked "agent (self)" is author-check, never an independent lens.
