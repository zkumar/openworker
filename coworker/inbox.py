"""The Inbox — the canonical, cross-session human-attention queue.

While a user works in one session (or is away with a session running Unattended), the Inbox
holds what other agents need from them: an **approval**, a **question**, or a **notification**.
It is the store of record; messaging connectors / mobile (Phase 3) are transports of the same
items.

Item state machine (the anti-race contract): each item is ``pending → resolved``, resolved
**once**, idempotent + first-responder-wins — so answering from any surface (in-app, Slack, the
composer after resuming) is safe. ``inbox_approver`` turns a permission request into an item and
suspends the agent until that item is resolved.
"""

from __future__ import annotations

import sqlite3

import os

import asyncio
import json
import threading
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

KIND_APPROVAL = "approval"
KIND_QUESTION = "question"
KIND_NOTIFICATION = "notification"
KIND_DIRECTORY = "directory"  # agent asks to be granted a folder
KIND_PLAN = "plan"  # agent presents a plan for approval
KIND_TOOL = "tool"  # agent asks for a missing CLI tool to be installed

STATE_PENDING = "pending"
STATE_RESOLVED = "resolved"

# Where a pending prompt surfaces. INLINE = an attended session answers it in the composer (parked
# server-side, redelivered on reconnect, never in the cross-session list). INBOX = the user set the
# session Unattended, so it joins the cross-session Inbox queue. Either way it's the same parked,
# awaitable, resolve-from-anywhere record — only the visibility differs.
VIS_INLINE = "inline"
VIS_INBOX = "inbox"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def args_preview(arguments: Optional[dict], *, limit: int = 240) -> str:
    """A compact one-line summary of a tool call's arguments, for an approval card body (so a
    mirrored 'Run `write_file`?' shows *what* — path/content — not just the tool name).
    """
    parts: list[str] = []
    for k, v in (arguments or {}).items():
        s = v if isinstance(v, str) else json.dumps(v, default=str, ensure_ascii=False)
        s = " ".join(str(s).split())  # collapse whitespace/newlines
        if len(s) > 80:
            s = s[:79] + "…"
        parts.append(f"{k}: {s}")
    out = " · ".join(parts)
    return out[: limit - 1] + "…" if len(out) > limit else out


@dataclass
class InboxItem:
    id: str
    session_id: str
    kind: str
    title: str
    body: str = ""
    state: str = STATE_PENDING
    resolution: Optional[str] = (
        None  # approval: "allow"/"deny"/"always"; question: answer text
    )
    inbox: str = "default"  # named inbox / delivery binding (Phase 3 routing)
    created_at: str = field(default_factory=_now)
    resolved_at: Optional[str] = None
    visibility: str = VIS_INBOX  # inline (attended) vs inbox (unattended)
    # The tool call this prompt is blocking (durable resume: persisted so a restart can rebuild the
    # suspension and continue the turn). Makes an item idempotent by (session_id, tool_call_id).
    tool_call_id: Optional[str] = None
    # Question metadata (ask_user): optional quick-reply choices + a free-text escape, mirroring
    # the structured-but-always-answerable shape of Claude Code's AskUserQuestion.
    # An option is a plain string OR a rich {label, description, recommended, preview} object
    # (OPE-51); old persisted items hold strings and stay valid.
    options: list = field(default_factory=list)
    allow_text: bool = (
        True  # accept a typed answer even when options exist (the "Other" escape)
    )
    multi: bool = False  # allow choosing more than one option
    header: str = ""  # short chip label for the card ("Region")
    # Grouped form (OPE-51): up to 4 {question, header, options, allow_text, multi} entries
    # rendered as a stepper. When non-empty the singular title/options fields above still hold
    # the FIRST question (so old surfaces and channel mirrors degrade to something sensible),
    # and the resolution is a JSON object string keyed by header-or-question.
    questions: list[dict] = field(default_factory=list)
    # Kind-specific payload (directory: suggested path/writable; plan: the plan text; …).
    data: dict[str, Any] = field(default_factory=dict)


