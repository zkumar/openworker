"""F-010 — a connector event becomes at most one work item, and only when it carries a record."""

from types import SimpleNamespace

from coworker.channels.connector_bridge import ConnectorBridge, record_from_event


def _event(raw, message_id="m1"):
    return SimpleNamespace(raw=raw, message_id=message_id)


def test_a_record_becomes_a_work_item():
    item = record_from_event("slack", _event({"record": {"request_id": "PA-2026-001"}}))
    assert item is not None
    assert item.channel == "slack"
    assert item.record["request_id"] == "PA-2026-001"
    assert item.meta["message_id"] == "m1"


def test_a_bare_text_message_carries_no_work():
    assert record_from_event("slack", _event({"text": "hello"})) is None
    assert record_from_event("slack", _event("just a string")) is None
    assert record_from_event("slack", _event(None)) is None


def test_a_record_without_an_identifier_is_not_work():
    assert record_from_event("slack", _event({"record": {"member_id": "MEM1"}})) is None


def test_the_same_message_delivers_one_work_item():
    got = []
    bridge = ConnectorBridge(SimpleNamespace(platform="slack"), got.append)
    ev = _event({"record": {"request_id": "PA-1"}}, message_id="m-42")
    import asyncio
    asyncio.run(bridge(ev))
    asyncio.run(bridge(ev))          # redelivery
    assert len(got) == 1


def test_two_different_messages_both_deliver():
    got = []
    bridge = ConnectorBridge(SimpleNamespace(platform="slack"), got.append)
    import asyncio
    asyncio.run(bridge(_event({"record": {"request_id": "PA-1"}}, message_id="a")))
    asyncio.run(bridge(_event({"record": {"request_id": "PA-2"}}, message_id="b")))
    assert [i.record["request_id"] for i in got] == ["PA-1", "PA-2"]


def test_a_message_without_an_id_is_still_delivered_once():
    got = []
    bridge = ConnectorBridge(SimpleNamespace(platform="slack"), got.append)
    import asyncio
    asyncio.run(bridge(_event({"record": {"request_id": "PA-1"}}, message_id=None)))
    assert len(got) == 1
