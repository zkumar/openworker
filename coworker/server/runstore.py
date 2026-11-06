"""Durable run state — the journal a restart reads instead of process memory.

Shaped after the DeepSeek Harness `effect` table: one row per run keyed by identity, with a
retry counter, a next-attempt time, and a generation used to fence two writers apart.

  state='dispatched'  → the run is owned by whoever holds the current generation
  state='gate'        → parked for a human signature (no retry: it is waiting, not broken)
  state='sealed'      → finished
  state='failed'      → retries exhausted
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Optional

MAX_ATTEMPTS = 5


class RunStore:
    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        self._lock = threading.Lock()
        con = self._con()
        with con:
            con.execute("""
                CREATE TABLE IF NOT EXISTS run_effect (
                    run_key     TEXT PRIMARY KEY,
                    session_id  TEXT NOT NULL DEFAULT '',
                    fabric_run  TEXT NOT NULL DEFAULT '',
                    agent       TEXT NOT NULL DEFAULT '',
                    record      TEXT NOT NULL DEFAULT '{}',
                    state       TEXT NOT NULL DEFAULT 'dispatched',
                    generation  INTEGER NOT NULL DEFAULT 0,
                    attempts    INTEGER NOT NULL DEFAULT 0,
                    error       TEXT NOT NULL DEFAULT '',
                    due         REAL NOT NULL DEFAULT 0,
                    since       TEXT NOT NULL DEFAULT ''
                )""")
        con.close()

    def _con(self) -> sqlite3.Connection:
        con = sqlite3.connect(self.path, check_same_thread=False, timeout=10)
        con.execute("PRAGMA journal_mode=WAL")
        return con

    # -- lifecycle -------------------------------------------------------------
    def begin(self, run_key: str, session_id: str, record: dict) -> int:
        with self._lock, self._con() as con:
            con.execute(
                "INSERT OR REPLACE INTO run_effect"
                "(run_key, session_id, record, state, generation, attempts, error, due, since)"
                " VALUES(?,?,?,'dispatched',1,0,'',?,?)",
                (run_key, session_id, json.dumps(record), time.time(), _now()))
            return 1

    def set_fabric_run(self, run_key: str, fabric_run: str, agent: str) -> None:
        with self._lock, self._con() as con:
            con.execute("UPDATE run_effect SET fabric_run=?, agent=? WHERE run_key=?",
                        (fabric_run, agent, run_key))

    def touch(self, run_key: str) -> None:
        """Heartbeat: push `due` out so a long healthy run is not reclaimed."""
        with self._lock, self._con() as con:
            con.execute("UPDATE run_effect SET due=? WHERE run_key=? AND state='dispatched'",
                        (time.time() + 60, run_key))

    def finish(self, run_key: str, state: str = "sealed") -> None:
        with self._lock, self._con() as con:
            con.execute("UPDATE run_effect SET state=?, error='', due=0 WHERE run_key=?",
                        (state, run_key))

    def fail(self, run_key: str, error: str) -> str:
        """Record a failure. Returns the new state: 'dispatched' to retry, else 'failed'."""
        with self._lock, self._con() as con:
            row = con.execute("SELECT attempts FROM run_effect WHERE run_key=?", (run_key,)).fetchone()
            attempts = (row[0] if row else 0) + 1
            if attempts >= MAX_ATTEMPTS:
                con.execute("UPDATE run_effect SET state='failed', attempts=?, error=?, due=0"
                            " WHERE run_key=?", (attempts, error, run_key))
                return "failed"
            backoff = min(60.0, 2.0 ** attempts)          # 2s, 4s, 8s, 16s …
            con.execute("UPDATE run_effect SET attempts=?, error=?, due=? WHERE run_key=?",
                        (attempts, error, time.time() + backoff, run_key))
            return "dispatched"

    # -- claiming --------------------------------------------------------------
    def due(self) -> list[dict[str, Any]]:
        """Runs a restart should pick up: still dispatched, and past their next-attempt time."""
        with self._lock, self._con() as con:
            rows = con.execute(
                "SELECT run_key, session_id, fabric_run, agent, record, attempts, generation"
                " FROM run_effect WHERE state='dispatched' AND due<=?"
                " ORDER BY due", (time.time(),)).fetchall()
        return [{"run_key": r[0], "session_id": r[1], "fabric_run": r[2], "agent": r[3],
                 "record": json.loads(r[4] or "{}"), "attempts": r[5], "generation": r[6]}
                for r in rows]

    def claim(self, run_key: str, generation: int) -> Optional[int]:
        """Fence a stale owner out: succeeds only if the generation is unchanged."""
        with self._lock, self._con() as con:
            cur = con.execute("UPDATE run_effect SET generation=generation+1, due=?"
                              " WHERE run_key=? AND generation=? AND state='dispatched'",
                              (time.time() + 60, run_key, generation))
            if cur.rowcount != 1:
                return None
            return generation + 1

    def stats(self) -> dict[str, int]:
        with self._lock, self._con() as con:
            return dict(con.execute(
                "SELECT state, count(*) FROM run_effect GROUP BY state").fetchall())

    def get(self, run_key: str) -> Optional[dict[str, Any]]:
        with self._lock, self._con() as con:
            r = con.execute("SELECT run_key, session_id, fabric_run, agent, record, state,"
                            " generation, attempts, error, due FROM run_effect WHERE run_key=?",
                            (run_key,)).fetchone()
        if r is None:
            return None
        return {"run_key": r[0], "session_id": r[1], "fabric_run": r[2], "agent": r[3],
                "record": json.loads(r[4] or "{}"), "state": r[5], "generation": r[6],
                "attempts": r[7], "error": r[8], "due": r[9]}


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")
