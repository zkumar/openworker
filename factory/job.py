#!/usr/bin/env python3
"""The only writer of factory/jobs/<job-id>/job.json.

Every change goes through this script, so the state file is always valid JSON,
every stage move is a legal one, and two runners never overwrite each other's
writes (each change takes a lock, re-reads the file, and replaces it atomically).
Run from the repo root (the main checkout). Standard library only.

  python3 factory/job.py create <slug> --mode quick|shaped|imported|characterize --feature TEXT [--issue N]
  python3 factory/job.py get <job-id> [key]                 print the job, or one key as JSON
  python3 factory/job.py stage <job-id> <stage>             legal moves only (see MOVES)
  python3 factory/job.py set <job-id> key=value ...         value is JSON if it parses, else a string
  python3 factory/job.py clear <job-id> key ...             remove keys
  python3 factory/job.py ticket <job-id> <stem> <state>     pending | building | done | blocked
  python3 factory/job.py tickets <job-id>                   add every tickets/*.md stem as pending
  python3 factory/job.py round <job-id> <N> [--lenses a,b] [--carried lens:round,...]
  python3 factory/job.py head <job-id> <N> <sha>           record the commit review round N reviews
  python3 factory/job.py review <job-id> <lens> <verdict>   PASS | CHANGES | pending | skipped
  python3 factory/job.py tokens <job-id> <key> <count|null> add to the ledger, keep tokens_total
  python3 factory/job.py find --issue N                     print the job id that holds issue N
  python3 factory/job.py list [--stage s,...]               one line per job: id stage round

Exit 0 on success, 1 when the change is refused (the reason is on stderr; the
file is untouched), 2 on bad usage. `--force` on stage skips the move check:
for a human repairing a job by hand, never for an agent.
"""
from __future__ import annotations

import contextlib
import datetime as dt
import json
import os
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
JOBS = ROOT / "factory" / "jobs"
CONFIG = ROOT / "factory" / "config.md"

MODES = {"shaped", "quick", "imported", "characterize"}
STAGES = {"shape", "ready", "build", "review", "approve", "needs-human", "pr-open", "merged", "dropped"}
# Legal moves. needs-human is reachable from every live stage; merged is final.
MOVES = {
    "shape": {"ready"},
    "ready": {"build", "shape"},
    "build": {"build", "review"},
    "review": {"review", "build", "approve"},
    "approve": {"approve", "merged", "pr-open"},
    "needs-human": {"build", "merged", "pr-open", "ready", "needs-human"},
    "pr-open": {"build", "merged", "pr-open"},
    "merged": set(),
    "dropped": set(),  # abandoned by a human; final like merged
}
for s in STAGES - {"merged", "dropped"}:
    MOVES[s].add("needs-human")
    MOVES[s].add("dropped")
TICKET_STATES = {"pending", "building", "done", "blocked"}
VERDICTS = {"pending", "PASS", "CHANGES", "skipped"}
RISKS = {"low", "medium", "high"}
CHECKS = {"pending", "PASS", "FAIL", "none"}
CI = {"pending", "passed", "failed", "none"}
# Keys with a fixed set of values; anything else is checked only for being JSON.
ENUMS = {"stage": STAGES, "mode": MODES, "risk": RISKS, "checks": CHECKS, "ci": CI,
         "awaiting": {"delivery"}}
# Keys only the dedicated commands may write, so their rules can't be bypassed.
GUARDED = {"stage": "stage", "tickets": "ticket/tickets", "reviews": "review/round", "round_heads": "head",
           "carried": "round", "round_carried": "round", "risk": "tickets (from the spec's Risk line)",
           "round": "round", "tokens": "tokens", "tokens_total": "tokens", "id": "create",
           "updated": "(automatic)"}


class Refused(Exception):
    pass


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def lenses_from_config() -> dict[str, str]:
    try:
        text = CONFIG.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {}
    m = re.search(r"^## Review lenses\s*$(.*?)(?=^## |\Z)", text, re.M | re.S)
    out = {}
    for line in (m.group(1) if m else "").splitlines():
        lm = re.match(r"^- ([a-z]+):[ \t]*(on|off|auto)\b", line)
        if lm:
            out[lm.group(1)] = lm.group(2)
    return out


def job_dir(job_id: str) -> Path:
    if not re.fullmatch(r"\d{3,}-[a-z0-9][a-z0-9-]*", job_id):
        raise Refused(f"'{job_id}' is not a job id (like 004-csv-export)")
    d = JOBS / job_id
    if not d.is_dir():
        raise Refused(f"no job folder factory/jobs/{job_id}/")
    return d


