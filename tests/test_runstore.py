"""The durable run journal: fencing, backoff, and terminal failure."""

import pathlib

from coworker.server.runstore import MAX_ATTEMPTS, RunStore


def _store(tmp_path) -> RunStore:
    return RunStore(pathlib.Path(tmp_path) / "runs.sqlite")


def test_a_fresh_run_is_due_and_claimable_once(tmp_path):
    s = _store(tmp_path)
    gen = s.begin("k", "ch_1", {"request_id": "PA-1"})
    assert [r["run_key"] for r in s.due()] == ["k"]
    assert s.claim("k", gen) == gen + 1
    assert s.claim("k", gen) is None, "a stale owner must be fenced out"


def test_a_failure_backs_off_then_gives_up(tmp_path):
    s = _store(tmp_path)
    s.begin("k", "ch_1", {})
    for attempt in range(1, MAX_ATTEMPTS):
        assert s.fail("k", "boom") == "dispatched"
        row = s.get("k")
        assert row["attempts"] == attempt
        assert row["due"] > 0, "a retry waits for its backoff window"
    assert s.fail("k", "boom") == "failed"
    assert s.get("k")["state"] == "failed"
    assert s.due() == [], "a failed run is never picked up again"


def test_finishing_removes_it_from_the_queue(tmp_path):
    s = _store(tmp_path)
    s.begin("k", "ch_1", {})
    s.finish("k", "gate")
    assert s.get("k")["state"] == "gate"
    assert s.due() == [], "a gated run waits for a human, not a retry"
