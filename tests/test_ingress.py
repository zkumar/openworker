"""Durable ingress: accepted work survives, offline work is drained, nothing runs twice."""

import json
import pathlib

from coworker.channels.spool import FileSpool
from coworker.ingress import MAX_ATTEMPTS, IngressQueue


def test_an_accepted_record_is_durable_immediately(tmp_path):
    q = IngressQueue(pathlib.Path(tmp_path) / "i.sqlite")
    eid = q.enqueue("webhook", {"record": {"request_id": "PA-2026-001"}})
    assert q.get(eid)["state"] == "pending"
    assert [e["id"] for e in q.due()] == [eid], "an accepted record must be dispatchable"


def test_a_claimed_record_is_not_handed_out_again(tmp_path):
    """Double dispatch would run one record twice."""
    q = IngressQueue(pathlib.Path(tmp_path) / "i.sqlite")
    eid = q.enqueue("webhook", {"record": {}})
    q.mark_dispatched(eid, "ch_1")
    assert q.due() == [], "a dispatched record must leave the queue"


def test_a_transient_failure_backs_off_then_gives_up(tmp_path):
    q = IngressQueue(pathlib.Path(tmp_path) / "i.sqlite")
    eid = q.enqueue("webhook", {"record": {}})
    for _ in range(MAX_ATTEMPTS - 1):
        assert q.mark_failed(eid, "fabric down") == "pending"
        assert q.due() == [], "a retry waits for its backoff window"
    assert q.mark_failed(eid, "fabric down") == "failed"
    assert q.stats().get("failed") == 1


def test_the_spool_survives_a_missing_directory(tmp_path):
    assert FileSpool(pathlib.Path(tmp_path) / "nope").poll() == []


def test_spooled_files_are_read_once_and_moved(tmp_path):
    spool = FileSpool(tmp_path)
    d = pathlib.Path(tmp_path) / "webhook"
    d.mkdir()
    (d / "PA-1.json").write_text(json.dumps({"record": {"request_id": "PA-1"}}))

    found = spool.poll()
    assert [c for c, _, _ in found] == ["webhook"]
    assert found[0][1]["record"]["request_id"] == "PA-1"

    spool.done(found[0][2])
    assert spool.poll() == [], "a processed file must not be picked up again"
    assert (pathlib.Path(tmp_path) / "processed" / "PA-1.json").is_file()


def test_a_malformed_file_does_not_block_the_queue(tmp_path):
    spool = FileSpool(tmp_path)
    d = pathlib.Path(tmp_path) / "webhook"
    d.mkdir()
    (d / "broken.json").write_text("{ not json")
    (d / "PA-2.json").write_text(json.dumps({"record": {"request_id": "PA-2"}}))

    found = spool.poll()
    assert [f.name for _, _, f in found] == ["PA-2.json"], "the good record still gets ingested"
    assert (pathlib.Path(tmp_path) / "failed" / "broken.json").is_file()
