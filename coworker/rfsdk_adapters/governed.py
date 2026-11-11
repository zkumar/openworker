"""The governed dispatch layer: Temporal activities routed through rfsdk (OW-F-014).

Every dispatch stage is a registered rfsdk action (needs_approval=False: the fabric part11
signoff stays the ONLY human gate) whose handler wraps the existing activity body unchanged.
`Dispatcher.dispatch` seals exactly one hash-chained SealedEnvelope per outcome into the
tenant's chain, and the stage that observes the fabric run terminal seals fabric's full
chain head as data (dispatch-anchor contract v1.0.0, fabric RFC 0054, CONTRACTS.md section
12): the rfsdk chain is the outer authority and fabric's chain is a sub-chain referenced by
hash. Fail closed: a null chain_head or verified false refuses the stage
(error_code "anchor_unavailable"); an anchor is read, never fabricated.

OW-F-015: beside the anchor, the same run-completing envelope seals view_sha256, the hash of
the declared view stored on the work item (null when none): it proves which presentation
contract was in force, not whether the GUI rendered it (adr-view-sha256-seals-declared).

Imported only on the OPENWORKER_EXECUTOR=temporal path, like temporalio itself.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict
from rfsdk_kernel.caller import Caller
from rfsdk_kernel.dispatcher import Dispatcher
from rfsdk_kernel.errors import ActionContractError
from rfsdk_kernel.registry import action, get_action

from coworker.dispatch.router import CapabilityRouter, FabricRefusal

from .sqlite_ports import (
    SqliteApprovalStore,
    SqliteChangeBus,
    SqliteEvidenceStore,
    TenantPolicy,
)

ANCHOR_UNAVAILABLE = "anchor_unavailable"
DB_NAME = "rfsdk.db"


class StageInput(BaseModel):
    """Every stage names the work item and its tenant; the TenantPolicy checks the pair."""
    inbox_id: str
    tenant: str


class SignInput(StageInput):
    approver: str


class StageResult(BaseModel):
    """The existing activity bodies return loose dicts; the envelope seals them as-is."""
    model_config = ConfigDict(extra="allow")


def dispatch_caller(tenant: str, inbox_id: str) -> Caller:
    """The dispatcher as a service principal scoped to the item's tenant.

    actor_kind "service" makes the Dispatcher run Policy.check on EVERY dispatch, so tenant
    isolation is enforced at the governed boundary, not by convention.
    """
    return Caller(
        principal_id="openworker-dispatcher", email="dispatcher@openworker.invalid",
        org_id=tenant, org_role="member", app_roles=frozenset(), surface="automation",
        actor_kind="service", thread_id=None, turn_id=None, run_id=inbox_id,
        authenticated_at=datetime.now(UTC))


_BOUND: Any = None     # the _Activities instance the handlers call (one engine per process)


def _activities() -> Any:
    if _BOUND is None:
        raise ActionContractError("governed actions are not bound to an engine",
                                  error_code="unbound_activities", status_code=500)
    return _BOUND


def read_fabric_anchor(fabric_run: str) -> dict:
    """Fabric's sealed head for one run, required verified and non-null (fail closed)."""
    try:
        chain = CapabilityRouter().chain(fabric_run)
    except FabricRefusal as exc:
        raise ActionContractError(
            f"the fabric chain read refused: {exc.detail}",
            error_code=ANCHOR_UNAVAILABLE, status_code=exc.status or 503) from exc
    if not chain.get("verified") or not chain.get("chain_head"):
        raise ActionContractError(
            f"fabric returned no attestable head for {fabric_run}"
            f" (verified={chain.get('verified')!r}, chain_head={chain.get('chain_head')!r})",
            error_code=ANCHOR_UNAVAILABLE, status_code=409)
    return {"session_id": fabric_run, "chain_head": chain["chain_head"]}


