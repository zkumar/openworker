"""OW-F-014 A5 — rfsdk is opt-in exactly like temporalio: with OPENWORKER_EXECUTOR unset,
neither rfsdk_kernel nor the adapters package is ever imported, and with the executor
selected but rfsdk-kernel missing, the import refuses loudly with the install hint
(never a silent thread fallback). Same proof shape as tests/test_temporal_optin.py."""
from __future__ import annotations

import os
import subprocess
import sys
import textwrap

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _python(code: str, env: dict | None = None) -> subprocess.CompletedProcess:
    full_env = {**os.environ, **(env or {})}
    full_env.pop("OPENWORKER_EXECUTOR", None)
    if env and "OPENWORKER_EXECUTOR" in env:
        full_env["OPENWORKER_EXECUTOR"] = env["OPENWORKER_EXECUTOR"]
    return subprocess.run([sys.executable, "-c", textwrap.dedent(code)],
                          capture_output=True, text=True, cwd=REPO, env=full_env, timeout=120)


def test_env_unset_means_no_rfsdk_import():
    out = _python("""
        import sys
        import coworker.server.app as app
        import coworker.dispatch

        assert not app._temporal_selected()
        assert "rfsdk_kernel" not in sys.modules, "rfsdk_kernel was imported with the env unset"
        assert "coworker.rfsdk_adapters" not in sys.modules
        print("clean")
    """)
    assert out.returncode == 0, out.stderr
    assert "clean" in out.stdout


def test_missing_rfsdk_fails_loudly_when_selected():
    out = _python("""
        import sys
        sys.modules["rfsdk_kernel"] = None   # simulate the dependency being absent
        try:
            import coworker.dispatch.temporal_executor  # noqa: F401
        except RuntimeError as exc:
            assert "rfsdk-kernel" in str(exc), str(exc)
            assert "agentic-native-port" in str(exc), str(exc)
            print("refused loudly")
        else:
            raise SystemExit("imported without rfsdk_kernel — the fail-closed guard is gone")
    """, env={"OPENWORKER_EXECUTOR": "temporal"})
    assert out.returncode == 0, out.stderr
    assert "refused loudly" in out.stdout
