"""The durable dispatcher — a Temporal workflow coordinating ONE work item (OW-F-013, phase 1).

The workflow owns coordination only. Every side effect — framing, the fabric run, the human
signature, the receipt, the lesson — lives in an activity that wraps the existing code path
(`CapabilityRouter`, `SessionManager.channel_*`, `sign_channel_item`, `deliver_receipt`), so
the thread executor and this one drive the same product code. Durability comes from Temporal:
the workflow survives a harness kill -9 and waits on the human gate as a Signal, for days.

This module is imported only when `OPENWORKER_EXECUTOR=temporal` selects the executor (via
`temporal_executor`), so `temporalio` stays an optional extra.

Determinism rules (fabric RAF-021 precedent): no I/O, no env reads — the poll interval arrives
as workflow input; activities are referenced by name. Breaking changes bump WORKFLOW_VERSION.
"""
from __future__ import annotations

from datetime import timedelta
from typing import Any, Optional

from temporalio import workflow
from temporalio.common import RetryPolicy

WORKFLOW_VERSION = 1
TASK_QUEUE = "openworker-dispatch"

# A fabric 4xx is a refusal: terminal, never retried (workspace invariant). Activities raise
# ApplicationError(type=REFUSAL_ERROR, non_retryable=True) for those; everything else (5xx,
# unreachable) retries with backoff, mirroring RunStore's hand-rolled 2s/4s/8s… policy.
REFUSAL_ERROR = "FabricRefusal"

_RETRY = RetryPolicy(
    initial_interval=timedelta(seconds=2),
    maximum_interval=timedelta(seconds=60),
    maximum_attempts=5,
    non_retryable_error_types=[REFUSAL_ERROR],
)


def _activity(name: str, *args: Any, timeout_s: int = 300) -> Any:
    return workflow.execute_activity(
        name,
        args=list(args),
        start_to_close_timeout=timedelta(seconds=timeout_s),
        retry_policy=_RETRY,
    )


@workflow.defn(name="WorkItemWorkflow")
class WorkItemWorkflow:
    """frame+capability → fabric pursue → signoff wait (Signal) → sign + receipt → learn."""

    def __init__(self) -> None:
        self._resolution: Optional[tuple[str, str]] = None  # ("approved"|"rejected", by)

    @workflow.signal
    def signoff_resolved(self, approver: str) -> None:
        if self._resolution is None:
            self._resolution = ("approved", approver or "a human approver")

    @workflow.signal
    def signoff_rejected(self, by: str) -> None:
        if self._resolution is None:
            self._resolution = ("rejected", by or "a human")

    @workflow.run
    async def run(self, item: dict) -> dict:
        inbox_id: str = item["inbox_id"]
        poll = timedelta(seconds=int(item.get("poll_seconds") or 300))

        framed = await _activity("frame_work_item", inbox_id)
        if not framed.get("framed"):
            return {"workflow_version": WORKFLOW_VERSION, **framed}

        result = await _activity("execute_work_item", inbox_id, timeout_s=600)
        if result.get("failed") or not result.get("awaiting_signoff"):
            if not result.get("failed"):
                await _activity("learn_work_item", inbox_id)
            return {"workflow_version": WORKFLOW_VERSION, **result}

        # The human gate. The inbox resolution sends the Signal; the slow poll is the fallback
        # that closes the gate when a signal was lost (e.g. an item signed inline before a
        # crash, or resolved while no workflow could be signalled). Days of waiting are fine:
        # the timer is durable and the worker holds nothing.
        while self._resolution is None:
            try:
                await workflow.wait_condition(lambda: self._resolution is not None, timeout=poll)
            except TimeoutError:
                state = await _activity("check_signoff", inbox_id)
                if state.get("signed"):
                    self._resolution = ("approved", state.get("approver") or "a human approver")
                elif state.get("rejected"):
                    self._resolution = ("rejected", state.get("by") or "a human")

        decision, by = self._resolution
        if decision == "rejected":
            return {"workflow_version": WORKFLOW_VERSION, **result,
                    "signed": False, "rejected": True}

        signed = await _activity("sign_work_item", inbox_id, by, timeout_s=600)
        await _activity("emit_receipt", inbox_id)
        await _activity("learn_work_item", inbox_id)
        return {"workflow_version": WORKFLOW_VERSION, **result, **signed, "signed": True}