def view_sha256(inbox_id: str) -> str | None:
    """sha-256 of the stored declared view's canonical JSON; None when no view was stored.

    The plain canonical form (sorted keys, compact separators, UTF-8), not
    receipts.canonical_bytes, which drops a top-level "integrity" key.
    """
    item = _activities().manager.inbox.get(inbox_id)
    view = (item.data or {}).get("view") if item is not None else None
    if view is None:
        return None
    canonical = json.dumps(view, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _register_actions() -> None:
    """Register the six stages once per process (the registry is module-global)."""
    if get_action("ow.frame_work_item") is not None:
        return

    @action(name="ow.frame_work_item", input_schema=StageInput, output_schema=StageResult,
            description="frame one work item against the declared capability cards and open "
                        "its governed fabric run")
    async def _frame(args: StageInput) -> StageResult:
        return StageResult(**_activities().frame_work_item(args.inbox_id))

    @action(name="ow.execute_work_item", input_schema=StageInput, output_schema=StageResult,
            description="drive the open fabric run to its gate or terminal state; a terminal "
                        "run seals the fabric anchor (dispatch-anchor v1.0.0) and view_sha256")
    async def _execute(args: StageInput) -> StageResult:
        result = _activities().execute_work_item(args.inbox_id)
        if (not result.get("failed") and not result.get("awaiting_signoff")
                and result.get("fabric_run")):
            result["fabric_anchor"] = read_fabric_anchor(result["fabric_run"])
            result["view_sha256"] = view_sha256(args.inbox_id)
        return StageResult(**result)

    @action(name="ow.check_signoff", input_schema=StageInput, output_schema=StageResult,
            description="read the inbox item's human-gate state (the Signal-lost fallback)",
            read_only=True)
    async def _check(args: StageInput) -> StageResult:
        return StageResult(**_activities().check_signoff(args.inbox_id))

    @action(name="ow.sign_work_item", input_schema=SignInput, output_schema=StageResult,
            description="complete the human gate through the F-012 freeze-and-digest path; "
                        "the now-terminal run seals the fabric anchor (dispatch-anchor v1.0.0) "
                        "and view_sha256")
    async def _sign(args: SignInput) -> StageResult:
        result = _activities().sign_work_item(args.inbox_id, args.approver)
        job = _activities().manager.runs.get(args.inbox_id) or {}
        if job.get("fabric_run"):
            result["fabric_anchor"] = read_fabric_anchor(job["fabric_run"])
            result["view_sha256"] = view_sha256(args.inbox_id)
        return StageResult(**result)

    @action(name="ow.emit_receipt", input_schema=StageInput, output_schema=StageResult,
            description="deliver the one JSON receipt for the work item (keyed, idempotent)")
    async def _receipt(args: StageInput) -> StageResult:
        return StageResult(**_activities().emit_receipt(args.inbox_id))

    @action(name="ow.learn_work_item", input_schema=StageInput, output_schema=StageResult,
            description="record the routing lesson for the decided item (best effort)")
    async def _learn(args: StageInput) -> StageResult:
        return StageResult(**_activities().learn_work_item(args.inbox_id))


class GovernedDispatch:
    """One Dispatcher over the SQLite port adapters; the sync facade the activities call."""

    def __init__(self, activities: Any, state_dir: str | Path) -> None:
        global _BOUND
        db = Path(state_dir) / DB_NAME
        self.evidence = SqliteEvidenceStore(db)
        self.approvals = SqliteApprovalStore(db)
        self.changes = SqliteChangeBus(db)
        self.policy = TenantPolicy()
        self.dispatcher = Dispatcher(evidence=self.evidence, policy=self.policy,
                                     approvals=self.approvals, changes=self.changes)
        _BOUND = activities
        _register_actions()

    def run(self, name: str, inbox_id: str, tenant: str, **extra: Any) -> dict:
        """Dispatch one stage for one work item; every outcome seals one envelope.

        Called from a Temporal activity thread; each call runs its own event loop, so no
        loop or connection crosses threads.
        """
        caller = dispatch_caller(tenant, inbox_id)
        result = asyncio.run(self.dispatcher.dispatch(
            name, {"inbox_id": inbox_id, "tenant": tenant, **extra}, caller,
            request_source="temporal"))
        return result.model_dump(mode="json")
