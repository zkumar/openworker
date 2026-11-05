"""API keys with tenants — replaces one shared static token.

Properties the static token did not have:
  - keys are stored HASHED (a database leak does not leak a usable credential),
  - every key names a tenant, so reads can be scoped,
  - keys are revocable, and rotation is "mint new, revoke old" with both valid in between,
  - usage is recorded (last_used_at) so a stale key can be found and retired.

A key looks like `ow_<40 hex>` and is shown ONCE at mint time.
"""

from __future__ import annotations

import hashlib
import secrets
import sqlite3
import time
import uuid
from typing import Any, Optional

DEFAULT_TENANT = "default"


def _hash(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


class KeyStore:
    def __init__(self, path: str) -> None:
        self.path = path
        with self._con() as con:
            con.execute("""
                CREATE TABLE IF NOT EXISTS api_key (
                    id           TEXT PRIMARY KEY,
                    tenant       TEXT NOT NULL,
                    label        TEXT NOT NULL DEFAULT '',
                    key_hash     TEXT NOT NULL UNIQUE,
                    created_at   TEXT NOT NULL,
                    revoked_at   TEXT NOT NULL DEFAULT '',
                    last_used_at TEXT NOT NULL DEFAULT '',
                    role         TEXT NOT NULL DEFAULT 'agent',
                    expires_at   TEXT NOT NULL DEFAULT ''
                )""")
            con.execute("CREATE INDEX IF NOT EXISTS idx_key_hash ON api_key(key_hash)")
            # migration for databases created before roles/expiry existed
            cols = {r[1] for r in con.execute("PRAGMA table_info(api_key)")}
            if "role" not in cols:
                con.execute("ALTER TABLE api_key ADD COLUMN role TEXT NOT NULL DEFAULT 'agent'")
            if "expires_at" not in cols:
                con.execute("ALTER TABLE api_key ADD COLUMN expires_at TEXT NOT NULL DEFAULT ''")

    def _con(self) -> sqlite3.Connection:
        con = sqlite3.connect(self.path, timeout=15, check_same_thread=False)
        con.execute("PRAGMA journal_mode=WAL")
        return con

    # -- lifecycle -------------------------------------------------------------
    def mint(self, tenant: str = DEFAULT_TENANT, label: str = "",
             role: str = "agent", ttl_days: int | None = None) -> tuple[str, str]:
        """Create a key. Returns (plaintext, id) — the plaintext is never recoverable again."""
        key = "ow_" + secrets.token_hex(20)
        key_id = uuid.uuid4().hex
        with self._con() as con:
            expires = ""
            if ttl_days:
                expires = time.strftime("%Y-%m-%dT%H:%M:%S",
                                        time.localtime(time.time() + ttl_days * 86400))
            con.execute(
                "INSERT INTO api_key (id, tenant, label, key_hash, created_at, role, expires_at)"
                " VALUES (?,?,?,?,?,?,?)",
                (key_id, tenant or DEFAULT_TENANT, label, _hash(key),
                 time.strftime("%Y-%m-%dT%H:%M:%S"), role if role in ("admin", "agent") else "agent",
                 expires),
            )
        return key, key_id

    def adopt(self, key: str, tenant: str = DEFAULT_TENANT,
              label: str = "legacy env token", role: str = "admin") -> Optional[str]:
        """Import an existing (env) token so an upgrade does not lock anyone out."""
        if not key:
            return None
        with self._con() as con:
            row = con.execute("SELECT id FROM api_key WHERE key_hash=?", (_hash(key),)).fetchone()
            if row:
                # A key imported from the environment is the machine's operator credential, so it
                # must carry the admin role even if it was created before roles existed.
                con.execute("UPDATE api_key SET role=? WHERE id=?", (role, row[0]))
                return row[0]
            key_id = uuid.uuid4().hex
            con.execute(
                "INSERT INTO api_key (id, tenant, label, key_hash, created_at, role)"
                " VALUES (?,?,?,?,?,?)",
                (key_id, tenant, label, _hash(key), time.strftime("%Y-%m-%dT%H:%M:%S"), role),
            )
        return key_id

    def revoke(self, key_id: str) -> bool:
        with self._con() as con:
            cur = con.execute("UPDATE api_key SET revoked_at=? WHERE id=? AND revoked_at=''",
                              (time.strftime("%Y-%m-%dT%H:%M:%S"), key_id))
            return cur.rowcount == 1

    def list(self) -> list[dict[str, Any]]:
        """Never returns a key or its hash — only what an operator needs to decide."""
        now = time.strftime("%Y-%m-%dT%H:%M:%S")
        with self._con() as con:
            rows = con.execute(
                "SELECT id, tenant, label, created_at, revoked_at, last_used_at, role, expires_at"
                " FROM api_key ORDER BY created_at DESC").fetchall()
        return [{"id": r[0], "tenant": r[1], "label": r[2], "created_at": r[3],
                 "revoked": bool(r[4]), "last_used_at": r[5], "role": r[6],
                 "expires_at": r[7] or None,
                 "expired": bool(r[7]) and r[7] <= now} for r in rows]

    def authenticate(self, key: str) -> Optional[dict[str, Any]]:
        """(tenant, role) for a live key. Revoked and expired keys never authenticate."""
        if not key:
            return None
        now = time.strftime("%Y-%m-%dT%H:%M:%S")
        with self._con() as con:
            row = con.execute(
                "SELECT id, tenant, role, expires_at FROM api_key"
                " WHERE key_hash=? AND revoked_at=''", (_hash(key),)).fetchone()
            if row is None:
                return None
            if row[3] and row[3] <= now:          # expired
                return None
            con.execute("UPDATE api_key SET last_used_at=? WHERE id=?", (now, row[0]))
        return {"tenant": row[1], "role": row[2] or "agent"}

    def verify(self, key: str) -> Optional[str]:
        """The tenant a key belongs to, or None."""
        found = self.authenticate(key)
        return found["tenant"] if found else None

    def count(self) -> int:
        with self._con() as con:
            return con.execute("SELECT count(*) FROM api_key WHERE revoked_at=''").fetchone()[0]
