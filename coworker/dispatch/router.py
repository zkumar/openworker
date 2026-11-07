"""Capability router — the harness's dispatch loop.

A work item (the record a channel delivered) is framed, matched to an agent by its declared
capability card, executed through the fabric's governed run, and the lesson is written to the
harness's memory. No domain pack is imported: the fabric is reached over its frozen contracts
(`/api/capabilities`, `/api/agents/{id}/plan`, `/api/runs`) and nothing else.
"""
from __future__ import annotations

import json
import os
import threading
from typing import Any, Callable, Optional

import httpx

FABRIC = os.environ.get("REGAGENTIC_FABRIC_URL", "http://127.0.0.1:8766")


class FabricRefusal(Exception):
    """The fabric refused the work in a way a human can act on (usually a 4xx).

    `retryable` is False for a refusal: repeating the same call cannot succeed.
    """

    def __init__(self, detail: str, status: int = 0) -> None:
        super().__init__(detail)
        self.detail = detail
        self.status = status
        self.retryable = status == 0 or status >= 500


class CapabilityRouter:
    """The harness half of `frame → capability → execute → learn`."""

    def __init__(self, *, base: str = FABRIC, username: str = "dr.md", password: str = "test",
                 learn: bool = True) -> None:
        self._base = base.rstrip("/")
        self._username, self._password = username, password
        self._learn = learn
        self._token: Optional[str] = None

    # --- fabric contracts -----------------------------------------------------
    def _headers(self) -> dict[str, str]:
        if self._token is None:
            with httpx.Client(timeout=10) as client:
                response = client.post(f"{self._base}/api/auth/login",
                                       json={"username": self._username, "password": self._password})
                response.raise_for_status()
                self._token = response.json()["access_token"]
        return {"Authorization": f"Bearer {self._token}"}

    @staticmethod
    def _refusal(exc: Exception) -> "FabricRefusal":
        status = getattr(getattr(exc, "response", None), "status_code", 0) or 0
        detail = ""
        try:
            body = exc.response.json()                      # type: ignore[attr-defined]
            detail = str(body.get("detail") or body.get("error") or "")
        except Exception:
            detail = str(getattr(exc, "response", "") or exc)
        return FabricRefusal(detail or "the fabric refused the request", status)

    def _get(self, path: str) -> Any:
        with httpx.Client(timeout=20) as client:
            response = client.get(f"{self._base}{path}", headers=self._headers())
            response.raise_for_status()
            return response.json()

    def _post(self, path: str, body: dict) -> Any:
        with httpx.Client(timeout=120) as client:
            response = client.post(f"{self._base}{path}", json=body, headers=self._headers())
            response.raise_for_status()
            return response.json()

    # --- the loop -------------------------------------------------------------
    def pick(self, cards: list[dict], item: dict) -> Optional[dict]:
        """The card whose declared input contract covers the item's fields best."""
        best: Optional[tuple[int, dict]] = None
        for card in cards:
            overlap = set(card.get("input_contract") or []) & set(item)
            if overlap and (best is None or len(overlap) > best[0]):
                best = (len(overlap), card)
        return best[1] if best else None

    def frame(self, item: dict, *, interactive_signoff: bool = True) -> Optional[tuple[str, str]]:
        """The frame stage alone: pick a card and open the governed run.

        Returns (session_id, agent_id), or None when no card's declared contract covers the
        item. OW-F-013 gives the durable coordinator each stage separately; `route()` below
        stays the single-call path the thread executor uses.
        """
        try:
            card = self.pick(self._get("/api/capabilities")["capabilities"], item)
            if card is None:
                return None
            start = self._post("/api/runs",
                               {"agent_id": card["id"], "interactive_signoff": interactive_signoff})
            return start["session_id"], card["id"]
        except httpx.HTTPStatusError as exc:
            raise self._refusal(exc) from exc
        except httpx.RequestError as exc:
            raise FabricRefusal(f"fabric unreachable: {exc}", 0) from exc

    def chain(self, session_id: str) -> dict:
        """The fabric chain read (dispatch-anchor contract v1.0.0, fabric RFC 0054).

        Returns the raw response: verified, count, chain_head (the full 64-char sealed head,
        or null on an empty or unverifiable chain), envelopes. OW-F-014 anchors the head into
        the harness rfsdk envelope; the fail-closed decision on a null head is the caller's.
        """
        try:
            return self._get(f"/api/runs/{session_id}/chain")
        except httpx.HTTPStatusError as exc:
            raise self._refusal(exc) from exc
        except httpx.RequestError as exc:
            raise FabricRefusal(f"fabric unreachable: {exc}", 0) from exc

    def _pursue(self, session_id: str, inputs: dict) -> Any:
        try:
            return self._post(f"/api/runs/{session_id}/pursue", {"inputs": inputs})
        except httpx.HTTPStatusError as exc:
            raise self._refusal(exc) from exc
        except httpx.RequestError as exc:
            raise FabricRefusal(f"fabric unreachable: {exc}", 0) from exc

    def _watch(self, session_id: str, on_step: Callable[[dict], None], stop: threading.Event) -> None:
        """Relay the fabric's live step stream into the caller as it happens."""
        try:
            with httpx.Client(timeout=None) as client:
                with client.stream("GET", f"{self._base}/api/runs/{session_id}/events",
                                   headers=self._headers()) as response:
                    for line in response.iter_lines():
                        if stop.is_set():
                            return
                        if not line.startswith("data:"):
                            continue
                        try:
                            payload = json.loads(line[5:].strip() or "{}")
                        except json.JSONDecodeError:
                            continue
                        if payload.get("type") != "process.advanced":
                            continue          # one row per transition; skills ride along as `skill`
                        body = payload.get("payload") or {}      # the sink wraps events as {type, payload}
                        on_step({"state_before": body.get("from"),
                                 "state_after": body.get("to"),
                                 "summary": body.get("skill"),
                                 "type": "step"})
        except Exception:
            return                        # watching must never break the governed run

    def resume(self, run_id: str, record: dict, *, agent: str | None = None,
               on_step: Callable[[dict], None] | None = None) -> dict[str, Any]:
        """Re-drive a run that outlived its request — WITHOUT advancing it twice.

        Resuming must be idempotent: if the run already parked at a gate, or already finished,
        pursuing again would append duplicate steps and drift the decision. So look first.
        """
        gates = self._get(f"/api/runs/{run_id}/pending-signoff").get("gates") or []
        finished = False
        try:
            for s in self._get("/api/sessions").get("sessions", []):
                if s.get("session_id") == run_id:
                    finished = s.get("status") == "complete"
                    break
        except Exception:
            finished = False
        if gates or finished:
            chain = self._get(f"/api/runs/{run_id}/chain")
            steps = [{"type": e.get("type"), "summary": e.get("summary"),
                      "state_before": e.get("state_before"), "state_after": e.get("state_after"),
                      "sha256": e.get("sha256")} for e in (chain.get("envelopes") or [])]
            return {"framed": True, "agent": agent, "awaiting_signoff": bool(gates), "gates": gates,
                    "plan": {}, "steps": steps, "envelopes": len(steps),
                    "decision": (gates[-1]["state_after"] if gates
                                 else (steps[-1]["state_after"] if steps else None)),
                    "session_id": run_id, "already": "gate" if gates else "complete"}

        stop = threading.Event()
        if on_step is not None:
            threading.Thread(target=self._watch, args=(run_id, on_step, stop), daemon=True).start()
        outcome = self._post(f"/api/runs/{run_id}/pursue", {"inputs": record})
        stop.set()
        chain = self._get(f"/api/runs/{run_id}/chain")
        steps = [{"type": e.get("type"), "summary": e.get("summary"),
                  "state_before": e.get("state_before"), "state_after": e.get("state_after"),
                  "sha256": e.get("sha256"), "at": e.get("timestamp")}
                 for e in (chain.get("envelopes") or [])]
        gates = self._get(f"/api/runs/{run_id}/pending-signoff").get("gates") or []
        plan = {}
        if agent:
            try:
                p = self._get(f"/api/agents/{agent}/plan")
                plan = {"name": p["name"],
                        "signoff": next((x.get("signoff") for x in p["transitions"]
                                         if x.get("signoff")), None),
                        "states": [s["name"] for s in p["states"]],
                        "gate_state": next((x["to"] for x in p["transitions"]
                                            if x.get("signoff")), None)}
            except Exception:
                plan = {}
        return {"framed": True, "agent": agent, "awaiting_signoff": bool(gates), "gates": gates,
                "plan": plan, "steps": steps, "envelopes": len(steps),
                "decision": (outcome or {}).get("decision") or (gates[-1]["state_after"] if gates else None),
                "session_id": run_id}

    def route(self, item: dict, on_step: Callable[[dict], None] | None = None,
              on_start: Callable[[str, str], None] | None = None) -> dict[str, Any]:
        card = self.pick(self._get("/api/capabilities")["capabilities"], item)
        if card is None:
            return {"framed": False, "reason": "no agent's declared contract covers this item"}
        plan = self._get(f"/api/agents/{card['id']}/plan")
        start = self._post("/api/runs", {"agent_id": card["id"], "interactive_signoff": True})
        session_id = start["session_id"]
        if on_start is not None:
            on_start(session_id, card["id"])      # record it now, so a crash can be resumed
        stop = threading.Event()
        watcher = None
        if on_step is not None:
            watcher = threading.Thread(target=self._watch, args=(session_id, on_step, stop), daemon=True)
            watcher.start()
        outcome = self._pursue(session_id, item)
        stop.set()
        paused = bool(outcome.get("paused"))
        gates = self._get(f"/api/runs/{session_id}/pending-signoff").get("gates") or [] if paused else []
        chain = self._get(f"/api/runs/{session_id}/chain")
        steps = [
            {"type": e.get("type"), "summary": e.get("summary"),
             "state_before": e.get("state_before"), "state_after": e.get("state_after"),
             "sha256": e.get("sha256"), "at": e.get("timestamp")}
            for e in (chain.get("envelopes") or [])
        ]
        result = {
            "framed": True,
            "agent": card["id"],
            "human_gate_required": card.get("human_gate_required"),
            "awaiting_signoff": paused,
            "gates": gates,
            "decision": outcome.get("decision") or (gates[-1]["state_after"] if gates else None),
            "plan": {"name": plan["name"],
                     "signoff": next((t.get("signoff") for t in plan["transitions"]
                                      if t.get("signoff")), None),
                     "states": [s["name"] for s in plan["states"]],
                     "gate_state": next((t["to"] for t in plan["transitions"]
                                         if t.get("signoff")), None)},
            "envelopes": len(steps),
            "steps": steps,
            "session_id": session_id,
        }
        if self._learn:
            self.learn(item, result)
        return result

    def learn(self, item: dict, result: dict) -> None:
        """Write the lesson to the harness's ONE memory store (best-effort)."""
        try:
            from coworker.memory.tools import remember
            remember(
                content=(f"Routed a work item with fields {sorted(item)} to {result.get('agent')}; "
                         f"the governed run decided {result.get('decision')}."),
                summary=f"{result.get('agent')} -> {result.get('decision')}",
                scope="workspace",
            )
        except Exception:
            return   # learning must never fail a completed governed run
