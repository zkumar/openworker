"""OW-F-014 — the SQLite rfsdk port adapters and the governed dispatch layer.

A2: each adapter passes rfsdk's OWN port contract suite (rfsdk_kernel.testing.contracts),
    subclassed here with the adapter fixtures the suites name.
A3: a null chain_head, verified false, or a fabric refusal refuses the anchor
    (anchor_unavailable) — an anchor is read, never fabricated.
A4: tenant isolation at the dispatch boundary — a cross-tenant call is denied AND the
    refusal itself is sealed on the caller's chain.
Plus the governed round trip: one dispatch seals exactly one verifiable envelope, and the
sign stage seals the fabric anchor into its envelope result.

The live joined-run criterion (A1) is driven against a real fabric + Temporal dev server
and recorded in factory/GATES.md, like OW-F-013's kill -9 proof.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

pytest.importorskip("rfsdk_kernel", reason="rfsdk-kernel not installed (temporal extra)")

from pydantic import BaseModel  # noqa: E402
from rfsdk_kernel.errors import ActionContractError  # noqa: E402
from rfsdk_kernel.registry import ActionSpec  # noqa: E402
from rfsdk_kernel.testing.contracts import (  # noqa: E402
    ORG,
    OTHER_ORG,
    ApprovalStoreContract,
    ChangeBusContract,
    EvidenceStoreContract,
    PolicyContract,
    make_caller,
)

from coworker.rfsdk_adapters import (  # noqa: E402
    ANCHOR_UNAVAILABLE,
    GovernedDispatch,
    SqliteApprovalStore,
    SqliteChangeBus,
    SqliteEvidenceStore,
    TenantPolicy,
    read_fabric_anchor,
)
from coworker.rfsdk_adapters import governed as governed_module  # noqa: E402

HEAD = "a" * 64


@pytest.fixture()
def db(tmp_path):
    return tmp_path / "rfsdk.db"


# --- A2: rfsdk's own port contract suites ---------------------------------------------------------

class TestEvidenceStoreContract(EvidenceStoreContract):
    @pytest.fixture()
    def adapter(self, db):
        return SqliteEvidenceStore(db)

    @pytest.fixture()
    def tamper(self, db):
        async def flip(chain: str, envelope_hash: str) -> None:
            con = sqlite3.connect(db)
            (body,) = con.execute(
                "SELECT body FROM rfsdk_evidence WHERE chain=? AND hash=?",
                (chain, envelope_hash)).fetchone()
            content = json.loads(body)
            content["action"] = content["action"] + "x"      # one byte behind the adapter's back
            con.execute("UPDATE rfsdk_evidence SET body=? WHERE chain=? AND hash=?",
                        (json.dumps(content), chain, envelope_hash))
            con.commit()
            con.close()
        return flip


class TestApprovalStoreContract(ApprovalStoreContract):
    @pytest.fixture()
    def adapter(self, db):
        return SqliteApprovalStore(db)


class TestChangeBusContract(ChangeBusContract):
    @pytest.fixture()
    def adapter(self, db):
        return SqliteChangeBus(db)


class _In(BaseModel):
    tenant: str


class _Out(BaseModel):
    ok: bool


def _spec() -> ActionSpec:
    async def run(args):
        return _Out(ok=True)
    return ActionSpec(name="contract-probe", description="policy contract probe",
                      input_schema=_In, output_schema=_Out, run=run)


class TestPolicyContract(PolicyContract):
    @pytest.fixture()
    def adapter(self):
        return TenantPolicy()

    @pytest.fixture()
    def allowed_call(self):
        return (_spec(), make_caller("contract-caller", ORG), {"tenant": ORG})

    @pytest.fixture()
    def denied_call(self):
        return (_spec(), make_caller("contract-caller", ORG), {"tenant": OTHER_ORG})


# --- A3: the anchor is read, never fabricated -----------------------------------------------------

def _patch_chain(monkeypatch, response):
    from coworker.dispatch.router import CapabilityRouter
    monkeypatch.setattr(CapabilityRouter, "chain", lambda self, sid: response)


def test_anchor_requires_a_verified_chain(monkeypatch):
    _patch_chain(monkeypatch, {"verified": False, "count": 3, "chain_head": HEAD})
    with pytest.raises(ActionContractError) as refused:
        read_fabric_anchor("run_x")
    assert refused.value.error_code == ANCHOR_UNAVAILABLE


def test_anchor_requires_a_non_null_head(monkeypatch):
    _patch_chain(monkeypatch, {"verified": True, "count": 0, "chain_head": None})
    with pytest.raises(ActionContractError) as refused:
        read_fabric_anchor("run_x")
    assert refused.value.error_code == ANCHOR_UNAVAILABLE


def test_anchor_maps_a_fabric_refusal(monkeypatch):
    from coworker.dispatch.router import CapabilityRouter, FabricRefusal

    def refuse(self, sid):
        raise FabricRefusal("unknown session", 404)
    monkeypatch.setattr(CapabilityRouter, "chain", refuse)
    with pytest.raises(ActionContractError) as refused:
        read_fabric_anchor("run_x")
    assert refused.value.error_code == ANCHOR_UNAVAILABLE
    assert refused.value.status_code == 404


def test_anchor_returns_the_sealed_pair(monkeypatch):
    _patch_chain(monkeypatch, {"verified": True, "count": 5, "chain_head": HEAD})
    assert read_fabric_anchor("run_x") == {"session_id": "run_x", "chain_head": HEAD}


# --- the governed round trip (and A4 at the dispatch boundary) ------------------------------------

class _FakeRuns:
    def __init__(self, row):
        self._row = row

    def get(self, inbox_id):
        return self._row


class _FakeInbox:
    def __init__(self, data):
        self._item = SimpleNamespace(data=data)

    def get(self, inbox_id):
        return self._item


class _FakeManager:
    def __init__(self, row):
        self.runs = _FakeRuns(row)
        self.inbox = _FakeInbox({})       # OW-F-015: no declared view stored


class _FakeActivities:
    """Just enough of _Activities for the handlers: raw bodies returning phase 1 shapes."""

    def __init__(self):
        self.manager = _FakeManager({"fabric_run": "run_fake", "agent": "payor_um"})
        self.calls = []

    def frame_work_item(self, inbox_id):
        self.calls.append(("frame", inbox_id))
        return {"framed": True, "fabric_run": "run_fake", "agent": "payor_um"}

    def sign_work_item(self, inbox_id, approver):
        self.calls.append(("sign", inbox_id, approver))
        return {"decision": "approved"}


@pytest.fixture()
def dispatch(tmp_path):
    return GovernedDispatch(_FakeActivities(), tmp_path)


def test_one_dispatch_seals_one_verifiable_envelope(dispatch):
    out = dispatch.run("ow.frame_work_item", "itm-1", "humana.centerwell")
    assert out["framed"] is True

    import asyncio
    report = asyncio.run(dispatch.evidence.verify("humana.centerwell"))
    assert (report.ok, report.length) == (True, 1)
    (envelope,) = dispatch.evidence.chain_envelopes("humana.centerwell")
    assert (envelope["action"], envelope["outcome"]) == ("ow.frame_work_item", "ok")
    assert envelope["caller"]["org_id"] == "humana.centerwell"


def test_the_sign_stage_seals_the_fabric_anchor(dispatch, monkeypatch):
    monkeypatch.setattr(governed_module, "read_fabric_anchor",
                        lambda run: {"session_id": run, "chain_head": HEAD})
    out = dispatch.run("ow.sign_work_item", "itm-1", "humana.centerwell", approver="vijay")
    assert out["fabric_anchor"] == {"session_id": "run_fake", "chain_head": HEAD}

    final = dispatch.evidence.chain_envelopes("humana.centerwell")[-1]
    assert final["result"]["fabric_anchor"]["chain_head"] == HEAD, \
        "the fabric head is sealed INSIDE the rfsdk envelope (anchor as data)"


def test_a_cross_tenant_call_is_denied_and_the_refusal_sealed(dispatch):
    import asyncio

    from coworker.rfsdk_adapters.governed import dispatch_caller
    caller = dispatch_caller("humana.centerwell", "itm-1")
    with pytest.raises(ActionContractError) as refused:
        asyncio.run(dispatch.dispatcher.dispatch(
            "ow.frame_work_item", {"inbox_id": "itm-1", "tenant": "caqh.cob"}, caller))
    assert refused.value.status_code == 403

    (envelope,) = dispatch.evidence.chain_envelopes("humana.centerwell")
    assert envelope["outcome"] == "refused", "the denial itself is evidence"


def test_an_anchorless_terminal_execute_refuses(dispatch, monkeypatch):
    """A terminal run whose head cannot be read refuses the stage; the refusal is sealed."""
    def unavailable(run):
        raise ActionContractError("no attestable head", error_code=ANCHOR_UNAVAILABLE,
                                  status_code=409)
    monkeypatch.setattr(governed_module, "read_fabric_anchor", unavailable)

    class _TerminalActivities(_FakeActivities):
        def execute_work_item(self, inbox_id):
            return {"framed": True, "awaiting_signoff": False, "decision": "denied",
                    "fabric_run": "run_fake", "agent": "payor_um"}

    d = GovernedDispatch(_TerminalActivities(), dispatch.evidence.path + "-2")
    with pytest.raises(ActionContractError) as refused:
        d.run("ow.execute_work_item", "itm-9", "humana.centerwell")
    assert refused.value.error_code == ANCHOR_UNAVAILABLE
    final = d.evidence.chain_envelopes("humana.centerwell")[-1]
    assert final["outcome"] == "error"
    assert final["error_code"] == ANCHOR_UNAVAILABLE


# --- OW-F-015: the run-completing envelope seals view_sha256 --------------------------------------

# A declared view as stored on the work item, keys deliberately out of order, one non-ASCII char.
STORED_VIEW = {"title": "Units ≤ limit", "components": [{"type": "gauge", "max": 1}]}
# sha-256 of its canonical JSON (sorted keys, compact separators, UTF-8), computed by hand:
#   printf '%s' '{"components":[{"max":1,"type":"gauge"}],"title":"Units ≤ limit"}' | shasum -a 256
STORED_VIEW_SHA256 = "301d3dfdef1fdbf65d40ba20a62da5ff47ac9b8098eeb5bfa1c80ce2a2e4e80c"


class _CompletingActivities(_FakeActivities):
    """A work item whose execute stage reaches the terminal state (or the gate, if gated)."""

    def __init__(self, stored: dict, gated: bool = False):
        super().__init__()
        self.manager.inbox = _FakeInbox(stored)
        self.gated = gated

    def execute_work_item(self, inbox_id):
        return {"framed": True, "awaiting_signoff": self.gated,
                "decision": None if self.gated else "approved",
                "fabric_run": "run_fake", "agent": "payor_um"}


@pytest.mark.parametrize("stage, extra", [("ow.execute_work_item", {}),
                                          ("ow.sign_work_item", {"approver": "vijay"})])
@pytest.mark.parametrize("stored, expected", [({"view": STORED_VIEW}, STORED_VIEW_SHA256),
                                              ({}, None)])
def test_the_run_completing_envelope_seals_view_sha256(tmp_path, monkeypatch, stage, extra,
                                                       stored, expected):
    """The hash of the stored declared view rides the envelope beside the fabric anchor;
    null when no view was stored (adr-view-sha256-seals-declared)."""
    monkeypatch.setattr(governed_module, "read_fabric_anchor",
                        lambda run: {"session_id": run, "chain_head": HEAD})
    d = GovernedDispatch(_CompletingActivities(stored), tmp_path)
    out = d.run(stage, "itm-1", "humana.centerwell", **extra)
    assert "view_sha256" in out and out["view_sha256"] == expected

    final = d.evidence.chain_envelopes("humana.centerwell")[-1]
    assert final["action"] == stage
    assert final["result"]["view_sha256"] == expected, "sealed INSIDE the rfsdk envelope"
    assert final["result"]["fabric_anchor"]["chain_head"] == HEAD


def test_a_gated_execute_seals_no_view_sha256(tmp_path):
    """Only the run-completing envelope carries the hash, like the fabric anchor."""
    d = GovernedDispatch(_CompletingActivities({"view": STORED_VIEW}, gated=True), tmp_path)
    out = d.run("ow.execute_work_item", "itm-1", "humana.centerwell")
    assert "view_sha256" not in out and "fabric_anchor" not in out


def test_caller_json_round_trips_for_approvals(db):
    """The stored requester compares equal after SQLite round trip (dataclass equality)."""
    import asyncio
    from datetime import timedelta

    store = SqliteApprovalStore(db)
    requester = make_caller("round-trip", ORG, authenticated_at=datetime.now(UTC))
    pending = asyncio.run(store.request("k", "a", requester, timedelta(hours=1)))
    assert pending.requester == requester
    approved = asyncio.run(store.consume("k", make_caller("other", ORG)))
    assert approved.requester == requester
