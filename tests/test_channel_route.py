"""A3b wiring — a channel POST becomes a governed run and a lesson."""

import urllib.request

import pytest
from fastapi.testclient import TestClient

from coworker.server.app import create_app
from coworker.server.manager import SessionManager


def _fabric_up() -> bool:
    try:
        urllib.request.urlopen("http://127.0.0.1:8766/api/config", timeout=2)
        return True
    except Exception:
        return False


@pytest.fixture()
def client(tmp_path):
    return TestClient(create_app(SessionManager(data_dir=tmp_path / "data")))


def test_unknown_channel_is_not_found(client):
    assert client.post("/v1/channels/nope", json={"record": {"a": 1}}).status_code == 404


def test_empty_payload_carries_no_work(client):
    body = client.post("/v1/channels/webhook", json={}).json()
    assert body["ok"] is False


@pytest.mark.skipif(not _fabric_up(), reason="no fabric at :8766")
def test_webhook_record_is_dispatched_and_sealed(client):
    response = client.post("/v1/channels/webhook", json={"record": {
        "member_id": "MEM001", "procedure_code": "27447", "provider_npi": "1234567890",
        "request_date": "2026-01-15", "requested_service_date": "2026-02-15",
        "requested_units": 1,
        "clinical_notes": "45yo male, severe right knee OA, conservative care failed.",
    }})
    body = response.json()
    assert body["ok"] is True and body["channel"] == "webhook"
    assert body["result"]["agent"] == "payor.demo.prior_auth"
    assert body["result"]["decision"] == "denied"
    assert body["result"]["envelopes"] >= 4