@contextlib.contextmanager
def locked(d: Path, name: str = ".job.lock"):
    """Exclusive lock per job; released when the block ends (or the process dies)."""
    fh = open(d / name, "a+")
    try:
        try:
            import fcntl
            fcntl.flock(fh, fcntl.LOCK_EX)
        except ImportError:  # Windows: no flock; single-writer use still works
            pass
        yield
    finally:
        fh.close()


def read(d: Path) -> dict:
    try:
        return json.loads((d / "job.json").read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise Refused(f"{d.name}: job.json is missing")
    except json.JSONDecodeError as e:
        raise Refused(f"{d.name}: job.json is not valid JSON ({e}); repair it by hand, then retry")


def write(d: Path, job: dict) -> None:
    job["updated"] = now()
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".job.", suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(job, f, indent=2, ensure_ascii=False)
        f.write("\n")
    os.replace(tmp, d / "job.json")  # atomic: the dashboard never sees half a file


def change(job_id: str, fn) -> dict:
    d = job_dir(job_id)
    with locked(d):
        job = read(d)
        fn(job, d)
        write(d, job)
    return job


def parse_value(raw: str):
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


def check_enum(key: str, value) -> None:
    if key in ENUMS and value not in ENUMS[key]:
        raise Refused(f"{key} must be one of {', '.join(sorted(ENUMS[key]))} (got {value!r})")


# ------------------------------------------------------------------ commands


def cmd_create(args: list[str]) -> None:
    opts = {"--mode": None, "--feature": None, "--issue": None}
    slug = None
    i = 0
    while i < len(args):
        if args[i] in opts and i + 1 < len(args):
            opts[args[i]] = args[i + 1]
            i += 2
        elif slug is None and not args[i].startswith("--"):
            slug = args[i]
            i += 1
        else:
            raise SystemExit(2)
    if not slug or not opts["--mode"] or opts["--feature"] is None:
        raise SystemExit(2)
    if not re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+){0,5}", slug):
        raise Refused(f"slug must be kebab-case words (got {slug!r})")
    check_enum("mode", opts["--mode"])
    issue = None
    if opts["--issue"] is not None:
        if not opts["--issue"].isdigit():
            raise Refused("--issue must be a number")
        issue = int(opts["--issue"])
    JOBS.mkdir(parents=True, exist_ok=True)
    with locked(JOBS, ".create.lock"):  # one creator at a time: the issue check and the claim are one step
        job_id = create_locked(slug, opts, issue)
    print(job_id)


def create_locked(slug: str, opts: dict, issue: int | None) -> str:
    if issue is not None:
        held = find_issue(issue)
        if held:
            raise Refused(f"issue #{issue} already has job {held}")
    nums = [int(m.group(1)) for p in JOBS.iterdir() if p.is_dir() and (m := re.match(r"(\d{3,})-", p.name))]
    n = max(nums, default=0) + 1
    while True:  # mkdir is the claim: two runners can't get the same number
        job_id = f"{n:03d}-{slug}"
        try:
            (JOBS / job_id).mkdir()
            break
        except FileExistsError:
            n += 1
    lenses = lenses_from_config()
    job = {"id": job_id, "feature": opts["--feature"], "title": slug.replace("-", " "),
           "mode": opts["--mode"], "branch": f"factory/{job_id}", "worktree": "",
           "stage": "shape", "round": 0, "tickets": {},
           "reviews": {l: ("skipped" if s == "off" else "pending") for l, s in lenses.items()}}
    if issue is not None:
        job["issue"] = issue
    d = JOBS / job_id
    with locked(d):
        write(d, job)
    return job_id


def find_issue(issue: int) -> str | None:
    if not JOBS.is_dir():
        return None
    for p in sorted(JOBS.glob("*/job.json")):
        try:
            if json.loads(p.read_text(encoding="utf-8")).get("issue") == issue:
                return p.parent.name
        except (OSError, json.JSONDecodeError):
            continue
    return None


def cmd_get(job_id: str, key: str | None = None) -> None:
    job = read(job_dir(job_id))
    if key is None:
        print(json.dumps(job, indent=2, ensure_ascii=False))
    elif key in job:
        v = job[key]
        print(v if isinstance(v, str) else json.dumps(v, ensure_ascii=False))
    else:
        raise Refused(f"{job_id} has no key '{key}'")


