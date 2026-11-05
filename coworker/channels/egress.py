"""Outbound egress adapters — how a sealed result leaves the harness as JSON."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


class FileEgress:
    """Write each receipt as JSON: one file per reference plus an append-only log."""

    name = "file"

    def __init__(self, directory: str | Path | None = None) -> None:
        self.directory = Path(directory or os.environ.get("COWORKER_EGRESS_DIR")
                              or Path.home() / ".config/coworker/receipts")

    def deliver(self, receipt: dict[str, Any]) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        ref = (receipt.get("work_item") or {}).get("ref") or receipt.get("harness", {}).get("inbox_id", "receipt")
        safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in str(ref))
        text = json.dumps(receipt, indent=2, sort_keys=True)
        (self.directory / f"{safe}.json").write_text(text, encoding="utf-8")
        with open(self.directory / "receipts.jsonl", "a", encoding="utf-8") as log:
            log.write(json.dumps(receipt, sort_keys=True) + "\n")


class WebhookEgress:
    """POST the receipt as JSON to a configured endpoint."""

    name = "webhook"

    def __init__(self, url: str | None = None, *, token: str = "") -> None:
        self.url = url or os.environ.get("COWORKER_EGRESS_URL", "")
        self.token = token or os.environ.get("COWORKER_EGRESS_TOKEN", "")

    def deliver(self, receipt: dict[str, Any]) -> None:
        if not self.url:
            raise RuntimeError("no egress URL configured")
        import httpx
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        r = httpx.post(self.url, json=receipt, headers=headers, timeout=20)
        r.raise_for_status()
