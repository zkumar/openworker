"""The generic webhook channel — any system that can POST JSON can deliver work."""

from __future__ import annotations

from typing import Any

from .base import WorkItem


class WebhookChannel:
    """`POST /v1/channels/webhook {"record": {...}}` — or the payload itself is the record."""

    name = "webhook"

    def __init__(self, name: str = "webhook") -> None:
        self.name = name

    def ingest(self, payload: dict[str, Any]) -> WorkItem | None:
        if not isinstance(payload, dict):
            return None
        record = payload.get("record") if isinstance(payload.get("record"), dict) else payload
        if not record:
            return None
        meta = {k: v for k, v in payload.items() if k != "record"}
        return WorkItem(channel=self.name, record=dict(record), meta=meta)
