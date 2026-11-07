"""SQLite adapters for the rfsdk ports the harness Dispatcher binds (OW-F-014).

Spec: factory/specs/OW-F-014.md; register entry features/dispatcher-rfsdk-temporal.md phase 2.
The semantics each adapter must honour are rfsdk's own port contract suites
(`rfsdk_kernel.testing.contracts`); tests/test_rfsdk_adapters.py subclasses them.

All adapters share one WAL database under the state dir. Every method opens its own
connection: the Temporal activities run on executor threads, each driving its own event
loop, so no connection ever crosses a thread (the IngressQueue precedent, coworker/ingress.py).
This module is imported only on the OPENWORKER_EXECUTOR=temporal path; with the env unset,
rfsdk_kernel never enters sys.modules (tests/test_rfsdk_optin.py proves it).
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import sqlite3
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal

from rfsdk_kernel.caller import Caller
from rfsdk_kernel.envelope import SealedEnvelope, canonical_json
from rfsdk_kernel.errors import ActionContractError
from rfsdk_kernel.ports.types import Approved, ChangeEvent, Decision, Pending, VerifyReport
from rfsdk_kernel.registry import ActionSpec

_SCHEMA = """
CREATE TABLE IF NOT EXISTS rfsdk_evidence (
    chain      TEXT NOT NULL,
    seq        INTEGER NOT NULL,
    hash       TEXT NOT NULL,
    prev_hash  TEXT,
    body       TEXT NOT NULL,
    PRIMARY KEY (chain, seq)
);
CREATE TABLE IF NOT EXISTS rfsdk_approvals (
    key_hash   TEXT PRIMARY KEY,
    action     TEXT NOT NULL,
    requester  TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    consumed   INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS rfsdk_approval_policy (
    action  TEXT NOT NULL,
    org_id  TEXT NOT NULL,
    policy  TEXT NOT NULL,
    PRIMARY KEY (action, org_id)
);
CREATE TABLE IF NOT EXISTS rfsdk_changes (
    version        INTEGER PRIMARY KEY AUTOINCREMENT,
    source         TEXT NOT NULL,
    type           TEXT NOT NULL,
    key            TEXT,
    owner          TEXT,
    org_id         TEXT,
    resource_type  TEXT,
    resource_id    TEXT,
    request_source TEXT
);
"""


class _SqliteBase:
    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        con = self._con()
        try:
            con.executescript(_SCHEMA)
        finally:
            con.close()

    def _con(self) -> sqlite3.Connection:
        con = sqlite3.connect(self.path, timeout=10)
        con.execute("PRAGMA journal_mode=WAL")
        return con


def _content_without_hash(envelope: SealedEnvelope) -> dict:
    content = dataclasses.asdict(envelope)
    del content["hash"]
    return content


class SqliteEvidenceStore(_SqliteBase):
    """Append-only, hash-chained: a tampered seal refuses, a stale prev_hash conflicts."""

    async def append(self, envelope: SealedEnvelope) -> None:
        recomputed = hashlib.sha256(canonical_json(_content_without_hash(envelope))).hexdigest()
        if recomputed != envelope.hash:
            raise ActionContractError(
                "envelope hash does not match its sealed content",
                error_code="invalid_envelope", status_code=422)
        con = self._con()
        try:
            con.execute("BEGIN IMMEDIATE")
            row = con.execute(
                "SELECT hash, seq FROM rfsdk_evidence WHERE chain=? ORDER BY seq DESC LIMIT 1",
                (envelope.chain,)).fetchone()
            head, seq = (row[0], row[1]) if row else (None, -1)
            if envelope.prev_hash != head:
                con.rollback()
                raise ActionContractError(
                    "prev_hash is not the chain head (another envelope landed first)",
                    error_code="chain_conflict", status_code=409)
            con.execute(
                "INSERT INTO rfsdk_evidence(chain, seq, hash, prev_hash, body) VALUES(?,?,?,?,?)",
                (envelope.chain, seq + 1, envelope.hash, envelope.prev_hash,
                 json.dumps(dataclasses.asdict(envelope))))
            con.commit()
        finally:
            con.close()

    async def head(self, chain: str) -> str | None:
        con = self._con()
        try:
            row = con.execute(
                "SELECT hash FROM rfsdk_evidence WHERE chain=? ORDER BY seq DESC LIMIT 1",
                (chain,)).fetchone()
            return row[0] if row else None
        finally:
            con.close()

    async def verify(self, chain: str) -> VerifyReport:
        con = self._con()
        try:
            rows = con.execute(
                "SELECT hash, prev_hash, body FROM rfsdk_evidence WHERE chain=? ORDER BY seq",
                (chain,)).fetchall()
        finally:
            con.close()
        prev: str | None = None
        for stored_hash, stored_prev, body in rows:
            content = json.loads(body)
            claimed = content.pop("hash", None)
            recomputed = hashlib.sha256(canonical_json(content)).hexdigest()
            if (recomputed != claimed or claimed != stored_hash
                    or content.get("prev_hash") != prev or stored_prev != prev):
                return VerifyReport(chain=chain, ok=False, length=len(rows),
                                    broken_at=stored_hash)
            prev = stored_hash
        return VerifyReport(chain=chain, ok=True, length=len(rows), broken_at=None)

    def chain_envelopes(self, chain: str) -> list[dict]:
        """The stored envelopes of one chain, oldest first (a read for proofs and tests)."""
        con = self._con()
        try:
            rows = con.execute(
                "SELECT body FROM rfsdk_evidence WHERE chain=? ORDER BY seq", (chain,)).fetchall()
            return [json.loads(body) for (body,) in rows]
        finally:
            con.close()


def _caller_json(caller: Caller) -> str:
    return json.dumps({
        "principal_id": caller.principal_id, "email": caller.email, "org_id": caller.org_id,
        "org_role": caller.org_role, "app_roles": sorted(caller.app_roles),
        "surface": caller.surface, "actor_kind": caller.actor_kind,
        "thread_id": caller.thread_id, "turn_id": caller.turn_id, "run_id": caller.run_id,
        "authenticated_at": caller.authenticated_at.isoformat()})


def _caller_from_json(raw: str) -> Caller:
    d = json.loads(raw)
    return Caller(
        principal_id=d["principal_id"], email=d["email"], org_id=d["org_id"],
        org_role=d["org_role"], app_roles=frozenset(d["app_roles"]), surface=d["surface"],
        actor_kind=d["actor_kind"], thread_id=d["thread_id"], turn_id=d["turn_id"],
        run_id=d["run_id"], authenticated_at=datetime.fromisoformat(d["authenticated_at"]))


class SqliteApprovalStore(_SqliteBase):
    """Single use, second person, same org, TTL. Present because the Dispatcher requires the
    binding; harness actions are needs_approval=False, so fabric part11 signoff stays the only
    human gate (OW-F-014 scope note)."""

    async def request(self, key_hash: str, action: str, requester: Caller,
                      ttl: timedelta) -> Pending:
        expires_at = datetime.now(UTC) + ttl
        con = self._con()
        try:
            with con:
                con.execute(
                    "INSERT OR REPLACE INTO rfsdk_approvals"
                    "(key_hash, action, requester, expires_at, consumed) VALUES(?,?,?,?,0)",
                    (key_hash, action, _caller_json(requester), expires_at.isoformat()))
        finally:
            con.close()
        return Pending(key_hash=key_hash, action=action, requester=requester,
                       expires_at=expires_at)

    async def consume(self, key_hash: str, approver: Caller) -> Approved:
        con = self._con()
        try:
            con.execute("BEGIN IMMEDIATE")
            row = con.execute(
                "SELECT action, requester, expires_at, consumed FROM rfsdk_approvals "
                "WHERE key_hash=?", (key_hash,)).fetchone()
            if row is None:
                con.rollback()
                raise ActionContractError(f"no approval is pending under {key_hash!r}",
                                          error_code="approval_refused", status_code=403)
            action, requester_raw, expires_raw, consumed = row
            requester = _caller_from_json(requester_raw)
            if consumed:
                con.rollback()
                raise ActionContractError("the approval was already consumed (single use)",
                                          error_code="approval_refused", status_code=403)
            if datetime.now(UTC) > datetime.fromisoformat(expires_raw):
                con.rollback()
                raise ActionContractError("the approval expired",
                                          error_code="approval_refused", status_code=403)
            if approver.principal_id == requester.principal_id:
                con.rollback()
                raise ActionContractError("the approver is never the requester (four eyes)",
                                          error_code="approval_refused", status_code=403)
            if approver.org_id != requester.org_id:
                con.rollback()
                raise ActionContractError("the approver is outside the requester's org",
                                          error_code="approval_refused", status_code=403)
            con.execute("UPDATE rfsdk_approvals SET consumed=1 WHERE key_hash=?", (key_hash,))
            con.commit()
        finally:
            con.close()
        return Approved(key_hash=key_hash, action=action, requester=requester, approver=approver)

    async def policy(self, action: str, org_id: str) -> Literal["ask", "always_allow"]:
        con = self._con()
        try:
            row = con.execute(
                "SELECT policy FROM rfsdk_approval_policy WHERE action=? AND org_id=?",
                (action, org_id)).fetchone()
            return "always_allow" if row and row[0] == "always_allow" else "ask"
        finally:
            con.close()


class SqliteChangeBus(_SqliteBase):
    """Monotonic versions; `since` is scoped to the caller's org; unscoped reaches nobody."""

    async def emit(self, event: ChangeEvent) -> int:
        con = self._con()
        try:
            with con:
                cur = con.execute(
                    "INSERT INTO rfsdk_changes(source, type, key, owner, org_id, resource_type,"
                    " resource_id, request_source) VALUES(?,?,?,?,?,?,?,?)",
                    (event.source, event.type, event.key, event.owner, event.org_id,
                     event.resource_type, event.resource_id, event.request_source))
                return int(cur.lastrowid or 0)
        finally:
            con.close()

    async def since(self, version: int, caller: Caller) -> list[ChangeEvent]:
        if caller.org_id is None:
            return []                                    # fail closed: no org, no changes
        con = self._con()
        try:
            rows = con.execute(
                "SELECT version, source, type, key, owner, org_id, resource_type, resource_id,"
                " request_source FROM rfsdk_changes WHERE version>? AND org_id=? ORDER BY version",
                (version, caller.org_id)).fetchall()
        finally:
            con.close()
        return [ChangeEvent(version=v, source=s, type=t, key=k, owner=o, org_id=org,
                            resource_type=rt, resource_id=ri, request_source=rs)
                for (v, s, t, k, o, org, rt, ri, rs) in rows]


class TenantPolicy:
    """Tenant isolation at the dispatch boundary (workspace invariant, OW-F-014 escalation).

    The caller's org_id IS the work item's tenant; a call naming another tenant, or a caller
    without one, is denied. Stateless and fail closed."""

    async def check(self, action: ActionSpec, caller: Caller,
                    args: Mapping[str, object]) -> Decision:
        if caller.org_id is None:
            return Decision(allowed=False, reason="the caller has no tenant (fail closed)")
        named = args.get("tenant")
        if named is not None and named != caller.org_id:
            return Decision(
                allowed=False,
                reason=f"the call names tenant {named!r} but the caller is scoped to "
                       f"{caller.org_id!r}")
        return Decision(allowed=True,
                        reason=f"tenant-scoped call within {caller.org_id!r}")
