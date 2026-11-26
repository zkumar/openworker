# Backlog

`/factory next` takes the first line starting with `- [ ]`, runs it as
`/factory quick`, and checks it off with its job id. For bigger items, run
`/factory shape <item>` yourself and check the item off by hand.

Add items below, one per line, for example:
`- [ ] Add a "copy link" button next to each heading on docs pages`

## From OW-F-020 CI signal split, PR #24 (2026-11-25)
- [ ] Decide the rail default and rewrite `surfaces/gui/e2e/rail-default.spec.ts`: UX-038 ruled "starts hidden" (2026-08-21) but ffba17c shipped "visible by default"; the first test in that file is quarantined (test.fixme) until the owner picks which default it should pin.
- [ ] Remove the prefilled `dr.md` / `test` credentials rendered by `surfaces/gui/src/components/FabricBar.tsx`: OW-F-019 removed the baked identity from the backend only; the GUI identity bar still ships test credentials as defaults.
- [ ] Watch the two e2e tests seen flaky once on CI (`surfaces/gui/e2e/machines.spec.ts:339`, `surfaces/gui/e2e/reasoning.spec.ts:7`); stabilise or quarantine with reason if they recur.

## From OW-F-019 fabric credentials, PR #23 (2026-11-25)
- [ ] Give the signing-path fabric login a `raise_for_status`: a rejected login currently surfaces as `KeyError('access_token')` in `sign_error` instead of a clean refusal (`coworker/server/manager.py` `sign_channel_item`).
- [ ] Withhold sidecar secrets from the other subprocess spawns that still inherit the full `os.environ`: `git_settings.py`, `workspace_safety.py`, `llamacpp_setup.py` and `openshell.py` (the agent shell in `coworker/tools/shell.py` already withholds them).
- [ ] Validate `REGAGENTIC_FABRIC_URL` (require https for non-local hosts): today the fabric password could travel over plain http to a remote host.

## From OW-F-018 input gate rendering, PR #22 (2026-11-25)
- [ ] Second input gate renders untyped (accepted at approval): fabric's `regagent_answer_input` reply at 614a456 carries field names without types, so after a first answer the renderer draws a second gate's fields as plain textareas; an `int` or `bool` field there gets refused and must be answered in Studio, and an idempotent reply leaves the footer empty. Fix is a fabric minor version returning `pending_input` in the answer reply, then `nextStopOf` in `surfaces/gui/src/views/WorkItemView.tsx` consumes it. Cross-repo: needs a features/<slug>.md entry in the workspace root.
- [ ] Restrict gate actions (`/resolve`, `/input`) to human or operator principals and bind the recorded actor to the authenticated key instead of the self-asserted `x-openworker-actor` header (OW-F-018 security review rounds 1 and 2).
- [ ] Add a test for the Temporal workflow-level input wait loop (no Temporal test env today, so it is untested; OW-F-018 decision.md traceability S3/S4).
- [ ] Handle the list form `visibility: ["app"]` in the app-only tool drop in `coworker/mcp/tools.py` (today only the string form is dropped).
- [ ] Add the 10 vitest failures in `Sidebar.test.tsx` and `Composer.draft.test.tsx` to `docs/known-failures.md`.
- [ ] Owner livecheck after PR #22 merges (tracking, not a code item): answer a gate live through a real MCP Apps host. Done 2026-11-26: the bridge installer re-pinned renderer digest `68a9fb7af768ef315516f56e0f4fdf8234e5b252a0e5748bc0091f5fe89d6fd9` and the fabric checkout is at 614a456. The gateway's `mcp` extra was installed into fabric's venv the same day, so the gateway can start; only the live answer itself remains.

## From OW-F-016 cite-back against fabric §14 (2026-11-13)
- [x] Align the renderer's ingestion point with work-item bundle v1.0.0 (fabric CONTRACTS.md §14, 38806bc, job F-022): in `surfaces/gui/src/views/WorkItemView.tsx` `workItemOf` must read the per-step list from `envelopes` (not `steps`, which §14 makes an int) and `SignedLine` must read `signature.signer`/`signature.signed_at` (not `approver`/`at`); fix the Plan type's `states` to `[{name, terminal}]`; update `fixtures.ts` (payorBundle has steps/envelopes inverted) and the affected vitests. Details in OW-F-016 spec.md Decisions cite-back. Blocks the owner's live render check. → OW-F-017-bundle-v1-ingestion

## From OW-F-016 PR #18 CI (2026-11-11)
- [x] CI on main is red and has been for at least the last 5 runs (incl. 46610d5): pytest 217 failed (many "missing or invalid OpenWorker sidecar token", so the CI env lacks the sidecar token the suite needs) and gui-e2e 5 failed (rail-default, remote-connectors machine scope, skills-session, skills-settings, team-view). PR #18 does not add to either (211/5116 pytest, same 5 e2e). Fix the CI environment or re-baseline against docs/known-failures.md so main's checks can go green. → OW-F-020-ci-signal-split (PR #24: blocking pytest-gate, non-blocking pytest-full, 4 e2e fixes, 1 quarantine)

## From OW-F-015 shaping (2026-11-10)
- [ ] Unify Worklist.tsx's narrower local RunData type with RunPanel's (two separate declarations of the same payload).
- [ ] Fix or retire the `text-warn` class RunPanel's TONE map uses: tailwind.config.js defines warnInk/warnSoft, not warn, so the class looks undefined.

## Audit 2026-11-06 (first Claude session, read-only)
- [ ] F-012 is open/reversed: the harness posts `receipt_digest` to `/api/runs/{run}/receipt-digest`, but fabric has no such endpoint or field anywhere (invented contract, forbidden by workspace rules). Fix order per workspace: spec the receipt contract in fabric (CONTRACTS.md/RFC), implement fabric first, then re-verify signed_over_content with a joined run. Cross-repo: needs a features/<slug>.md entry in the workspace root.
- [x] Replace hardcoded fabric credentials ("dr.md" / "test") in coworker/dispatch/router.py (lines 36-37) and coworker/server/manager.py (~line 8233) with configuration. Test identity is baked into the signing path. → OW-F-019-fabric-credentials-config (PR #23)
- [ ] Decide the release/harness-line rule: 7 commits (F-010, F-012 t01-t03 + reversal) landed directly on main after the one-time reconcile at 115ea9b, bypassing the flow AGENTS.md line 13 still prescribes. Retire the rule in AGENTS.md + docs/harness-release-line.md, or resume landing there.
- [ ] Make the local gate fail loudly when fabric at :8766 is down: tests/test_channel_route.py (lines 50, 71) and tests/test_dispatch_router.py (line 30) skipif(_fabric_up()), so the gate silently shrinks and can look green.
- [ ] Reconcile upstream-remote docs with reality: AGENTS.md and docs/harness-release-line.md describe an `upstream` remote with push disabled; the checkout has no upstream remote at all.
- [ ] Add the fabric contract version or commit citation the workspace rules require to the harness specs (none found in docs/ or factory/).
- [ ] Fix or remove the "RFC 0041 F4" citations in coworker/server/manager.py and coworker/dispatch/router.py docstrings; fabric's docs/rfc/ ends at 0020, no such RFC exists.
- [ ] Commit the uncommitted Software Factory+ installer update (17 modified + 4 untracked files) on a branch.
- [ ] Re-record docs/known-failures.md: the F-012 commits postdate the recorded baseline (224 failed / 5071 passed at 115ea9b); receipt tests need re-baselining.

