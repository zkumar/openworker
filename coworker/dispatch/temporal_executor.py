"""Temporal executor glue — worker, client and the activities (OW-F-013, phase 1).

Imported ONLY when `OPENWORKER_EXECUTOR=temporal`, so `temporalio` stays an optional extra
(`pip install 'openworker[temporal]'`). Fail closed, loudly: a missing extra or an unreachable
Temporal server refuses at startup; nothing silently falls back to the thread path.

One background thread carries the event loop with the Temporal client and worker. Each activity
is a thin wrapper over the EXISTING side-effect path, so the thread executor and the workflow
drive the same product code:

  frame_work_item    CapabilityRouter.frame + SessionManager.channel_set_run
  execute_work_item  CapabilityRouter.resume (looks before pursuing — idempotent under retry)
                     + channel_run_finish / channel_run_fail
  check_signoff      reads the inbox item (the Signal-lost fallback)
  sign_work_item     SessionManager.sign_channel_item (freeze → digest post → signoff),
                     record_signature, record_steps — the F-012 path, unchanged
  emit_receipt       SessionManager.deliver_receipt (derive-at-read + keyed egress: exactly one
                     receipt file per work item, re-delivery replaces its own file)
  learn_work_item    CapabilityRouter.learn (best-effort, as today)
"""
from __future__ import annotations

import asyncio
import concurrent.futures
import os
import threading
from typing import Any, Optional

try:
    from temporalio import activity
    from temporalio.client import Client
    from temporalio.exceptions import ApplicationError, WorkflowAlreadyStartedError
    from temporalio.worker import Worker
except ImportError as exc:  # fail closed, actionably — never fall back to the thread path
    raise RuntimeError(
        "OPENWORKER_EXECUTOR=temporal needs the optional extra: "
        "pip install 'openworker[temporal]' (temporalio is not installed)"
    ) from exc

from .router import CapabilityRouter, FabricRefusal
from .temporal_workflow import REFUSAL_ERROR, TASK_QUEUE, WorkItemWorkflow


def workflow_id(inbox_id: str) -> str:
    """Deterministic id: the approval resolution can signal by inbox item alone."""
    return f"workitem-{inbox_id}"


