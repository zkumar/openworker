"""The channel registry — the one place channels are added or removed."""

from __future__ import annotations

from .base import Channel, WorkItem

_CHANNELS: dict[str, Channel] = {}


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


def install_defaults() -> None:
    """Register the built-in channels once (idempotent)."""
    from .webhook import WebhookChannel

    if get("webhook") is None:
        register(WebhookChannel())
