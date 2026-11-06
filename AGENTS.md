# openworker (the harness)

This is a **fork** of `andrewyng/openworker`. Our product work lives on top of it.
Read this before touching anything; it is the only repo briefing agents get.

## Remotes — read this first
| name | repo | push |
|---|---|---|
| `origin` | `zkumar/openworker` (ours) | yes |
| `upstream` | `andrewyng/openworker` (third party) | **disabled** |

A plain `git push` goes to **our** repo. Never re-enable the upstream push URL.
`main` is synced forward from upstream periodically; work lands on `release/harness-line` first.

## What this repo is
The harness around the governed engine: channels → work item → dispatcher → fabric run → human
gate → JSON receipt. Fabric (a separate repo, `zkumar/regagentic-fabric`) owns the contracts;
this repo consumes them and never invents contract fields.

## Commands — proven in this checkout
```
.venv/bin/python -m pytest tests/ -q            # full suite; see docs/known-failures.md for the baseline
.venv/bin/python -m pytest tests/<file> -q      # one file (there is no .venv/bin/pytest)
cd surfaces/gui && npm run build                # tsc + vite build (the UI gate)
cd surfaces/gui && npm run test                 # vitest run
cd surfaces/gui && npx playwright test          # e2e (needs the sidecar + GUI running)
```
Sidecar: `COWORKER_API_TOKEN=<key> .venv/bin/python -m coworker.server.run --port 8765`
GUI: `cd surfaces/gui && npm run dev -- --port <PORT>`

**No `--timeout` flag**: pytest-timeout is not installed.

## Gates
1. No **new** test failures beyond `docs/known-failures.md`.
2. `npm run build` must pass for any UI change.
3. A UI change carries **before and after** captures, labelled from the run log, same viewport and state.
4. Every work item that changes output carries the receipt assertion (`tests/test_receipt_*.py`).

## Invariants
1. **A channel run is a panel, not a chat.** No synthetic transcript message.
2. **Every item emits exactly one JSON receipt** — sealed, rejected, or error. Refusals are not retried.
3. **Never retry a 4xx.** Refusals are terminal (`FabricRefusal.retryable` is False).
4. **Regulated data at rest is `0600` and atomic.** Receipts are keyed by the **request**, never the member.
5. **The receipt is derived at read time**, never a stored snapshot.
6. **Accepted work is durable**: the ingress event is committed before dispatch.
7. **A tenant sees only its own work**; cross-tenant reads answer 404.

## Pointers
- `COMPLIANCE.md` · `CODING_STANDARDS.md`
- `docs/production-readiness.md` — what is built and what is not
- `docs/de-fork-plan.md` — why this is a fork and how it stops being one
- `docs/known-failures.md` — the documented baseline
