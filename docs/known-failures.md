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
  tests/test_receipt_verification.py tests/test_runstore.py tests/test_keys.py -q
cd surfaces/gui && npm run build
```
These are the tests that cover this product's work (36 tests) plus the UI build.

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
