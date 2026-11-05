"""A3b — the harness's capability router: pure match, then the governed loop."""

import urllib.request

import pytest

from coworker.dispatch.router import CapabilityRouter

CARDS = [
    {"id": "payor.demo.prior_auth", "input_contract": ["member_id", "procedure_code"]},
    {"id": "medtech.demo.capa", "input_contract": ["device_name", "severity"]},
]


def test_pick_matches_by_declared_contract_only():
    router = CapabilityRouter(learn=False)
    assert router.pick(CARDS, {"member_id": "M", "procedure_code": "P"})["id"] == "payor.demo.prior_auth"
    assert router.pick(CARDS, {"device_name": "Pump", "severity": "major"})["id"] == "medtech.demo.capa"
    assert router.pick(CARDS, {"mystery": "X"}) is None


def _fabric_up() -> bool:
    try:
        urllib.request.urlopen("http://127.0.0.1:8766/api/config", timeout=2)
        return True
    except Exception:
        return False


@pytest.mark.skipif(not _fabric_up(), reason="no fabric at :8766")
def test_route_executes_the_governed_run_and_seals():
    result = CapabilityRouter(learn=False).route({
        "request_id": "PA-2026-001",
        "member_id": "MEM001", "procedure_code": "27447", "provider_npi": "1234567890",
        "request_date": "2026-01-15", "requested_service_date": "2026-02-15",
        "requested_units": 1,
        "clinical_notes": "45yo male, severe right knee OA, conservative care failed.",
    })
    assert result["agent"] == "payor.demo.prior_auth"
    assert result["decision"] == "denied"
    assert result["awaiting_signoff"] is True, "a gated agent must pause for a human"
    assert result["gates"][0]["signoff"] == "part11_single"