def cmd_stage(job_id: str, stage: str, force: bool) -> None:
    check_enum("stage", stage)

    def fn(job, d):
        cur = job.get("stage")
        if not force and stage not in MOVES.get(cur, set()):
            ok = ", ".join(sorted(MOVES.get(cur, set()))) or "none (final)"
            raise Refused(f"{job_id}: can't move from '{cur}' to '{stage}' (allowed: {ok})")
        if stage == "build" and cur == "ready" and not job.get("tickets"):
            raise Refused(f"{job_id}: no tickets yet; run `tickets` first")
        if stage == "merged" or stage == "pr-open":
            job.pop("awaiting", None)
        job["stage"] = stage
    change(job_id, fn)


def cmd_set(job_id: str, pairs: list[str]) -> None:
    updates = {}
    for p in pairs:
        if "=" not in p:
            raise SystemExit(2)
        k, raw = p.split("=", 1)
        if not re.fullmatch(r"[a-z_]+", k):
            raise Refused(f"bad key {k!r}")
        if k in GUARDED:
            raise Refused(f"'{k}' is written by `{GUARDED[k]}`, not `set`")
        v = parse_value(raw)
        check_enum(k, v)
        updates[k] = v

    def fn(job, d):
        job.update(updates)
    change(job_id, fn)


def cmd_clear(job_id: str, keys: list[str]) -> None:
    for k in keys:
        if k in GUARDED:
            raise Refused(f"'{k}' can't be cleared")

    def fn(job, d):
        for k in keys:
            job.pop(k, None)
    change(job_id, fn)


def cmd_ticket(job_id: str, stem: str, state: str) -> None:
    if state not in TICKET_STATES:
        raise Refused(f"ticket state must be one of {', '.join(sorted(TICKET_STATES))}")

    def fn(job, d):
        if stem not in job.get("tickets", {}):
            raise Refused(f"{job_id} has no ticket '{stem}' (known: {', '.join(job.get('tickets', {})) or 'none'})")
        job["tickets"][stem] = state
    change(job_id, fn)


def cmd_tickets(job_id: str) -> None:
    def fn(job, d):
        stems = sorted(p.stem for p in (d / "tickets").glob("*.md"))
        if not stems:
            raise Refused(f"{job_id}: no tickets/*.md files")
        t = job.setdefault("tickets", {})
        for s in stems:
            t.setdefault(s, "pending")
        for s in list(t):
            if s not in stems and t[s] == "pending":
                del t[s]  # a ticket file the spec-writer removed
        spec = d / "spec.md"
        if spec.exists():
            m = re.search(r"^# (.+)$", spec.read_text(encoding="utf-8"), re.M)
            if m:
                job["title"] = m.group(1).strip()
            r = re.search(r"^\*\*Risk:\*\*[ \t]*(low|medium|high)\b(?![ \t]*\|)", spec.read_text(encoding="utf-8"), re.M | re.I)
            if r:
                job["risk"] = r.group(1).lower()
            else:  # missing, reworded or the template placeholder: unknown, so security always reviews
                job.pop("risk", None)
    change(job_id, fn)


def cmd_round(job_id: str, n: str, args: list[str]) -> None:
    if not n.isdigit() or int(n) < 1:
        raise Refused("round must be a whole number >= 1")
    lenses = None
    carried: dict[str, int] = {}
    i = 0
    while i < len(args):
        if args[i] == "--lenses" and i + 1 < len(args):
            lenses = [x for x in args[i + 1].split(",") if x]
        elif args[i] == "--carried" and i + 1 < len(args):
            for item in filter(None, args[i + 1].split(",")):
                l, _, r = item.partition(":")
                if not r.isdigit():
                    raise Refused(f"--carried wants lens:round, got {item!r}")
                carried[l] = int(r)
        else:
            raise SystemExit(2)
        i += 2
    N = int(n)

    def fn(job, d):
        if job.get("stage") != "review":
            raise Refused(f"{job_id}: move to stage 'review' before starting a round")
        if N not in (job.get("round", 0), job.get("round", 0) + 1):
            raise Refused(f"{job_id}: round {N} doesn't follow round {job.get('round', 0)}")
        known = list(job.get("reviews", {}))
        on = [l for l, s in lenses_from_config().items() if s == "on"] or known
        reviewing = lenses if lenses is not None else on
        for l in reviewing + list(carried):
            if l not in known:
                raise Refused(f"unknown lens '{l}' (this job has: {', '.join(known)})")
        for l, r in carried.items():
            f = d / f"round-{r}" / f"review-{l}.md"
            first = f.read_text(encoding="utf-8", errors="replace").split("\n", 1)[0].strip() if f.exists() else ""
            if first != "VERDICT: PASS":
                raise Refused(f"can't carry {l} from round {r}: round-{r}/review-{l}.md doesn't start with VERDICT: PASS")
        overlap = set(reviewing) & set(carried)
        if overlap:
            raise Refused(f"lens(es) both reviewing and carried: {', '.join(sorted(overlap))}")
        job["round"] = N
        job["reviews"] = {l: ("pending" if l in reviewing else "PASS" if l in carried else "skipped")
                          for l in known}
        job["carried"] = carried
        rc = job.setdefault("round_carried", {})
        rc[str(N)] = sorted(carried)
        job["checks"] = "pending"
    change(job_id, fn)


