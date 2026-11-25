"""A3b — the harness's capability router: pure match, then the governed loop."""

import json
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

    def handle(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        self.calls.append(f"{request.method} {path}")
        if path == VIEW_PATH:
            return self.view_response(request)
        if path == "/api/auth/login":
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
        if path == f"/api/runs/{RUN}/chain":
            return httpx.Response(200, json={"envelopes": []})
        if path == "/api/sessions":
            return httpx.Response(200, json={"sessions": []})
        return httpx.Response(404, json={"detail": "no such route"})

    def view_calls(self) -> int:
        return self.calls.count(f"GET {VIEW_PATH}")


@pytest.fixture
def fabric(monkeypatch):
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


def _finished_item(tmp_path, monkeypatch, result):
    from types import SimpleNamespace

    from coworker.server.manager import SessionManager

    manager = SessionManager(workspace=tmp_path)
    monkeypatch.setattr(manager, "deliver_receipt", lambda item_id: [])
    _, inbox_id = manager.channel_run_start(SimpleNamespace(channel="fhir", record=dict(ITEM)))
    manager.channel_run_finish(inbox_id, result, "ch_session")
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
