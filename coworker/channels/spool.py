"""Offline ingress: drop a JSON file and it is ingested when the harness can run.

A producer that cannot reach the HTTP endpoint (harness down, network blip, batch loader) writes
`<spool>/<channel>/<name>.json`. The consumer ingests each file exactly once: success moves it to
`processed/`, a refusal to `rejected/`, an unexpected error to `failed/`.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class FileSpool:
    name = "spool"
    # These are the spool's own output buckets, not channels — scanning them re-ingests files.
    MANAGED = frozenset({"processed", "failed", "rejected"})

    def __init__(self, directory: str | Path) -> None:
        self.directory = Path(directory)

    def poll(self) -> list[tuple[str, dict[str, Any], Path]]:
        """Every waiting payload as (channel, payload, file). Channel = subdirectory name."""
        if not self.directory.exists():
            return []
        found: list[tuple[str, dict[str, Any], Path]] = []
        for channel_dir in sorted(
            p for p in self.directory.iterdir()
            if p.is_dir() and p.name not in self.MANAGED
        ):
            for path in sorted(channel_dir.glob("*.json")):
                try:
                    payload = json.loads(path.read_text(encoding="utf-8"))
                except Exception:
                    self._move(path, "failed")
                    continue
                found.append((channel_dir.name, payload, path))
        return found

    def _move(self, path: Path, bucket: str) -> None:
        target_dir = self.directory / bucket
        target_dir.mkdir(parents=True, exist_ok=True)
        try:
            path.replace(target_dir / path.name)
        except OSError:
            pass

    def done(self, path: Path) -> None:
        self._move(path, "processed")

    def reject(self, path: Path) -> None:
        self._move(path, "rejected")

    def fail(self, path: Path) -> None:
        self._move(path, "failed")