class InboxStore:
    def __init__(self, path: Optional[str | Path] = None) -> None:
        self.path = Path(path) if path else None
        # Work items live in SQLite (WAL, transactional) next to the old JSON file. The JSON
        # rewrite-per-step could be corrupted by a crash mid-write and had no cross-process
        # safety at all; SQLite gives atomic commits and a single-writer lock.
        self.db_path = (
            self.path.with_name("inbox.sqlite") if self.path else None
        )
        self._lock = threading.Lock()
        self._items: dict[str, InboxItem] = {}
        self._waiters: dict[str, asyncio.Event] = {}
        self._load()

    # -- persistence ------------------------------------------------------------
    def _con(self) -> "sqlite3.Connection":
        con = sqlite3.connect(str(self.db_path), timeout=15, check_same_thread=False)
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("PRAGMA synchronous=FULL")
        return con

    def _init_db(self) -> None:
        with self._con() as con:
            con.execute("""
                CREATE TABLE IF NOT EXISTS inbox_item (
                    id          TEXT PRIMARY KEY,
                    session_id  TEXT NOT NULL,
                    kind        TEXT NOT NULL,
                    state       TEXT NOT NULL,
                    created_at  TEXT NOT NULL,
                    payload     TEXT NOT NULL
                )""")
            con.execute("CREATE INDEX IF NOT EXISTS idx_item_session ON inbox_item(session_id)")
            con.execute("CREATE INDEX IF NOT EXISTS idx_item_state ON inbox_item(state)")

    def _load(self) -> None:
        if not self.db_path:
            return
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
        with self._con() as con:
            rows = con.execute("SELECT payload FROM inbox_item").fetchall()
        for (payload,) in rows:
            try:
                item = InboxItem(**json.loads(payload))
            except Exception:
                continue
            self._items[item.id] = item
        if self._items:
            return                      # once SQLite holds items, it is authoritative
        # First run on this machine: import a legacy JSON inbox once, then leave it as a backup.
        if self.path and self.path.is_file():
            try:
                if (self.path.stat().st_mode & 0o077):     # tighten a pre-existing loose file
                    os.chmod(self.path, 0o600)
            except OSError:
                pass
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
            except Exception:
                data = {}
            for raw in data.get("items", []):
                try:
                    self._items[InboxItem(**raw).id] = InboxItem(**raw)
                except Exception:
                    continue
            if self._items:
                self._save()

    def _save(self) -> None:
        """Commit every item in one transaction.

        SQLite gives what the JSON rewrite could not: an all-or-nothing commit (a crash cannot
        leave a truncated inbox) and file mode 0600 by default. Two processes can still race on
        the same row — WAL keeps the database consistent, but true multi-writer correctness needs
        row-level updates, which is a separate step.
        """
        if not self.db_path:
            return
        rows = [
            (i.id, i.session_id, i.kind, i.state, i.created_at, json.dumps(asdict(i)))
            for i in self._items.values()
        ]
        keep = tuple(self._items.keys())
        with self._con() as con:
            con.executemany(
                """INSERT INTO inbox_item (id, session_id, kind, state, created_at, payload)
                   VALUES (?, ?, ?, ?, ?, ?)
                   ON CONFLICT(id) DO UPDATE SET
                     session_id = excluded.session_id, kind = excluded.kind,
                     state = excluded.state, created_at = excluded.created_at,
                     payload = excluded.payload""",
                rows,
            )
            if keep:
                con.execute(
                    f"DELETE FROM inbox_item WHERE id NOT IN ({','.join('?' * len(keep))})", keep
                )
            else:
                con.execute("DELETE FROM inbox_item")
        try:
            os.chmod(self.db_path, 0o600)
        except OSError:
            pass

    # -- adding -----------------------------------------------------------------
    def add(
        self,
        session_id: str,
        kind: str,
        title: str,
        *,
        body: str = "",
        inbox: str = "default",
        visibility: str = VIS_INBOX,
        data: Optional[dict[str, Any]] = None,
        options=None,
        allow_text: bool = True,
        multi: bool = False,
        header: str = "",
        questions=None,
        tool_call_id: Optional[str] = None,
    ) -> InboxItem:
        # Idempotent by (session_id, tool_call_id): a durable resume re-raises the same prompt, and
        # must reuse the existing (possibly already-resolved) item rather than re-prompt.
        if tool_call_id:
            existing = self.for_tool_call(session_id, tool_call_id)
            if existing is not None:
                return existing
        item = InboxItem(
            id=uuid.uuid4().hex,
            session_id=session_id,
            kind=kind,
            title=title,
            body=body,
            inbox=inbox,
            visibility=visibility,
            data=dict(data or {}),
            options=list(options or []),
            allow_text=bool(allow_text),
            multi=bool(multi),
            header=str(header or ""),
            questions=list(questions or []),
            tool_call_id=tool_call_id,
        )
        with self._lock:
            self._items[item.id] = item
            self._save()
        return item

    def for_tool_call(self, session_id: str, tool_call_id: str) -> Optional[InboxItem]:
        for i in self._items.values():
            if i.session_id == session_id and i.tool_call_id == tool_call_id:
                return i
        return None

    def add_approval(
        self,
        session_id,
        title,
        *,
        body="",
        inbox="default",
        visibility=VIS_INBOX,
        data=None,
        tool_call_id=None,
    ) -> InboxItem:
        # `data` carries the automation-run context for standing scoped approvals (§25):
        # {task_id, task_title, standing_target?} — the in-app card's "Allow every time" gate.
        return self.add(
            session_id,
            KIND_APPROVAL,
            title,
            body=body,
            inbox=inbox,
            visibility=visibility,
            data=data,
            tool_call_id=tool_call_id,
        )

    def add_question(
        self,
        session_id,
        title,
        *,
        body="",
        inbox="default",
        visibility=VIS_INBOX,
        options=None,
        allow_text=True,
        multi=False,
        header="",
        questions=None,
        tool_call_id=None,
    ) -> InboxItem:
        return self.add(
            session_id,
            KIND_QUESTION,
            title,
            body=body,
            inbox=inbox,
            visibility=visibility,
            options=options,
            allow_text=allow_text,
            multi=multi,
            header=header,
            questions=questions,
            tool_call_id=tool_call_id,
        )

    def add_directory(
        self,
        session_id,
        title,
        *,
        body="",
        inbox="default",
        visibility=VIS_INBOX,
        data=None,
        tool_call_id=None,
    ) -> InboxItem:
        return self.add(
            session_id,
            KIND_DIRECTORY,
            title,
            body=body,
            inbox=inbox,
            visibility=visibility,
            data=data,
            tool_call_id=tool_call_id,
        )

    def add_plan(
        self,
        session_id,
        title,
        *,
        body="",
        inbox="default",
        visibility=VIS_INBOX,
        data=None,
        tool_call_id=None,
    ) -> InboxItem:
        return self.add(
            session_id,
            KIND_PLAN,
            title,
            body=body,
            inbox=inbox,
            visibility=visibility,
            data=data,
            tool_call_id=tool_call_id,
        )

    def add_tool_request(
        self,
        session_id,
        title,
        *,
        body="",
        inbox="default",
        visibility=VIS_INBOX,
        data=None,
        tool_call_id=None,
    ) -> InboxItem:
        return self.add(
            session_id,
            KIND_TOOL,
            title,
            body=body,
            inbox=inbox,
            visibility=visibility,
            data=data,
            tool_call_id=tool_call_id,
        )

    def add_notification(
        self, session_id, title, *, body="", inbox="default", visibility=VIS_INBOX
    ) -> InboxItem:
        return self.add(
            session_id,
            KIND_NOTIFICATION,
            title,
            body=body,
            inbox=inbox,
            visibility=visibility,
        )

    # -- queries ----------------------------------------------------------------
    def get(self, item_id: str) -> Optional[InboxItem]:
        return self._items.get(item_id)

    def list(
        self,
        *,
        session_id: Optional[str] = None,
        state: Optional[str] = None,
        inbox: Optional[str] = None,
        visibility: Optional[str] = None,
    ) -> list[InboxItem]:
        out = list(self._items.values())
        if session_id is not None:
            out = [i for i in out if i.session_id == session_id]
        if state is not None:
            out = [i for i in out if i.state == state]
        if inbox is not None:
            out = [i for i in out if i.inbox == inbox]
        if visibility is not None:
            out = [i for i in out if i.visibility == visibility]
        return sorted(out, key=lambda i: i.created_at)

    def pending(self, session_id: Optional[str] = None) -> list[InboxItem]:
        return self.list(session_id=session_id, state=STATE_PENDING)

    # -- the state machine ------------------------------------------------------
    def resolve(self, item_id: str, resolution: str) -> bool:
        """Resolve an item exactly once. First responder wins; later attempts are no-ops
        (return False). Fires any awaiting agent (the suspended inbox_approver)."""
        with self._lock:
            item = self._items.get(item_id)
            if item is None or item.state == STATE_RESOLVED:
                return False
            item.state = STATE_RESOLVED
            item.resolution = resolution
            item.resolved_at = _now()
            self._save()
        waiter = self._waiters.get(item_id)
        if waiter is not None:
            waiter.set()
        return True

    def resolve_session(
        self, session_id: str, resolution: str = "session deleted"
    ) -> int:
        """Resolve every still-pending item of a session (called when the session is deleted —
        an orphaned approval/question can never be meaningfully answered). Releases any waiter
        the usual way; returns how many items were closed."""
        closed = 0
        for item in self.pending(session_id):
            if self.resolve(item.id, resolution):
                closed += 1
        return closed

    async def wait(self, item_id: str) -> str:
        """Await an item's resolution; returns the resolution string. Used by the approver to
        suspend the agent until a human answers (from any surface)."""
        item = self._items.get(item_id)
        if item is not None and item.state == STATE_RESOLVED:
            return item.resolution or ""
        ev = self._waiters.setdefault(item_id, asyncio.Event())
        await ev.wait()
        resolved = self._items.get(item_id)
        return (resolved.resolution if resolved else "") or ""

    # -- resume reconciliation --------------------------------------------------
    def reconcile_on_resume(self, session_id: str) -> dict:
        """When a user resumes attended control, surface this session's still-pending items
        inline (one place to answer from now on) plus a recap of what was answered while away.
        Single source of truth: every item already has one authoritative resolution."""
        pending = self.pending(session_id)
        recap = [i for i in self.list(session_id=session_id, state=STATE_RESOLVED)]
        return {
            "pending": [asdict(i) for i in pending],
            "recap": [asdict(i) for i in recap],
        }


# -- approver routing -----------------------------------------------------------
def inbox_approver(store: InboxStore, session_id: str, *, inbox: str = "default"):
    """An Approver that routes a permission request to the Inbox and suspends until resolved.
    Maps the resolution to an ApprovalOutcome (allow → ONCE, always → ALWAYS_TOOL, else DENY).
    """
    from .engine import ApprovalOutcome, PermissionRequest

    async def approve(request: "PermissionRequest") -> "ApprovalOutcome":
        item = store.add_approval(
            session_id,
            title=f"Run `{request.tool_name}`?",
            body=request.reason or "",
            inbox=inbox,
        )
        resolution = await store.wait(item.id)
        if resolution == "always":
            return ApprovalOutcome.ALWAYS_TOOL
        if resolution == "allow":
            return ApprovalOutcome.ONCE
        return ApprovalOutcome.DENY

    return approve
