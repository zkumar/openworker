"""F-010 ticket 02 — which sink gets a receipt, and how delivery retries.

Two gaps the spec names:
  1. `registry.deliver` fans every receipt to EVERY sink. A receipt belongs to one channel and one
     tenant; delivery follows a binding, not a broadcast.
  2. a failed delivery retried every 5s, forever. Delivery gets the same discipline as the run
     journal: attempts, a backoff window, and a dead letter after MAX_ATTEMPTS.
"""
from __future__ import annotations

import sqlite3
import time
from typing import Any, Optional

MAX_ATTEMPTS = 5


class BindingStore:
    """(channel, tenant) -> delivery target, e.g. `slack:C0123`."""

    def __init__(self, path: str) -> None:
        self.path = path
        with self._con() as con:
            con.execute("""CREATE TABLE IF NOT EXISTS egress_binding (
                channel TEXT NOT NULL, tenant TEXT NOT NULL, target TEXT NOT NULL, since TEXT NOT NULL,
                PRIMARY KEY (channel, tenant))""")

    def _con(self) -> sqlite3.Connection:
        con = sqlite3.connect(self.path, timeout=10, check_same_thread=False)
        con.execute("PRAGMA journal_mode=WAL")
        return con

    def set(self, channel: str, tenant: str, target: str) -> None:
        with self._con() as con:
            con.execute("INSERT INTO egress_binding VALUES (?,?,?,?) ON CONFLICT(channel,tenant)"
                        " DO UPDATE SET target=excluded.target",
                        (channel, tenant, target, time.strftime("%Y-%m-%dT%H:%M:%S")))

    def unset(self, channel: str, tenant: str) -> bool:
        with self._con() as con:
            return con.execute("DELETE FROM egress_binding WHERE channel=? AND tenant=?",
                               (channel, tenant)).rowcount == 1

    def resolve(self, channel: str, tenant: str) -> Optional[str]:
        with self._con() as con:
            row = con.execute("SELECT target FROM egress_binding WHERE channel=? AND tenant=?",
                              (channel, tenant)).fetchone()
        return row[0] if row else None


class DeliveryLedger:
    """Per (receipt, sink) attempts, error, next attempt time, and dead-letter state."""

    def __init__(self, path: str) -> None:
        self.path = path
        with self._con() as con:
            con.execute("""CREATE TABLE IF NOT EXISTS egress_attempt (
                receipt TEXT NOT NULL, sink TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0,
                error TEXT NOT NULL DEFAULT '', due REAL NOT NULL DEFAULT 0,
                state TEXT NOT NULL DEFAULT 'pending', PRIMARY KEY (receipt, sink))""")

    def _con(self) -> sqlite3.Connection:
        con = sqlite3.connect(self.path, timeout=10, check_same_thread=False)
        con.execute("PRAGMA journal_mode=WAL")
        return con

    def delivered(self, receipt: str, sink: str) -> None:
        with self._con() as con:
            con.execute("INSERT INTO egress_attempt (receipt, sink, state, due) VALUES (?,?, 'delivered', 0)"
                        " ON CONFLICT(receipt,sink) DO UPDATE SET state='delivered', error='', due=0",
                        (receipt, sink))

    def failed(self, receipt: str, sink: str, error: str) -> str:
        """Record a failure. Returns 'pending' (retry after backoff) or 'dead'."""
        with self._con() as con:
            row = con.execute("SELECT attempts FROM egress_attempt WHERE receipt=? AND sink=?",
                              (receipt, sink)).fetchone()
            attempts = (row[0] if row else 0) + 1
            if attempts >= MAX_ATTEMPTS:
                con.execute("INSERT INTO egress_attempt VALUES (?,?,?,?,0,'dead')"
                            " ON CONFLICT(receipt,sink) DO UPDATE SET attempts=?, error=?, state='dead'",
                            (receipt, sink, attempts, error[:400], attempts, error[:400]))
                return "dead"
            due = time.time() + min(60.0, 2.0 ** attempts)
            con.execute("INSERT INTO egress_attempt VALUES (?,?,?,?,?,'pending')"
                        " ON CONFLICT(receipt,sink) DO UPDATE SET attempts=?, error=?, due=?",
                        (receipt, sink, attempts, error[:400], due, attempts, error[:400], due))
            return "pending"

    def dead_letters(self) -> list[dict[str, Any]]:
        with self._con() as con:
            rows = con.execute("SELECT receipt, sink, attempts, error FROM egress_attempt"
                               " WHERE state='dead'").fetchall()
        return [{"receipt": r[0], "sink": r[1], "attempts": r[2], "error": r[3]} for r in rows]
