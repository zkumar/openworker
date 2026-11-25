# Known failures — harness suite

Recorded 2026-11-06 on `main` @ `115ea9b`.

## The finding
The full suite does **not** pass on a developer machine, and the environment is not the cause.
Two runs, 20 minutes each:

| run | condition | result |
|---|---|---|
| polluted | sidecar + GUI running, used state dir | **216 failed** · 5079 passed |
| clean | services stopped, `COWORKER_STATE_DIR` empty | **224 failed** · 5071 passed |

Stopping the services and isolating state made it **worse**, not better. So these failures are not
session leftovers; the suite assumes a CI-only environment.

Failures by file (clean run, top):
```
test_server.py 40 · test_remote_home.py 30 · test_skills_api.py 16 · test_cloud_server.py 13
test_memory_api.py 12 · test_run_cli.py 7 · test_web_search.py 6 · test_subscriptions.py 6
test_persona_connections.py 6 · test_fake_slack.py 6 · test_slack_workspaces.py 5
```
They are concentrated in core API surfaces, not only external connectors — so "park the connector
tests" does not make the suite green.

## Decision
**The full suite is not the local gate.** It is CI's job. Treating ~220 failures as a "baseline"
would normalise a broken signal.

**Local gate for this repo:**
```bash
./.venv/bin/python -m pytest tests/test_channel_route.py tests/test_channels.py \
  tests/test_dispatch_router.py tests/test_ingress.py tests/test_receipt_integrity.py \
  tests/test_receipt_verification.py tests/test_runstore.py tests/test_keys.py \
  tests/test_receipt_body.py tests/test_mcp_tool_selection.py \
  tests/test_shell_env_isolation.py tests/test_temporal_optin.py -q
cd surfaces/gui && npm run build
```
These are the test files that cover this product's work plus the UI build. The 12 files are
the same list CI's `pytest-gate` job runs, so the local and CI gates do not drift.

## CI (OW-F-020)
`.github/workflows/ci.yml` splits the Python signal:
- **`pytest-gate` blocks.** It runs exactly the 12 files of the local gate above. A red gate
  means a real regression in the product's tests. The fabric-dependent tests in
  `test_channel_route.py` and `test_dispatch_router.py` skip there (no fabric at :8766 in CI).
  The tests that need the temporal extra (the two durable tests in `test_dispatch_router.py`
  and one in `test_temporal_optin.py`) also skip there: CI does not install
  `openworker[temporal]`, whose `rfsdk-kernel` is not on PyPI. With
  `OPENWORKER_EXECUTOR=temporal` set they fail instead of skipping.
- **`pytest-full` does not block.** It runs the whole suite (`pytest tests -q --cov=coworker`)
  with job-level `continue-on-error: true` and still uploads the `coverage-report` artifact.
  Its failures are the debt described below, **not expected results**: nothing is marked
  xfail, skipped or deselected to make it pass. Read the job, not the workflow badge.
- `gui-unit` and `gui-e2e` block as before.

**Quarantined e2e test** (`test.fixme`, so it is reported as skipped with its reason):
- `surfaces/gui/e2e/rail-default.spec.ts` "rail is hidden by default; the toggle persists
  across restarts". ffba17c ("rail visible by default") changed the shipped default this test
  pins (UX-038 owner ruling 2026-08-21: "starts hidden"), and its probe
  (`rail-toggle-artifacts`) no longer shows whether the rail is open. Rewriting it needs the
  owner to decide which default is right.

## Parked — external services this deployment does not use
Named explicitly so nobody mistakes "parked" for "passing". Not counted in the local gate:
- `test_slack_*`, `test_fake_slack` — no Slack workspace, outbound sockets unavailable
- `test_web_search` — no provider keys
- `test_cloud_server`, `test_subscriptions` — no cloud broker
- `test_ui_refresh_e2e`, browser tests — no browser in this environment
- `test_codex_provider`, `test_remote_home`, `test_machine_poll` — no remote machine enrolled

## Known failures — real, to be fixed
The remainder of the 224 in the clean run are **unexplained**, not parked. They are the harness's
debt, and CI is where they must be triaged. This file exists so nobody claims the suite is green.
