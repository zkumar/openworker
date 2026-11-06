"""Operational visibility — the numbers an operator needs without reading a database.

Nothing here changes behaviour; it reports what the durable stores already know. An "alert" is a
condition with a name and a severity, so it can be scraped, logged or wired to paging later
without this module deciding where alerts go.
"""

from __future__ import annotations

import time
from typing import Any

# A run that has been dispatched for longer than this is probably stuck rather than slow.
STUCK_RUN_SECONDS = 15 * 60
# Signature requests older than this are delaying a regulated decision.
STALE_GATE_SECONDS = 4 * 60 * 60
# An ingress backlog that never drains means the consumer is not keeping up.
INGRESS_BACKLOG_WARN = 100


def _age_seconds(stamp: str) -> float | None:
    if not stamp:
        return None
    try:
        return time.time() - time.mktime(time.strptime(stamp[:19], "%Y-%m-%dT%H:%M:%S"))
    except Exception:
        return None


def snapshot(manager) -> dict[str, Any]:
    """Everything measurable, in one dict, safe to expose to an authenticated caller."""
    runs = manager.runs.stats() if hasattr(manager.runs, "stats") else {}
    ingress = manager.ingress.stats()
    items = list(manager.inbox._items.values())     # noqa: SLF001 — read-only snapshot

    pending_gates = 0
    stale_gates = 0
    stuck = 0
    by_decision: dict[str, int] = {}
    oldest_gate_age: float | None = None

    for item in items:
        d = item.data or {}
        if d.get("running"):
            age = _age_seconds(item.created_at)
            if age and age > STUCK_RUN_SECONDS:
                stuck += 1
        if d.get("awaiting_signoff") and item.state == "pending":
            pending_gates += 1
            age = _age_seconds(item.created_at)
            if age:
                oldest_gate_age = age if oldest_gate_age is None else max(oldest_gate_age, age)
                if age > STALE_GATE_SECONDS:
                    stale_gates += 1
        decision = d.get("decision")
        if decision:
            by_decision[str(decision)] = by_decision.get(str(decision), 0) + 1

    alerts: list[dict[str, str]] = []
    if runs.get("failed"):
        alerts.append({"name": "runs_failed", "severity": "warn",
                       "detail": f"{runs['failed']} run(s) exhausted their retries"})
    if ingress.get("failed"):
        alerts.append({"name": "ingress_failed", "severity": "error",
                       "detail": f"{ingress['failed']} accepted record(s) could never be dispatched"})
    backlog = ingress.get("pending", 0)
    if backlog > INGRESS_BACKLOG_WARN:
        alerts.append({"name": "ingress_backlog", "severity": "warn",
                       "detail": f"{backlog} record(s) waiting to be dispatched"})
    if stuck:
        alerts.append({"name": "runs_stuck", "severity": "warn",
                       "detail": f"{stuck} run(s) dispatched for over {STUCK_RUN_SECONDS // 60} minutes"})
    if stale_gates:
        alerts.append({"name": "signatures_stale", "severity": "warn",
                       "detail": f"{stale_gates} decision(s) waiting for a signature over "
                                 f"{STALE_GATE_SECONDS // 3600}h"})

    return {
        "runs": runs,
        "ingress": ingress,
        "items": {"total": len(items), "awaiting_signature": pending_gates,
                  "oldest_gate_age_seconds": int(oldest_gate_age) if oldest_gate_age else None},
        "decisions": by_decision,
        "alerts": alerts,
        "healthy": not [a for a in alerts if a["severity"] == "error"],
    }