class _Activities:
    """The side effects, each wrapping the existing path. `manager` is the SessionManager."""

    def __init__(self, manager: Any) -> None:
        self.manager = manager

    def _job(self, inbox_id: str) -> dict:
        row = self.manager.runs.get(inbox_id)
        if row is None:
            raise ApplicationError(f"no RunStore row for {inbox_id}", non_retryable=True)
        return row

    def _refused(self, inbox_id: str, exc: FabricRefusal) -> dict:
        """Mirror the thread path: record the refusal, then let Temporal's policy decide.

        A 4xx is terminal (never retried — workspace invariant): the failure is recorded and
        the receipt delivered by channel_run_fail, so the activity RETURNS and the workflow
        ends cleanly. A 5xx/unreachable raises retryably; channel_run_fail has already marked
        the item retrying, exactly as the sweep path does.
        """
        self.manager.channel_run_fail(inbox_id, exc.detail, retryable=exc.retryable,
                                      not_found=(exc.status == 404))
        if not exc.retryable:
            return {"failed": True, "refused": True, "detail": exc.detail}
        raise ApplicationError(f"fabric error (will retry): {exc.detail}") from exc

    @activity.defn(name="frame_work_item")
    def frame_work_item(self, inbox_id: str) -> dict:
        job = self._job(inbox_id)
        if job.get("fabric_run"):   # an activity retry or a restart: the run is already open
            return {"framed": True, "fabric_run": job["fabric_run"], "agent": job["agent"]}
        try:
            framed = CapabilityRouter().frame(job["record"])
        except FabricRefusal as exc:
            return self._refused(inbox_id, exc)
        if framed is None:
            result = {"framed": False,
                      "reason": "no agent's declared contract covers this item"}
            self.manager.channel_run_finish(inbox_id, result, job["session_id"])
            return result
        fabric_run, agent = framed
        self.manager.channel_set_run(inbox_id, fabric_run, agent)
        return {"framed": True, "fabric_run": fabric_run, "agent": agent}

    @activity.defn(name="execute_work_item")
    def execute_work_item(self, inbox_id: str) -> dict:
        job = self._job(inbox_id)
        try:
            result = CapabilityRouter().resume(
                job["fabric_run"], job["record"], agent=job["agent"],
                on_step=lambda s: self.manager.channel_append_step(inbox_id, s))
        except FabricRefusal as exc:
            return self._refused(inbox_id, exc)
        self.manager.channel_run_finish(inbox_id, result, job["session_id"])
        return {"framed": True, "awaiting_signoff": bool(result.get("awaiting_signoff")),
                "decision": result.get("decision"),
                "fabric_run": job["fabric_run"], "agent": job["agent"]}

    @activity.defn(name="check_signoff")
    def check_signoff(self, inbox_id: str) -> dict:
        item = self.manager.inbox.get(inbox_id)
        if item is None:
            return {"signed": False, "rejected": True, "by": "unknown (item gone)"}
        data = item.data or {}
        sig = data.get("signature") or {}
        rejected = (item.state == "resolved" and not sig
                    and (item.resolution or "") in ("deny", "denied", "reject", "rejected"))
        return {"signed": bool(sig), "approver": sig.get("approver"),
                "rejected": rejected, "by": item.resolution or ""}

    @activity.defn(name="sign_work_item")
    def sign_work_item(self, inbox_id: str, approver: str) -> dict:
        item = self.manager.inbox.get(inbox_id)
        if item is None:
            raise ApplicationError(f"unknown inbox item {inbox_id}", non_retryable=True)
        if (item.data or {}).get("signature"):   # retry/replay: the signature already landed
            return {"decision": (item.data or {}).get("decision"), "already_signed": True}
        import httpx
        try:
            signed = self.manager.sign_channel_item(item.session_id)
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            if 400 <= status < 500:   # never retry a 4xx
                raise ApplicationError(f"fabric refused the signoff ({status})",
                                       type=REFUSAL_ERROR, non_retryable=True) from exc
            raise
        self.manager.record_signature(inbox_id, approver, (signed or {}).get("signed") or {})
        self.manager.record_steps(inbox_id, (signed or {}).get("steps") or [])
        return {"decision": (signed or {}).get("final_state") or (signed or {}).get("decision")}

    @activity.defn(name="emit_receipt")
    def emit_receipt(self, inbox_id: str) -> dict:
        failed = self.manager.deliver_receipt(inbox_id)
        if failed:   # retryable: the receipt is derived at read time, re-delivery is keyed
            raise ApplicationError(f"egress delivery failed: {failed}")
        return {"delivered": True}

    @activity.defn(name="learn_work_item")
    def learn_work_item(self, inbox_id: str) -> dict:
        item = self.manager.inbox.get(inbox_id)
        data = (item.data or {}) if item is not None else {}
        CapabilityRouter().learn(data.get("record") or {},
                                 {"agent": data.get("agent"), "decision": data.get("decision")})
        return {"ok": True}

    def all(self) -> list:
        return [self.frame_work_item, self.execute_work_item, self.check_signoff,
                self.sign_work_item, self.emit_receipt, self.learn_work_item]


