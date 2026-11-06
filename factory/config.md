# Factory config — openworker (harness)

## Limits
- base_branch: main
- max_parallel_implementers: 1     # one venv, one sidecar port, one dev server
- max_fix_rounds: 2
- quick_spec_gate: true            # spec stops at `ready` for a human before code
- serial_browser_lenses: true      # ux then ui; one dev server at a time

## Review lenses
- spec: on
- code: on
- security: on
- ux: on
- ui: on
- compliance: on
- cross: off

## Merge policy
- auto_merge: false                # regulated: an APPROVE still reaches a human
- merge_mode: pr
- pr_draft: false

## Always escalate
- touches PHI, member identity or clinical content
- changes a fabric contract: capability card, plan, chain, receipt, sign-off
- changes auth, keys, tenancy or the tenant-scope of a read
- changes evidence emission or receipt integrity
- any schema change or data migration
- adds, removes or upgrades a dependency

## Gates
- `.venv/bin/python -m pytest tests/ -q` — must not introduce NEW failures beyond the documented
  baseline in `docs/known-failures.md`
- `cd surfaces/gui && npm run build` (tsc --noEmit + vite build)
- `.venv/bin/ruff check <changed files>` where Python changed
- A UI change carries before/after captures, labelled from the run log

## Cross-repo rule
fabric owns the contracts. A harness job that consumes a contract change cites the fabric job id in
its spec and may not invent contract fields. Merge order: fabric first, harness pinned after.

## Specs
`factory/jobs/<job-id>/spec.md` · `tickets/` · `visuals/` then the SPEC GATE.
