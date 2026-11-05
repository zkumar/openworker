"""The channel registry — the one place channels are added or removed."""

from __future__ import annotations

import os

from .base import Channel, WorkItem

_CHANNELS: dict[str, Channel] = {}
_EGRESS: dict[str, Any] = {}


def register(channel: Channel) -> None:
    _CHANNELS[channel.name] = channel


def unregister(name: str) -> bool:
    return _CHANNELS.pop(name, None) is not None


def get(name: str) -> Channel | None:
    return _CHANNELS.get(name)


def names() -> list[str]:
    return sorted(_CHANNELS)


def ingest(name: str, payload: dict) -> WorkItem | None:
    channel = get(name)
    if channel is None:
        raise KeyError(f"unknown channel {name!r}")
    return channel.ingest(payload)


def register_egress(egress: Any) -> None:
    _EGRESS[egress.name] = egress


def egress_names() -> list[str]:
    return sorted(_EGRESS)


def deliver(receipt: dict) -> list[str]:
    """Fan a receipt out to every egress. Returns the names that FAILED (for retry)."""
    failed: list[str] = []
    for name, sink in _EGRESS.items():
        try:
            sink.deliver(receipt)
        except Exception:
            failed.append(name)
    return failed


def install_defaults() -> None:
    """Register the built-in channels once (idempotent)."""
    from .egress import FileEgress, WebhookEgress
    from .webhook import WebhookChannel

    if get("webhook") is None:
        register(WebhookChannel())
    if "file" not in _EGRESS:
        register_egress(FileEgress())
    if os.environ.get("COWORKER_EGRESS_URL") and "webhook" not in _EGRESS:
        register_egress(WebhookEgress())