class TemporalExecutor:
    """Owns the client + worker on a background event loop; sync facade for the HTTP paths."""

    def __init__(self, manager: Any, *, address: str | None = None,
                 namespace: str | None = None) -> None:
        self.manager = manager
        self.address = address or os.environ.get("OPENWORKER_TEMPORAL_ADDRESS", "127.0.0.1:7233")
        self.namespace = namespace or os.environ.get("OPENWORKER_TEMPORAL_NAMESPACE", "default")
        self.poll_seconds = int(os.environ.get("OPENWORKER_TEMPORAL_POLL_SECONDS", "300"))
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._client: Optional[Client] = None
        self._ready = threading.Event()
        self._startup_error: Optional[BaseException] = None

    def start(self, timeout: float = 15.0) -> "TemporalExecutor":
        threading.Thread(target=self._run_loop, name="temporal-executor", daemon=True).start()
        if not self._ready.wait(timeout) or self._startup_error is not None:
            raise RuntimeError(
                f"OPENWORKER_EXECUTOR=temporal: cannot reach the Temporal server at "
                f"{self.address} (is `temporal server start-dev` running?): "
                f"{self._startup_error or 'timed out connecting'}")
        return self

    def _run_loop(self) -> None:
        loop = asyncio.new_event_loop()
        self._loop = loop
        asyncio.set_event_loop(loop)
        loop.run_until_complete(self._main())

    async def _main(self) -> None:
        try:
            self._client = await Client.connect(self.address, namespace=self.namespace)
            # The sandbox re-imports the workflow module's import chain; the dispatch package's
            # __init__ pulls in the router (httpx → urllib), which the workflow never calls.
            # Mark those as pass-through — the workflow module itself stays deterministic.
            from temporalio.worker.workflow_sandbox import (
                SandboxedWorkflowRunner,
                SandboxRestrictions,
            )

            worker = Worker(
                self._client,
                task_queue=TASK_QUEUE,
                workflows=[WorkItemWorkflow],
                activities=_Activities(self.manager).all(),
                activity_executor=concurrent.futures.ThreadPoolExecutor(max_workers=8),
                workflow_runner=SandboxedWorkflowRunner(
                    restrictions=SandboxRestrictions.default.with_passthrough_modules(
                        "coworker", "httpx")),
            )
        except BaseException as exc:   # surface it to start(); the thread ends here
            self._startup_error = exc
            self._ready.set()
            return
        self._ready.set()
        await worker.run()

    # -- sync facade (called from HTTP handler threads / the FastAPI loop) -------------
    def _call(self, coro: Any, timeout: float = 15.0) -> Any:
        assert self._loop is not None
        return asyncio.run_coroutine_threadsafe(coro, self._loop).result(timeout)

    def submit(self, inbox_id: str) -> str:
        """Start the durable workflow for one work item. Idempotent by workflow id."""
        wid = workflow_id(inbox_id)

        async def _start() -> None:
            try:
                await self._client.start_workflow(
                    WorkItemWorkflow.run,
                    {"inbox_id": inbox_id, "poll_seconds": self.poll_seconds},
                    id=wid, task_queue=TASK_QUEUE)
            except WorkflowAlreadyStartedError:
                pass   # a re-dispatch after restart: the durable workflow already owns it

        self._call(_start())
        return wid

    def signal_signoff(self, inbox_id: str, approver: str) -> None:
        handle = self._client.get_workflow_handle(workflow_id(inbox_id))
        self._call(handle.signal(WorkItemWorkflow.signoff_resolved, approver))

    def signal_rejected(self, inbox_id: str, by: str) -> None:
        handle = self._client.get_workflow_handle(workflow_id(inbox_id))
        self._call(handle.signal(WorkItemWorkflow.signoff_rejected, by))


_EXECUTOR: Optional[TemporalExecutor] = None


def start_executor(manager: Any) -> TemporalExecutor:
    global _EXECUTOR
    if _EXECUTOR is None:
        _EXECUTOR = TemporalExecutor(manager).start()
    return _EXECUTOR


def current() -> TemporalExecutor:
    if _EXECUTOR is None:   # fail closed: selected but never started is a refusal, not a fallback
        raise RuntimeError("OPENWORKER_EXECUTOR=temporal is set but the executor was not "
                           "started — the server refused at startup; fix that first")
    return _EXECUTOR