def cmd_head(job_id: str, n: str, sha: str) -> None:
    if not n.isdigit() or not re.fullmatch(r"[0-9a-f]{7,40}", sha):
        raise Refused("usage: head <job-id> <round> <commit sha>")

    def fn(job, d):
        job.setdefault("round_heads", {})[n] = sha
    change(job_id, fn)


def cmd_review(job_id: str, lens: str, verdict: str) -> None:
    if verdict not in VERDICTS:
        raise Refused(f"verdict must be one of {', '.join(sorted(VERDICTS))}")

    def fn(job, d):
        if lens not in job.get("reviews", {}):
            raise Refused(f"{job_id} has no lens '{lens}'")
        job["reviews"][lens] = verdict
    change(job_id, fn)


def cmd_tokens(job_id: str, key: str, raw: str) -> None:
    if raw != "null" and not raw.isdigit():
        raise Refused("token count must be a whole number or null")

    def fn(job, d):
        t = job.setdefault("tokens", {})
        if raw == "null":
            t.setdefault(key, None)
        else:
            t[key] = (t.get(key) or 0) + int(raw)
        job["tokens_total"] = sum(v for v in t.values() if isinstance(v, int))
    change(job_id, fn)


def cmd_list(args: list[str]) -> None:
    want = None
    if args[:1] == ["--stage"] and len(args) == 2:
        want = set(args[1].split(","))
    elif args:
        raise SystemExit(2)
    for p in sorted(JOBS.glob("*/job.json")) if JOBS.is_dir() else []:
        try:
            j = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            print(f"{p.parent.name} ? (job.json unreadable)")
            continue
        if want is None or j.get("stage") in want:
            print(f"{j.get('id', p.parent.name)} {j.get('stage')} {j.get('round', 0)}"
                  + (f" issue#{j['issue']}" if "issue" in j else ""))


def main(argv: list[str]) -> int:
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__.strip())
        return 0 if argv else 2
    cmd, rest = argv[0], argv[1:]
    force = "--force" in rest
    rest = [a for a in rest if a != "--force"]
    try:
        if cmd == "create":
            cmd_create(rest)
        elif cmd == "get" and len(rest) in (1, 2):
            cmd_get(*rest)
        elif cmd == "stage" and len(rest) == 2:
            cmd_stage(rest[0], rest[1], force)
        elif cmd == "set" and len(rest) >= 2:
            cmd_set(rest[0], rest[1:])
        elif cmd == "clear" and len(rest) >= 2:
            cmd_clear(rest[0], rest[1:])
        elif cmd == "ticket" and len(rest) == 3:
            cmd_ticket(*rest)
        elif cmd == "tickets" and len(rest) == 1:
            cmd_tickets(rest[0])
        elif cmd == "round" and len(rest) >= 2:
            cmd_round(rest[0], rest[1], rest[2:])
        elif cmd == "head" and len(rest) == 3:
            cmd_head(*rest)
        elif cmd == "review" and len(rest) == 3:
            cmd_review(*rest)
        elif cmd == "tokens" and len(rest) == 3:
            cmd_tokens(*rest)
        elif cmd == "find" and rest[:1] == ["--issue"] and len(rest) == 2 and rest[1].isdigit():
            held = find_issue(int(rest[1]))
            if held:
                print(held)
            return 0 if held else 1
        elif cmd == "list":
            cmd_list(rest)
        else:
            print(__doc__.strip(), file=sys.stderr)
            return 2
    except Refused as e:
        print(f"refused: {e}", file=sys.stderr)
        return 1
    except SystemExit as e:
        if e.code == 2:
            print(__doc__.strip(), file=sys.stderr)
        return int(e.code or 0)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
