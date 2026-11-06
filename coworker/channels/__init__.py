"""Inbound channels (A4): work items enter the harness here, and only here."""
from .base import Channel, WorkItem
from .registry import get, ingest, install_defaults, names, register, unregister

__all__ = ["Channel", "WorkItem", "get", "ingest", "install_defaults", "names", "register", "unregister"]
