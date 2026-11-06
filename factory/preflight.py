#!/usr/bin/env python3
"""Check a job and the repo before /factory run launches any agent.

    python3 factory/preflight.py <job-id>      (from the repo root)

Prints one line per check: "ok", "warn" or "FAIL". Exits 1 if anything FAILs,
so the orchestrator stops before spending tokens. Standard library only.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FACTORY = ROOT / "factory"
AGENTS = ROOT / ".claude" / "agents"
LENSES_KNOWN = {"spec", "code", "security", "ux", "ui", "compliance", "cross"}
STAGES_RUNNABLE = {"ready", "build", "review", "approve", "needs-human"}

results: list[tuple[str, str]] = []


def ok(msg: str) -> None:
    results.append(("ok", msg))


def warn(msg: str) -> None:
    results.append(("warn", msg))


def fail(msg: str) -> None:
    results.append(("FAIL", msg))


def git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, text=True)


# ---------------------------------------------------------------- config


def codex_signed_in(exe: str) -> bool:
    try:
        return subprocess.run([exe, "login", "status"], capture_output=True, timeout=30).returncode == 0
    except (subprocess.TimeoutExpired, OSError):
        return False


def section(text: str, name: str) -> str:
    m = re.search(rf"^## {re.escape(name)}\s*$(.*?)(?=^## |\Z)", text, re.M | re.S)
    return m.group(1) if m else ""


def keyvals(block: str) -> dict[str, str]:
    """`- key: value   # comment` lines of a config section."""
    out = {}
    for line in block.splitlines():
        m = re.match(r"^- ([A-Za-z_]+):[ \t]*(.*?)(?:[ \t]+#.*)?[ \t]*$", line)
        if m:
            out[m.group(1)] = m.group(2).strip()
    return out


def check_config() -> dict:
    path = FACTORY / "config.md"
    if not path.exists():
        fail("factory/config.md is missing (re-run install.sh)")
        return {}
    text = path.read_text(encoding="utf-8")
    limits = keyvals(section(text, "Limits"))
    lenses = keyvals(section(text, "Review lenses"))
    policy = keyvals(section(text, "Merge policy"))
    cfg = {"limits": limits, "lenses": lenses, "policy": policy}
    bad = False

    def need_int(key: str, low: int) -> None:
        nonlocal bad
        v = limits.get(key)
        if v is None or not v.isdigit() or int(v) < low:
            fail(f"config Limits: {key} must be a whole number >= {low} (got {v!r})")
            bad = True

    need_int("max_parallel_implementers", 1)
    need_int("max_fix_rounds", 0)
    if not limits.get("base_branch"):
        fail("config Limits: base_branch is missing")
        bad = True
    for key in ("quick_spec_gate", "serial_browser_lenses"):
        if key in limits and limits[key] not in ("true", "false"):
            fail(f"config Limits: {key} must be true or false (got {limits[key]!r})")
            bad = True
    for lens, state in lenses.items():
        if lens not in LENSES_KNOWN:
            warn(f"config Review lenses: unknown lens '{lens}' (no built-in reviewer)")
        if state not in ("on", "off"):
            fail(f"config Review lenses: {lens} must be on or off (got {state!r})")
            bad = True
        elif state == "on" and not (AGENTS / f"reviewer-{lens}.md").exists():
            fail(f"lens '{lens}' is on but .claude/agents/reviewer-{lens}.md is missing")
            bad = True
    if not any(s == "on" for s in lenses.values()):
        fail("config Review lenses: every lens is off, so nothing would review the work")
        bad = True
    mode = policy.get("merge_mode", "local")
    if mode not in ("local", "pr"):
        fail(f"config Merge policy: merge_mode must be local or pr (got {mode!r})")
        bad = True
    for key in ("auto_merge", "pr_draft"):
        if key in policy and policy[key] not in ("true", "false"):
            fail(f"config Merge policy: {key} must be true or false (got {policy[key]!r})")
            bad = True
    if lenses.get("cross") == "on":
        cmd = keyvals(section(text, "Cross-vendor review")).get("cross_command", "")
        exe = cmd.split()[0] if cmd else ""
        if not exe:
            fail("lens 'cross' is on but config has no cross_command")
            bad = True
        elif not shutil.which(exe):
            fail(f"lens 'cross' is on but '{exe}' is not installed (cross_command: {cmd})")
            bad = True
        elif Path(exe).name == "codex" and not codex_signed_in(exe):
            fail("lens 'cross' is on but the Codex CLI is not signed in (run: codex login)")
            bad = True
        else:
            ok(f"cross-vendor reviewer available: {exe}")
    if not bad:
        on = ", ".join(k for k, v in lenses.items() if v == "on")
        ok(f"config valid (lenses on: {on}; merge_mode: {mode})")
    return cfg


# ---------------------------------------------------------------- job


def check_job(job_id: str) -> None:
    folder = FACTORY / "jobs" / job_id
    if not folder.is_dir():
        fail(f"no job folder factory/jobs/{job_id}/")
        return
    try:
        job = json.loads((folder / "job.json").read_text(encoding="utf-8"))
    except FileNotFoundError:
        fail("job.json is missing")
        return
    except json.JSONDecodeError as e:
        fail(f"job.json is not valid JSON: {e}")
        return
    stage = job.get("stage")
    if stage not in STAGES_RUNNABLE:
        fail(f"job stage is '{stage}'; /factory run needs one of {', '.join(sorted(STAGES_RUNNABLE))}")
    if not (folder / "spec.md").exists():
        fail("spec.md is missing")
    files = sorted(p.stem for p in (folder / "tickets").glob("*.md")) if (folder / "tickets").is_dir() else []
    if not files:
        fail("no tickets in tickets/")
        return
    listed = set((job.get("tickets") or {}).keys())
    if listed != set(files):
        missing, extra = set(files) - listed, listed - set(files)
        fail("job.json tickets don't match tickets/: "
             + "; ".join(x for x in (f"not in job.json: {', '.join(sorted(missing))}" if missing else "",
                                     f"no file for: {', '.join(sorted(extra))}" if extra else "") if x))
    def num(stem: str) -> int | None:
        m = re.match(r"(\d+)-", stem)
        return int(m.group(1)) if m else None

    numbers = {num(f): f for f in files if num(f) is not None}
    for f in files:
        if num(f) is None:
            fail(f"ticket {f}: file name must start with its number, like 01-<slug>.md")
    edges: dict[str, list[str]] = {}
    graph_ok = True
    for f in files:
        text = (folder / "tickets" / f"{f}.md").read_text(encoding="utf-8")
        m = re.search(r"^\*\*Blocked by:\*\*[ \t]*(.*?)[ \t]*$", text, re.M)
        if not m:
            fail(f"ticket {f}: no '**Blocked by:**' line")
            graph_ok = False
            continue
        value = m.group(1)
        if not value:
            fail(f"ticket {f}: '**Blocked by:**' is empty (write None, or the ticket numbers)")
            graph_ok = False
            continue
        deps: list[int] = []
        if not re.match(r"(?i)none\b", value):
            # each comma-separated item starts with a ticket number: "02", "2", "02-export-button"
            for item in re.split(r"[,;]", value):
                d = re.match(r"\s*(\d+)", item)
                if d:
                    deps.append(int(d.group(1)))
                elif item.strip():
                    fail(f"ticket {f}: can't read '{item.strip()}' in Blocked by")
                    graph_ok = False
        for d in deps:
            if d not in numbers:
                fail(f"ticket {f}: blocked by {d:02d}, which has no ticket file")
                graph_ok = False
        if num(f) is not None:
            edges[num(f)] = [d for d in deps if d in numbers]
    # cycle check (a cycle would leave the ticket loop waiting forever)
    state: dict[int, int] = {}

    def visit(n: int, path: list[int]) -> list[int] | None:
        state[n] = 1
        for d in edges.get(n, []):
            if state.get(d) == 1:
                return path + [n, d]
            if state.get(d) is None:
                found = visit(d, path + [n])
                if found:
                    return found
        state[n] = 2
        return None

    for n in edges:
        if state.get(n) is None:
            cyc = visit(n, [])
            if cyc:
                fail("tickets block each other in a cycle: " + " -> ".join(f"{c:02d}" for c in cyc))
                graph_ok = False
                break
    if graph_ok:
        ok(f"job {job_id}: stage {stage}, {len(files)} ticket(s), blocking edges valid")


# ---------------------------------------------------------------- git and tools


def check_git(cfg: dict) -> None:
    v = git("--version")
    m = re.search(r"(\d+)\.(\d+)", v.stdout or "")
    if not m:
        fail("git not found")
        return
    if (int(m.group(1)), int(m.group(2))) < (2, 38):
        fail(f"git {m.group(1)}.{m.group(2)} is too old; the factory needs 2.38 or newer")
    else:
        ok(f"git {m.group(1)}.{m.group(2)}")
    limits, policy, lenses = cfg.get("limits", {}), cfg.get("policy", {}), cfg.get("lenses", {})
    base = limits.get("base_branch", "main")
    mode = policy.get("merge_mode", "local")
    ref = base
    if mode == "pr":
        if git("remote", "get-url", "origin").returncode != 0:
            fail("merge_mode is pr but the repo has no 'origin' remote")
            return
        ref = f"origin/{base}"
        if git("fetch", "-q", "origin", base).returncode != 0:
            warn(f"git fetch origin {base} failed; checking the last fetched {ref}")
        if not shutil.which("gh"):
            warn("gh is not installed: delivery will push and give a compare link instead of opening the PR")
        elif subprocess.run(["gh", "auth", "status"], capture_output=True).returncode != 0:
            warn("gh is not signed in (gh auth login): delivery will give a compare link instead of a PR")
        else:
            ok("gh signed in")
    if git("rev-parse", "--verify", "--quiet", ref).returncode != 0:
        fail(f"base ref '{ref}' not found" + (" (run: git fetch origin)" if mode == "pr" else ""))
        return
    if git("cat-file", "-e", f"{ref}:.claude/skills/factory/SKILL.md").returncode != 0:
        fail(f"the factory files are not committed on {ref}: agents work in worktrees and would not see them")
    else:
        ok(f"factory files committed on {ref}")
    if lenses.get("compliance") == "on" and git("cat-file", "-e", f"{ref}:COMPLIANCE.md").returncode != 0:
        fail(f"compliance lens is on but COMPLIANCE.md is not committed on {ref}")
    if not (ROOT / "AGENTS.md").exists() and not (ROOT / "CLAUDE.md").exists():
        warn("no AGENTS.md or CLAUDE.md: agents won't know how to set up, test or build (run /factory setup)")


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__.strip())
        return 2
    cfg = check_config()
    check_job(sys.argv[1])
    check_git(cfg)
    width = max(len(s) for s, _ in results)
    for status, msg in results:
        print(f"{status.ljust(width)}  {msg}")
    failed = sum(1 for s, _ in results if s == "FAIL")
    print(f"\npreflight: {'FAILED, ' + str(failed) + ' problem(s) to fix first' if failed else 'passed'}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
