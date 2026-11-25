"""A3b — the harness's capability router: pure match, then the governed loop."""

import json
import os
import urllib.request

import httpx
import pytest

from coworker.dispatch import router as router_module
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


def _fabric_live() -> bool:
    """A live fabric and a configured identity: without one the harness refuses by design."""
    return _fabric_up() and all(os.environ.get(name, "").strip() for name in
                                ("REGAGENTIC_FABRIC_USERNAME", "REGAGENTIC_FABRIC_PASSWORD"))


@pytest.mark.skipif(not _fabric_live(), reason="no fabric at :8766 or no fabric credentials")
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


# --- OW-F-015: the declared view (view v1.0.0, fabric CONTRACTS.md §13) ----------------------

AGENT = "payor.demo.prior_auth"
RUN = "run-1"
ITEM = {"member_id": "MEM001", "procedure_code": "27447"}
PLAN = {"name": "prior_auth",
        "states": [{"name": "received"}, {"name": "denied"}],
        "transitions": [{"from": "received", "to": "denied", "signoff": "part11_single"}]}
VIEW = {"view": "1.0.0",
        "record": [{"component": "header", "title_field": "procedure_code",
                    "subtitle_field": "member_id"},
                   {"component": "gauge", "label": "Units against per-authorization limit",
                    "value_field": "requested_units", "max": 1}],
        "decision_labels": {"denied": "Not authorized"}}
VIEW_PATH = f"/api/agents/{AGENT}/view"


