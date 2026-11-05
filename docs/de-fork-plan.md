# De-forking the harness

## Measured surface (not an estimate)
Against the merge base with `main`:

```
67 files ADDED      — ours already: channels/, dispatch/, ingress.py, receipts.py,
                      auth/keys.py, observability.py, server/runstore.py, RunPanel, Worklist
15 files MODIFIED   — 904 insertions / 49 deletions woven into upstream files
```

The 15 modified files, by weight:

| File | Δ | Why |
|---|---|---|
| `coworker/server/manager.py` | +373 | run lifecycle, receipts, tenant stamping |
| `coworker/server/app.py` | +236 | endpoints (channels, receipts, keys, metrics), auth middleware |
| `coworker/inbox.py` | +121 | SQLite storage, atomic 0600 writes |
| `surfaces/gui/src/App.tsx` | +75 | run panel wiring |
| `components/SessionIntro.tsx` | +53 | fabric task list |
| 10 others | ≤19 each | nav rows, settings tab, inbox tab, locales, css |

## The blocker
There is **no extension machinery**: no entry points, no plugin registry, and
`create_app(manager)` accepts nothing but a manager. So a zero-fork extension is not possible
today without changing upstream. Anything claiming otherwise would be wishful.

## The plan
Two tracks, in this order.

### Track 1 — shrink the server diff (we can do this alone)
The server coupling is 730 of the 904 lines, but our endpoints are already self-contained
functions. Move them into a single `APIRouter` owned by our code:

- `regagentic/router.py` — channels, receipts, keys, metrics endpoints (moved, not rewritten)
- `regagentic/auth.py` — the key middleware, registered as a dependency
- `regagentic/lifecycle.py` — run start/finish, receipts, tenant stamping

Upstream then needs **three small hook lines** instead of 730 lines: include the router, add the
middleware, and call the lifecycle from the one place a run starts. That is the whole win: the
fork diff drops from 904 to roughly 150 lines, and the part that must be re-resolved at each
upstream sync becomes a handful of insertions rather than whole-file rewrites.

### Track 2 — UI slots (needs a small upstream contribution)
The 184 lines of UI coupling are insertion points: a nav row, a settings tab, an inbox tab, a
session intro, a panel above the transcript. The honest fix is a slot registry in the GUI
(`registerView(slot, component)`) accepted upstream. Until that exists, keep these edits tiny and
stable — each is ≤20 lines and they conflict rarely.

## What this is not
This does not remove the fork today. It converts it from "904 lines tangled through 15 files" to
"a small hook surface plus our own package", which is the difference between a fork that can be
synced in an afternoon and one that costs a week each time.

## Order of work
1. Land the current stack (it is reviewable and ready).
2. Track 1 refactor as its own PR — no behaviour change, tests must stay green.
3. Ask upstream for the slot registry (Track 2), or carry the small UI patch series indefinitely.

Refactoring before landing would invalidate ten reviewed slices; that is why the order matters.
