"""Inbound CHANNEL contract (A4) — how a work item enters the harness.

A channel is the only place a work item can originate. It turns a payload from the outside
world (a webhook POST, a mail message, a Kafka record) into a `WorkItem` — the RECORD the
dispatcher frames. Nothing here knows a domain: the record's fields are the contract the
capability cards are matched against.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Protocol


@dataclass(frozen=True)
class WorkItem:
    """One unit of inbound work: the record plus where it came from."""

    channel: str
    record: dict[str, Any]
    received_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    meta: dict[str, Any] = field(default_factory=dict)


class Channel(Protocol):
    """A pluggable source of work items. Adding one is a registry entry, not a code edit."""

    name: str

    def ingest(self, payload: dict[str, Any]) -> WorkItem | None:
        """Turn one payload into a work item, or None if it carries no work."""
        ...