class StubFabric:
    """A fabric over httpx.MockTransport: canned contract reads, every request logged."""

    def __init__(self, view_response):
        self.view_response = view_response          # callable(request) -> httpx.Response
        self.calls: list[str] = []
        self.pursued = {"paused": True, "decision": "denied"}
        self.input_gates: list[dict] = []           # OW-F-018: the pending-input read's gates
        self.answer_response = None                 # callable(request) -> httpx.Response
        self.answer_bodies: list[dict] = []
        self.logins: list[dict] = []                # OW-F-019: every login body, as sent
        self.login_response = None                  # callable(request) -> httpx.Response

    def handle(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        self.calls.append(f"{request.method} {path}")
        if path == VIEW_PATH:
            return self.view_response(request)
        if path == "/api/auth/login":
            self.logins.append(json.loads(request.content))
            if self.login_response is not None:
                return self.login_response(request)
            return httpx.Response(200, json={"access_token": "t"})
        if path == "/api/capabilities":
            return httpx.Response(200, json={"capabilities": [
                {"id": AGENT, "input_contract": ["member_id", "procedure_code"]}]})
        if path == f"/api/agents/{AGENT}/plan":
            return httpx.Response(200, json=PLAN)
        if path == "/api/runs":
            return httpx.Response(200, json={"session_id": RUN})
        if path == f"/api/runs/{RUN}/pursue":
            return httpx.Response(200, json=self.pursued)
        if path == f"/api/runs/{RUN}/pending-signoff":
            return httpx.Response(200, json={"gates": []})
        if path == f"/api/runs/{RUN}/pending-input":
            return httpx.Response(200, json={"session_id": RUN, "gates": self.input_gates})
        if path == f"/api/runs/{RUN}/input":
            self.answer_bodies.append(json.loads(request.content))
            return self.answer_response(request)
        if path == f"/api/runs/{RUN}/receipt-digest":
            return httpx.Response(200, json={"recorded": True})
        if path == f"/api/runs/{RUN}/signoff":
            return httpx.Response(200, json={"session_id": RUN, "signed": True})
        if path == f"/api/runs/{RUN}/chain":
            return httpx.Response(200, json={"envelopes": []})
        if path == "/api/sessions":
            return httpx.Response(200, json={"sessions": []})
        return httpx.Response(404, json={"detail": "no such route"})

    def view_calls(self) -> int:
        return self.calls.count(f"GET {VIEW_PATH}")


FABRIC_USER, FABRIC_PASSWORD = "harness.operator", "configured-secret"


@pytest.fixture
def fabric(monkeypatch):
    monkeypatch.setenv("REGAGENTIC_FABRIC_USERNAME", FABRIC_USER)
    monkeypatch.setenv("REGAGENTIC_FABRIC_PASSWORD", FABRIC_PASSWORD)

    def install(view_response):
        stub = StubFabric(view_response)
        real_client = httpx.Client

        def client(*args, **kwargs):
            return real_client(*args, transport=httpx.MockTransport(stub.handle), **kwargs)

        monkeypatch.setattr(router_module.httpx, "Client", client)
        return stub
    return install


def _declared(request):
    return httpx.Response(200, json={"view_version": "1.0.0", "agent_id": AGENT,
                                     "declared": True, "view": VIEW})


def _undeclared(request):
    return httpx.Response(200, json={"view_version": "1.0.0", "agent_id": AGENT,
                                     "declared": False, "view": None})


def _older_fabric(request):
    return httpx.Response(404, json={"detail": "Not Found"})


def _unreachable(request):
    raise httpx.ConnectError("connection refused", request=request)


def _route():
    return CapabilityRouter(learn=False).route(dict(ITEM))


def _resume():
    return CapabilityRouter(learn=False).resume(RUN, dict(ITEM), agent=AGENT)


def test_dispatch_fetches_the_view_right_after_the_plan_and_carries_it(fabric):
    stub = fabric(_declared)
    result = _route()
    assert result["view"] == VIEW
    plan_at = stub.calls.index(f"GET /api/agents/{AGENT}/plan")
    assert stub.calls[plan_at + 1] == f"GET {VIEW_PATH}"


def test_resume_fetches_the_view_right_after_the_plan_and_carries_it(fabric):
    stub = fabric(_declared)
    result = _resume()
    assert result["view"] == VIEW
    plan_at = stub.calls.index(f"GET /api/agents/{AGENT}/plan")
    assert stub.calls[plan_at + 1] == f"GET {VIEW_PATH}"


@pytest.mark.parametrize("view_response", [_unreachable, _older_fabric, _undeclared],
                         ids=["unreachable", "older-fabric-404", "declared-false"])
@pytest.mark.parametrize("drive", [_route, _resume], ids=["dispatch", "resume"])
def test_no_view_stores_nothing_lets_the_run_proceed_and_is_not_retried(fabric, view_response,
                                                                         drive):
    stub = fabric(view_response)
    result = drive()
    assert "view" not in result
    assert result["framed"] is True
    assert result["decision"] == "denied"
    assert result["plan"]["signoff"] == "part11_single"
    assert stub.view_calls() == 1


def _finished(tmp_path, monkeypatch, result):
    from types import SimpleNamespace

    from coworker.server.manager import SessionManager

    manager = SessionManager(workspace=tmp_path)
    monkeypatch.setattr(manager, "deliver_receipt", lambda item_id: [])
    _, inbox_id = manager.channel_run_start(SimpleNamespace(channel="fhir", record=dict(ITEM)))
    manager.channel_run_finish(inbox_id, result, "ch_session")
    return manager, inbox_id


def _finished_item(tmp_path, monkeypatch, result):
    manager, inbox_id = _finished(tmp_path, monkeypatch, result)
    return manager.inbox.get(inbox_id).data


def test_a_declared_view_is_stored_on_the_work_item_payload(fabric, tmp_path, monkeypatch):
    fabric(_declared)
    data = _finished_item(tmp_path, monkeypatch, _route())
    assert data["view"] == VIEW


def test_no_view_leaves_the_work_item_payload_without_one(fabric, tmp_path, monkeypatch):
    fabric(_undeclared)
    data = _finished_item(tmp_path, monkeypatch, _route())
    assert "view" not in data


# --- OW-F-018: the parked run (input gate v1.0.0, fabric CONTRACTS.md §15) --------------------

# The pending-input read's one gate, exactly as Studio serves it (§15, bundle v1.1.0 `pending_input`).
GATE = {"from": "step_therapy", "to": "criteria",
        "fields": [{"name": "clinical_notes", "type": "str"},
                   {"name": "requested_units", "type": "int"}]}
PARKED = {"paused": True, "awaiting_input": True, "session_id": RUN,
          "detail": "awaiting input", "gates": [GATE]}


def _parked(stub):
    stub.pursued = PARKED
    stub.input_gates = [GATE]
    return stub


@pytest.mark.parametrize("drive", [_route, _resume], ids=["dispatch", "resume"])
def test_a_run_parked_on_input_mirrors_awaiting_input_beside_awaiting_signoff(fabric, drive):
    _parked(fabric(_undeclared))
    result = drive()
    assert result["awaiting_input"] is True
    assert result["pending_input"] == GATE
    assert result["awaiting_signoff"] is False
    assert result["gates"] == []
    assert result["decision"] is None


ANSWERS = {"clinical_notes": "Six weeks of physical therapy failed.", "requested_units": 1}


def _answered(request):
    return httpx.Response(200, json={"session_id": RUN, "answered": GATE, "paused": False,
                                     "decision": "approved", "final_state": "approved"})


def _idempotent(request):
    return httpx.Response(200, json={"session_id": RUN, "answered": GATE, "idempotent": True,
                                     "state": "approved"})


def _answer():
    return CapabilityRouter(learn=False).answer_input(RUN, dict(ANSWERS), agent=AGENT)


@pytest.mark.parametrize("answer_response", [_answered, _idempotent],
                         ids=["answered", "idempotent-repost"])
def test_answering_posts_the_answers_to_the_studio_input_endpoint_and_reads_the_next_stop(
        fabric, answer_response):
    stub = fabric(_undeclared)
    stub.answer_response = answer_response
    result = _answer()
    assert stub.answer_bodies == [{"answers": ANSWERS}]
    assert result["awaiting_input"] is False
    assert result["pending_input"] is None
    assert result["awaiting_signoff"] is False
    assert result["plan"]["signoff"] == "part11_single"


def test_answering_returns_another_input_gate_when_the_run_parks_again(fabric):
    stub = fabric(_undeclared)
    stub.input_gates = [GATE]
    stub.answer_response = lambda request: httpx.Response(200, json=PARKED)
    result = _answer()
    assert result["awaiting_input"] is True
    assert result["pending_input"] == GATE
    assert result["decision"] is None


def _refused(status, detail):
    return lambda request: httpx.Response(status, json={"detail": detail})


@pytest.mark.parametrize("status,detail", [
    (422, "answers refused, nothing sealed: field 'requested_units' must be int"),
    (409, "the gate already sealed different answers; the first answers stand"),
    (404, "unknown session"),
], ids=["mistyped-422", "different-repost-409", "unknown-404"])
def test_a_refused_answer_is_terminal_and_never_retried(fabric, status, detail):
    stub = fabric(_undeclared)
    stub.answer_response = _refused(status, detail)
    with pytest.raises(router_module.FabricRefusal) as refused:
        _answer()
    assert refused.value.status == status
    assert refused.value.detail == detail
    assert refused.value.retryable is False
    assert stub.calls.count(f"POST /api/runs/{RUN}/input") == 1


def test_a_run_parked_on_input_parks_the_work_item_beside_the_signoff_gate(fabric, tmp_path,
                                                                           monkeypatch):
    _parked(fabric(_undeclared))
    manager, inbox_id = _finished(tmp_path, monkeypatch, _route())
    data = manager.inbox.get(inbox_id).data
    assert manager.runs.get(inbox_id)["state"] == "gate", "parked, not sealed and not retried"
    assert data["awaiting_input"] is True
    assert data["pending_input"] == GATE
    assert data["awaiting_signoff"] is False
    assert data["running"] is False


@pytest.fixture
def parked_item(fabric, tmp_path, monkeypatch):
    """A sidecar holding one work item whose run is parked on GATE."""
    from fastapi.testclient import TestClient

    from coworker.server.app import create_app

    stub = _parked(fabric(_undeclared))
    manager, inbox_id = _finished(tmp_path, monkeypatch, _route())
    monkeypatch.setenv("COWORKER_API_TOKEN", "test-token")
    client = TestClient(create_app(manager))
    client.headers.update({"X-OpenWorker-Token": "test-token"})
    return stub, manager, inbox_id, client


def test_answering_a_parked_item_posts_through_the_dispatcher_and_flips_it_to_the_next_stop(
        parked_item):
    stub, manager, inbox_id, client = parked_item
    stub.input_gates = []
    stub.answer_response = _answered
    response = client.post(f"/v1/inbox/{inbox_id}/input", json={"answers": ANSWERS})
    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert stub.answer_bodies == [{"answers": ANSWERS}]
    data = manager.inbox.get(inbox_id).data
    assert data["awaiting_input"] is False
    assert data["pending_input"] is None
    assert data["decision"] == "approved"


def test_a_refused_answer_surfaces_the_detail_leaves_the_item_parked_and_is_not_retried(
        parked_item):
    stub, manager, inbox_id, client = parked_item
    detail = "answers refused, nothing sealed: field 'requested_units' must be int"
    stub.answer_response = _refused(422, detail)
    response = client.post(f"/v1/inbox/{inbox_id}/input", json={"answers": ANSWERS})
    assert response.status_code == 422
    assert response.json()["detail"] == detail
    assert stub.calls.count(f"POST /api/runs/{RUN}/input") == 1
    data = manager.inbox.get(inbox_id).data
    assert data["awaiting_input"] is True
    assert data["pending_input"] == GATE
    assert manager.runs.get(inbox_id)["state"] == "gate"


def test_another_tenants_key_gets_404_and_fabric_is_never_called(parked_item):
    stub, manager, inbox_id, client = parked_item
    stub.answer_response = _answered
    manager.stamp_tenant(inbox_id, "acme")
    other, _ = manager.keys.mint("globex", "tenant agent")
    response = client.post(f"/v1/inbox/{inbox_id}/input", json={"answers": ANSWERS},
                           headers={"X-OpenWorker-Token": other})
    assert response.status_code == 404
    assert f"POST /api/runs/{RUN}/input" not in stub.calls
    data = manager.inbox.get(inbox_id).data
    assert data["awaiting_input"] is True
    assert data["pending_input"] == GATE


def test_the_answering_actor_is_recorded_on_the_item_and_the_answers_are_not(parked_item):
    stub, manager, inbox_id, client = parked_item
    stub.input_gates = []
    stub.answer_response = _answered
    response = client.post(f"/v1/inbox/{inbox_id}/input", json={"answers": ANSWERS},
                           headers={"x-openworker-actor": "dr.reviewer"})
    assert response.status_code == 200
    data = manager.inbox.get(inbox_id).data
    assert [a["actor"] for a in data["input_answered_by"]] == ["dr.reviewer"]
    assert set(data["input_answered_by"][0]) == {"actor", "at"}
    assert ANSWERS["clinical_notes"] not in json.dumps(data)


def test_a_refused_answer_records_no_answering_actor(parked_item):
    stub, manager, inbox_id, client = parked_item
    stub.answer_response = _refused(422, "answers refused, nothing sealed")
    client.post(f"/v1/inbox/{inbox_id}/input", json={"answers": ANSWERS},
                headers={"x-openworker-actor": "dr.reviewer"})
    assert "input_answered_by" not in manager.inbox.get(inbox_id).data


@pytest.fixture
def temporal_item(fabric, tmp_path, monkeypatch):
    """The Temporal executor's activities over one framed work item (no Temporal server)."""
    from types import SimpleNamespace

    temporal_executor = pytest.importorskip("coworker.dispatch.temporal_executor")
    from coworker.server.manager import SessionManager

    stub = fabric(_undeclared)
    manager = SessionManager(workspace=tmp_path)
    monkeypatch.setattr(manager, "deliver_receipt", lambda item_id: [])
    _, inbox_id = manager.channel_run_start(SimpleNamespace(channel="fhir", record=dict(ITEM)))
    manager.stamp_tenant(inbox_id, "acme")
    manager.channel_set_run(inbox_id, RUN, AGENT)
    activities = temporal_executor._Activities(manager)
    return stub, manager, inbox_id, activities


def test_the_durable_execute_stage_mirrors_a_run_parked_on_input(temporal_item):
    stub, manager, inbox_id, activities = temporal_item
    _parked(stub)
    result = activities.governed.run("ow.execute_work_item", inbox_id, "acme")
    assert result["awaiting_input"] is True
    assert result["awaiting_signoff"] is False
    assert "fabric_anchor" not in result, "a parked run is not terminal: nothing to anchor"
    assert "pending_input" not in result, "the gate's fields never enter the dispatch chain"
    assert manager.inbox.get(inbox_id).data["pending_input"] == GATE


def test_the_durable_input_check_reads_the_items_next_stop(temporal_item, tmp_path, monkeypatch):
    stub, manager, inbox_id, activities = temporal_item
    _parked(stub)
    activities.governed.run("ow.execute_work_item", inbox_id, "acme")
    assert activities.check_input(inbox_id)["awaiting_input"] is True
    stub.input_gates = []
    stub.answer_response = _answered
    manager.answer_channel_input(inbox_id, dict(ANSWERS))
    state = activities.check_input(inbox_id)
    assert state["awaiting_input"] is False
    assert state["awaiting_signoff"] is False
    assert state["decision"] == "approved"


# --- OW-F-019: the fabric identity comes from configuration, fail closed -----------------------

def test_login_uses_the_configured_fabric_identity(fabric):
    stub = fabric(_undeclared)
    _route()
    assert stub.logins == [{"username": FABRIC_USER, "password": FABRIC_PASSWORD}]


MISSING = pytest.mark.parametrize("unset", [
    {"REGAGENTIC_FABRIC_USERNAME": None},
    {"REGAGENTIC_FABRIC_PASSWORD": None},
    {"REGAGENTIC_FABRIC_USERNAME": "", "REGAGENTIC_FABRIC_PASSWORD": "  "},
], ids=["username-missing", "password-missing", "both-empty"])


def _configure(monkeypatch, unset):
    for name, value in unset.items():
        if value is None:
            monkeypatch.delenv(name)
        else:
            monkeypatch.setenv(name, value)


@MISSING
def test_missing_fabric_credentials_refuse_dispatch(fabric, monkeypatch, unset):
    stub = fabric(_undeclared)
    _configure(monkeypatch, unset)
    with pytest.raises(router_module.FabricRefusal) as refused:
        _route()
    assert "REGAGENTIC_FABRIC_USERNAME" in refused.value.detail
    assert "REGAGENTIC_FABRIC_PASSWORD" in refused.value.detail
    assert stub.calls == []


@pytest.fixture
def signoff_item(fabric, tmp_path, monkeypatch):
    """A sidecar holding one work item whose run is parked at the signoff gate."""
    stub = fabric(_undeclared)
    manager, inbox_id = _finished(tmp_path, monkeypatch, _route())
    stub.calls.clear()
    stub.logins.clear()
    return stub, manager, inbox_id


def test_signing_logs_in_with_the_configured_fabric_identity(signoff_item):
    stub, manager, inbox_id = signoff_item
    manager.sign_channel_item(manager.inbox.get(inbox_id).session_id)
    assert stub.logins == [{"username": FABRIC_USER, "password": FABRIC_PASSWORD}]
    assert f"POST /api/runs/{RUN}/signoff" in stub.calls


@MISSING
def test_missing_fabric_credentials_refuse_signing(signoff_item, monkeypatch, unset):
    from coworker.receipts import SIGNED_BODY_KEY

    stub, manager, inbox_id = signoff_item
    _configure(monkeypatch, unset)
    with pytest.raises(router_module.FabricRefusal):
        manager.sign_channel_item(manager.inbox.get(inbox_id).session_id)
    assert stub.calls == []
    data = manager.inbox.get(inbox_id).data
    assert SIGNED_BODY_KEY not in data
    assert "receipt_digest_recorded" not in data


SENTINEL = "sentinel-password-4f9c"


def test_credential_values_never_leak(fabric, monkeypatch, caplog):
    import logging

    caplog.set_level(logging.DEBUG)
    stub = fabric(_undeclared)
    monkeypatch.setenv("REGAGENTIC_FABRIC_PASSWORD", SENTINEL)
    monkeypatch.delenv("REGAGENTIC_FABRIC_USERNAME")
    with pytest.raises(router_module.FabricRefusal) as missing:
        CapabilityRouter(learn=False).frame(dict(ITEM))
    monkeypatch.setenv("REGAGENTIC_FABRIC_USERNAME", FABRIC_USER)
    stub.login_response = _refused(401, "invalid username or password")
    with pytest.raises(router_module.FabricRefusal) as rejected:
        CapabilityRouter(learn=False).frame(dict(ITEM))
    assert rejected.value.status == 401
    assert stub.logins == [{"username": FABRIC_USER, "password": SENTINEL}], "the 401 path ran"
    assert SENTINEL not in missing.value.detail
    assert SENTINEL not in rejected.value.detail
    assert caplog.records, "the stubbed fabric calls were logged"
    assert all(SENTINEL not in record.getMessage() for record in caplog.records)
