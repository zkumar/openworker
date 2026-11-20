# Factory config — openworker (harness)

## Limits
- base_branch: main
- max_parallel_implementers: 1     # one venv, one sidecar port, one dev server
- max_fix_rounds: 2
- quick_spec_gate: true            # spec stops at `ready` for a human before code
- serial_browser_lenses: true      # ux then ui; one dev server at a time
- rereview: changed        # changed: after round 1, re-run lenses that asked for changes, code, compliance,

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
- delivery_control: root  # root: runners stop at "approved"; /factory approve in the root delivers

## Always escalate
- touches PHI, member identity or clinical content
- changes a fabric contract: capability card, plan, chain, receipt, sign-off
- changes auth, keys, tenancy or the tenant-scope of a read
- changes evidence emission or receipt integrity
- any schema change or data migration
- adds, removes or upgrades a dependency

## Gates
- `.venv/bin/python -m pytest tests/test_channel_route.py tests/test_channels.py
  tests/test_dispatch_router.py tests/test_ingress.py tests/test_receipt_integrity.py
  tests/test_receipt_verification.py tests/test_runstore.py tests/test_keys.py -q`
  — the local gate. The full suite is CI-only; see `docs/known-failures.md`.
- `cd surfaces/gui && npm run build` (tsc --noEmit + vite build)
- `.venv/bin/ruff check <changed files>` where Python changed
- A UI change carries before/after captures, labelled from the run log

## Cross-repo rule
fabric owns the contracts. A harness job that consumes a contract change cites the fabric job id in
its spec and may not invent contract fields. Merge order: fabric first, harness pinned after.

## Specs
`factory/jobs/<job-id>/spec.md` · `tickets/` · `visuals/` then the SPEC GATE.

## PR follow-up

Used by `/factory watch <job-id>` after a PR is open (merge_mode: pr).

- ci_repairs: 2           # automatic fix attempts for failing CI checks before asking you
- pr_feedback: ask        # ask: show new review comments and wait for you; auto: send them to the fixer

## Cross-vendor review

Used when the `cross` lens is on. The command reads the review prompt on stdin,
runs in the job worktree, and must not be able to write (read-only sandbox).

- cross_command: codex exec --sandbox read-only --ephemeral -
- cross_timeout_min: 15

## Visuals

What the `visualizer` agent draws for approval (see `.claude/skills/factory/visuals.md`).
`always`, `auto` (only when the job has something to show) or `off`.

- context: always        # who and what is involved
- solution: always       # the parts this job adds or changes
- interaction: auto      # sequence diagram of the main story
- logical: auto          # data model / domain types
- deployment: auto       # only when hosting, infra or CI changes
- ux_journey: auto       # screens and states a user moves through
- ui_wireframes: auto    # grey-box HTML mock-ups of new or changed screens
- as_built: on           # before approval, redraw from the code and report drift from the plan

## Ports

Each job gets a block of ports. With `n` the job number (`004` → 4):
`base = 5100 + 20 * n`.

- implementer slot k (0, 1, 2 ...): base + k
- fixer: base + 8
- reviewer-ux: base + 9
- reviewer-ui: base + 10

