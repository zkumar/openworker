# Landing harness work: the release line

## The situation
This repository is a fork. Our product work (the governed run loop, receipts, keys, metrics, the
run panel) sits on a branch built from `5bc10d9`. Meanwhile `main` was synced forward and is now
**966 commits ahead** of that point, carrying upstream refactors of `App.tsx` and `SettingsView.tsx`.

Rebasing 39 commits across ten stacked branches onto that drift means resolving the same upstream
changes ten times, and again at every future sync.

## The approach
Land the work on the line it was built on, then reconcile with `main` **once**:

1. `release/harness-line` is cut at `5bc10d9` — the exact base our branches were built on, so the
   stack applies with no conflicts.
2. PR #2 targets the release line; #3–#11 continue to chain off each other.
3. Merge the ten PRs in order into `release/harness-line`.
4. Merge `release/harness-line` into `main` **once**, resolving the upstream drift in a single
   deliberate pass — not ten.
5. Tag that merge, so the reconciliation point is identifiable later.

## Why not rebase onto main directly
Purest, and I tried it: `SettingsView.tsx` alone needed the Organization tab woven into a
restructured tab model, and that cost repeats for every branch and every future upstream sync.
The release line pays it once.

## Remote convention (fixed)
| name | repo | push |
|---|---|---|
| `origin` | `zkumar/openworker` (ours) | yes |
| `upstream` | `andrewyng/openworker` (third party) | **disabled** |

Before this was corrected, `origin` pointed at the third-party repo and `origin/main` meant *their*
main — which is exactly how the wrong baseline got measured. `upstream` is now read-only on purpose.

## The longer-term answer
The fork should stop being load-bearing. Our additions belong in a `regagentic-harness` package
installed into stock OpenWorker (fabric client, channels, run loop, receipts, keys, metrics, UI),
so our product is reviewable in our own repository and upstream syncs are dependency bumps, not
merge conflicts. The release line is a bridge to that, not a replacement for it.
