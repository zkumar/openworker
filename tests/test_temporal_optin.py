"""OW-F-013 — the temporal executor is opt-in, lazy, and fails closed.

Additive test file (not in the local gate's 8-file list). The joined-run binary criterion
(kill -9 between dispatch and signoff) is driven live and recorded in factory/GATES.md; what
lives here is what a unit test can prove without a Temporal server:

  * env unset        → no temporalio import anywhere in the dispatch wiring
  * extra missing    → an actionable RuntimeError, never a silent thread fallback
  * never started    → current() refuses (fail closed)
  * frame()          → the new stage opens a run and returns (session_id, agent); None when
                       no card covers the item; a refusal maps to FabricRefusal

Temporal-path tests that NEED the dev server must fail loudly when OPENWORKER_EXECUTOR=temporal
is set and the dependency is missing — never skip silently (register rule).
"""
from __future__ import annotations

import os
import subprocess
import sys
import textwrap

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_TEMPORAL_EXPECTED = os.environ.get("OPENWORKER_EXECUTOR", "").strip().lower() == "temporal"


def _python(code: str, env: dict | None = None) -> subprocess.CompletedProcess:
    full_env = {**os.environ, **(env or {})}
    full_env.pop("OPENWORKER_EXECUTOR", None)
    if env and "OPENWORKER_EXECUTOR" in env:
        full_env["OPENWORKER_EXECUTOR"] = env["OPENWORKER_EXECUTOR"]
    return subprocess.run([sys.executable, "-c", textwrap.dedent(code)],
                          capture_output=True, text=True, cwd=REPO, env=full_env, timeout=120)


def test_env_unset_means_no_temporalio_import():
    """The negative half of the binary criterion: unset = byte-identical, no lazy module load."""
    out = _python("""
        import sys
        import coworker.server.app as app
        import coworker.dispatch  # the package the executor lives under

        assert not app._temporal_selected(), "env is unset, so temporal must not be selected"
        assert "temporalio" not in sys.modules, "temporalio was imported with the env unset"
        assert "coworker.dispatch.temporal_executor" not in sys.modules
        assert "coworker.dispatch.temporal_workflow" not in sys.modules
        print("clean")
    """)
    assert out.returncode == 0, out.stderr
    assert "clean" in out.stdout


def test_missing_extra_fails_loudly_when_selected():
    """OPENWORKER_EXECUTOR=temporal without the extra refuses with the install hint."""
    out = _python("""
        import sys
        sys.modules["temporalio"] = None   # simulate the optional extra being absent
        try:
            import coworker.dispatch.temporal_executor  # noqa: F401
        except RuntimeError as exc:
            assert "openworker[temporal]" in str(exc), str(exc)
            print("refused loudly")
        else:
            raise SystemExit("imported without temporalio — the lazy guard is gone")
    """, env={"OPENWORKER_EXECUTOR": "temporal"})
    assert out.returncode == 0, out.stderr
    assert "refused loudly" in out.stdout


def test_selected_but_never_started_fails_closed():
    try:
        from coworker.dispatch import temporal_executor
    except RuntimeError:
        if _TEMPORAL_EXPECTED:
            pytest.fail("OPENWORKER_EXECUTOR=temporal is set but temporalio is not installed "
                        "— install the extra; this must never skip silently")
        pytest.skip("temporalio not installed (optional extra; env unset)")
    if temporal_executor._EXECUTOR is not None:
        pytest.skip("an executor is live in this process; fail-closed is for the cold path")
    with pytest.raises(RuntimeError):
        temporal_executor.current()


class _FakeFabric:
    """Just enough of the router's HTTP surface for frame()."""

    def __init__(self, cards, start=None):
        self.cards, self.start = cards, start or {"session_id": "run_fake1"}
        self.posted = []

    def get(self, path):
        assert path == "/api/capabilities"
        return {"capabilities": self.cards}

    def post(self, path, body):
        self.posted.append((path, body))
        assert path == "/api/runs"
        return self.start


def _router(fake):
    from coworker.dispatch.router import CapabilityRouter
    r = CapabilityRouter()
    r._get, r._post = fake.get, fake.post
    return r


def test_frame_opens_the_run_and_returns_the_pair():
    fake = _FakeFabric([{"id": "payor_um", "input_contract": ["request_id", "member_id"]}])
    assert _router(fake).frame({"request_id": "PA-2026-001", "member_id": "M1"}) == \
        ("run_fake1", "payor_um")
    assert fake.posted == [("/api/runs", {"agent_id": "payor_um", "interactive_signoff": True})]


def test_frame_returns_none_when_no_card_covers_the_item():
    fake = _FakeFabric([{"id": "payor_um", "input_contract": ["request_id"]}])
    assert _router(fake).frame({"unrelated": 1}) is None
    assert fake.posted == []


def test_frame_maps_transport_errors_to_fabric_refusal():
    import httpx

    from coworker.dispatch.router import CapabilityRouter, FabricRefusal
    r = CapabilityRouter(base="http://127.0.0.1:1")   # nothing listens here
    original = r._get

    def boom(path):
        raise httpx.ConnectError("refused")
    r._get = boom
    with pytest.raises(FabricRefusal) as exc:
        r.frame({"request_id": "PA-2026-001"})
    assert exc.value.retryable, "unreachable is retryable (it is not a 4xx refusal)"
    del original
