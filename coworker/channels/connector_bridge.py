"""F-010 — a connector event becomes a work item.

connectors own transport (BasePlatformAdapter connects, receives, sends). This bridge owns only the
translation: a `MessageEvent` carries conversation (text, threads, mentions); a `WorkItem` needs a
record. So the record must arrive explicitly — in the event's `raw` payload — and a message that
carries no record produces no work.

Idempotency: one work item per (platform, message_id) when the platform supplies an id.
"""
from __future__ import annotations

from typing import Any

from .base import WorkItem


def record_from_event(platform: str, event: Any) -> WorkItem | None:
    """Translate one connector event to a work item, or None when it carries no record.

    A miss returns None rather than guessing: adjudicating a mis-parsed record would be worse
    than dropping a message.
    """
    raw = getattr(event, "raw", None)
    if not isinstance(raw, dict):
        return None
    record = raw.get("record") if isinstance(raw.get("record"), dict) else raw
    # A record must be identifiable; a bare text message is conversation, not work.
    if not isinstance(record, dict) or not record.get("request_id"):
        return None
    message_id = getattr(event, "message_id", None)
    return WorkItem(
        channel=platform,
        record=dict(record),
        meta={"message_id": message_id} if message_id else {},
    )


class ConnectorBridge:
    """Registers itself as a platform adapter's message handler; hands records to the dispatcher."""

    def __init__(self, adapter: Any, on_work) -> None:
        self.adapter = adapter
        self.on_work = on_work          # callable(WorkItem) -> None, the existing intake path
        self.seen: set[tuple[str, str]] = set()

    async def __call__(self, event: Any) -> None:
        platform = getattr(self.adapter, "platform", "connector")
        item = record_from_event(platform, event)
        if item is None:
            return                       # no record: nothing to adjudicate, nothing to reply
        key = (platform, str(item.meta.get("message_id") or ""))
        if key[1]:                       # idempotent when the platform gives us an id
            if key in self.seen:
                return
            self.seen.add(key)
        self.on_work(item)

    def attach(self) -> None:
        self.adapter.set_message_handler(self)
