"""A4 — channels are pluggable: add two, ingest, remove one, the rest keep working."""

import pytest

from coworker.channels import base, registry
from coworker.channels.webhook import WebhookChannel


@pytest.fixture(autouse=True)
def _clean():
    registry._CHANNELS.clear()
    yield
    registry._CHANNELS.clear()


def test_add_and_remove_channels_without_touching_code():
    registry.register(WebhookChannel("webhook"))
    registry.register(WebhookChannel("email"))

    assert registry.names() == ["email", "webhook"]

    item = registry.ingest("webhook", {"record": {"member_id": "M1", "procedure_code": "P1"}})
    assert item is not None
    assert item.channel == "webhook"
    assert item.record == {"member_id": "M1", "procedure_code": "P1"}

    assert registry.unregister("webhook") is True
    assert registry.names() == ["email"]          # the remaining channel is untouched
    with pytest.raises(KeyError):
        registry.ingest("webhook", {"record": {"a": 1}})


def test_the_payload_itself_can_be_the_record():
    channel = WebhookChannel("kafka")
    item = channel.ingest({"device_name": "Infusion Pump", "severity": "major"})
    assert item is not None and item.channel == "kafka"
    assert item.record["device_name"] == "Infusion Pump"
    assert item.received_at                            # stamped by the channel, not the caller


def test_an_empty_payload_carries_no_work():
    assert WebhookChannel().ingest({}) is None
