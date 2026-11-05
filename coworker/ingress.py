"""Durable ingress — accept work BEFORE processing it, so a crash or restart loses nothing.

Today the HTTP handler dispatches inline: if the process dies (or the fabric is down) between
"request accepted" and "run started", the work item vanishes. This queue fixes the order:

    accept → persist the raw payload (committed) → respond → dispatch from the queue

A record that was accepted therefore always has a row, and the consumer retries anything a
restart interrupted. A producer that cannot reach the harness at all can drop a JSON file in the
channel's spool directory instead (see coworker/channels/spool.py).
"""

from __future__ import annotations

import json
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any, Optional

MAX_ATTEMPTS = 8


class IngressQueue:
    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        with self._con() as con:
            con.execute("""
                CREATE TABLE IF NOT EXISTS ingress_event (
                    id           TEXT PRIMARY KEY,
                    channel      TEXT NOT NULL,
                    payload      TEXT NOT NULL,
                    state        TEXT NOT NULL DEFAULT 'pending',   -- pending | dispatched | failed
                    session_id   TEXT NOT NULL DEFAULT '',
                    attempts     INTEGER NOT NULL DEFAULT 0,
                    error        TEXT NOT NULL DEFAULT '',
                    due          REAL NOT NULL DEFAULT 0,
                    received_at  TEXT NOT NULL,
                    dispatched_at TEXT NOT NULL DEFAULT ''
                )""")
            con.execute("CREATE INDEX IF NOT EXISTS idx_ing_state ON ingress_event(state, due)")

    def _con(self) -> sqlite3.Connection:
        con = sqlite3.connect(self.path, timeout=15, check_same_thread=False)
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("PRAGMA synchronous=FULL")
        return con

    def enqueue(self, channel: str, payload: dict[str, Any]) -> str:
        event_id = uuid.uuid4().hex
        with self._con() as con:
            con.execute(
                "INSERT INTO ingress_event (id, channel, payload, received_at) VALUES (?,?,?,?)",
                (event_id, channel, json.dumps(payload), time.strftime("%Y-%m-%dT%H:%M:%S")),
            )
        return event_id

    def mark_dispatched(self, event_id: str, session_id: str) -> None:
        with self._con() as con:
            con.execute(
                "UPDATE ingress_event SET state='dispatched', session_id=?, error='',"
                " dispatched_at=? WHERE id=?",
                (session_id, time.strftime("%Y-%m-%dT%H:%M:%S"), event_id),
            )

    def mark_failed(self, event_id: str, error: str) -> str:
        """Backoff, then give up. Returns the resulting state."""
        with self._con() as con:
            row = con.execute("SELECT attempts FROM ingress_event WHERE id=?", (event_id,)).fetchone()
            attempts = (row[0] if row else 0) + 1
            if attempts >= MAX_ATTEMPTS:
                con.execute("UPDATE ingress_event SET state='failed', attempts=?, error=?, due=0"
                            " WHERE id=?", (attempts, error[:500], event_id))
                return "failed"
            con.execute("UPDATE ingress_event SET attempts=?, error=?, due=? WHERE id=?",
                        (attempts, error[:500], time.time() + min(60.0, 2.0 ** attempts), event_id))
            return "pending"

    def due(self, limit: int = 20) -> list[dict[str, Any]]:
        with self._con() as con:
            rows = con.execute(
                "SELECT id, channel, payload, attempts FROM ingress_event"
                " WHERE state='pending' AND due<=? ORDER BY due LIMIT ?",
                (time.time(), limit),
            ).fetchall()
        return [{"id": r[0], "channel": r[1], "payload": json.loads(r[2]), "attempts": r[3]} for r in rows]

    def stats(self) -> dict[str, int]:
        with self._con() as con:
            return dict(con.execute("SELECT state, count(*) FROM ingress_event GROUP BY state").fetchall())

    def get(self, event_id: str) -> Optional[dict[str, Any]]:
        with self._con() as con:
            r = con.execute("SELECT id, channel, payload, state, session_id, attempts, error"
                            " FROM ingress_event WHERE id=?", (event_id,)).fetchone()
        if r is None:
            return None
        return {"id": r[0], "channel": r[1], "payload": json.loads(r[2]), "state": r[3],
                "session_id": r[4], "attempts": r[5], "error": r[6]}
