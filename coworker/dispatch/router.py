"""Capability router — the harness's dispatch loop.

A work item (the record a channel delivered) is framed, matched to an agent by its declared
capability card, executed through the fabric's governed run, and the lesson is written to the
harness's memory. No domain pack is imported: the fabric is reached over its frozen contracts
(`/api/capabilities`, `/api/agents/{id}/plan`, `/api/runs`) and nothing else.
"""
from __future__ import annotations

import os
from typing import Any, Optional

import httpx

FABRIC = os.environ.get("REGAGENTIC_FABRIC_URL", "http://127.0.0.1:8766")


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

    def route(self, item: dict) -> dict[str, Any]:
        card = self.pick(self._get("/api/capabilities")["capabilities"], item)
        if card is None:
            return {"framed": False, "reason": "no agent's declared contract covers this item"}
        plan = self._get(f"/api/agents/{card['id']}/plan")
        start = self._post("/api/runs", {"agent_id": card["id"], "interactive_signoff": True})
        session_id = start["session_id"]
        outcome = self._post(f"/api/runs/{session_id}/pursue", {"inputs": item})
        paused = bool(outcome.get("paused"))
        gates = self._get(f"/api/runs/{session_id}/pending-signoff").get("gates") or [] if paused else []
        chain = self._get(f"/api/runs/{session_id}/chain")
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
            "envelopes": len(chain.get("envelopes") or []),
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
