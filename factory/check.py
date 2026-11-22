#!/usr/bin/env python3
"""The deterministic gate: run the repo's own checks before any AI reviewer.

    python3 factory/check.py <worktree> [<out.md>]    run the checks, write the report
    python3 factory/check.py <worktree> --list         print the commands it would run

The commands come from factory/config.md, section **Checks**:

    - check: auto                      detect from the repo (default)
    - check: npm run lint              or list your own, one per line, in order

`auto` looks at the worktree: package.json scripts (lint, typecheck, test, build),
Python (ruff, mypy when configured, pytest), Go, Rust, and a Makefile `check` or
`test` target; an auto-detected tool that isn't installed is skipped and named. Every command runs in the worktree with a time limit
(`check_timeout_min`, default 15). The report's first line is `CHECKS: PASS`,
`CHECKS: FAIL` or `CHECKS: NONE` (nothing to run); each failing command keeps
the last 120 lines of its output. Exit 0 for PASS or NONE, 1 for FAIL, 2 for
bad usage. Standard library only.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TAIL = 120


def config_section(name: str) -> str:
    try:
        text = (ROOT / "factory" / "config.md").read_text(encoding="utf-8", errors="replace")
    except FileNotFoundError:
        return ""
    m = re.search(rf"^## {re.escape(name)}\s*$(.*?)(?=^## |\Z)", text, re.M | re.S)
    return m.group(1) if m else ""


def configured() -> tuple[list[str], int]:
    block = config_section("Checks")
    cmds, timeout = [], 15
    for line in block.splitlines():
        m = re.match(r"^- check:[ \t]*(.+?)[ \t]*$", line)
        if m:
            cmds.append(m.group(1))
        t = re.match(r"^- check_timeout_min:[ \t]*(\d+)", line)
        if t:
            timeout = int(t.group(1))
    return cmds or ["auto"], timeout


def detect(wt: Path) -> list[str]:
    out: list[str] = []
    pkg = wt / "package.json"
    if pkg.exists():
        try:
            scripts = json.loads(pkg.read_text(encoding="utf-8", errors="replace")).get("scripts", {}) or {}
        except json.JSONDecodeError:
            scripts = {}
        pm = "pnpm" if (wt / "pnpm-lock.yaml").exists() else "yarn" if (wt / "yarn.lock").exists() \
            else "bun" if (wt / "bun.lockb").exists() else "npm"
        for s in ("lint", "typecheck", "type-check", "test", "build"):
            if s in scripts and "no test specified" not in str(scripts[s]):
                out.append(f"{pm} run {s}" if not (pm == "npm" and s == "test") else "npm test")
        if "typecheck" not in scripts and "type-check" not in scripts and (wt / "tsconfig.json").exists():
            out.insert(1 if out[:1] and "lint" in out[0] else 0, "npx --no-install tsc --noEmit")
    py = (wt / "pyproject.toml").exists() or (wt / "setup.py").exists() or (wt / "requirements.txt").exists()
    if py:
        pp = (wt / "pyproject.toml").read_text(encoding="utf-8", errors="replace") if (wt / "pyproject.toml").exists() else ""
        # run tools inside the project's own environment when it has one
        run = "uv run " if (wt / "uv.lock").exists() else "poetry run " if (wt / "poetry.lock").exists() else ""
        if "[tool.ruff" in pp or (wt / "ruff.toml").exists() or (wt / ".ruff.toml").exists():
            out.append(f"{run}ruff check .")
        if "[tool.mypy" in pp or (wt / "mypy.ini").exists():
            out.append(f"{run}mypy ." if run else "python3 -m mypy .")
        if any((wt / d).is_dir() for d in ("tests", "test")) or "[tool.pytest" in pp or (wt / "pytest.ini").exists():
            out.append(f"{run}pytest -q" if run else "python3 -m pytest -q")
    if (wt / "go.mod").exists():
        out += ["go vet ./...", "go test ./..."]
    if (wt / "Cargo.toml").exists():
        out += ["cargo clippy --quiet -- -D warnings" if shutil.which("cargo-clippy") else "cargo check --quiet",
                "cargo test --quiet"]
    mk = wt / "Makefile"
    if not out and mk.exists():
        targets = re.findall(r"^([a-zA-Z_-]+):", mk.read_text(encoding="utf-8", errors="replace"), re.M)
        for t in ("check", "test"):
            if t in targets:
                out.append(f"make {t}")
                break
    return out


def installed(cmd: str) -> bool:
    """Auto-detected commands are skipped when their tool isn't installed here."""
    m = re.match(r"python3 -m (\w+)", cmd)
    if m:
        return subprocess.run([sys.executable, "-c", f"import {m.group(1)}"], capture_output=True).returncode == 0
    if cmd.startswith(("uv run ", "poetry run ")):
        return shutil.which(cmd.split()[0]) is not None
    if cmd.startswith("npx --no-install tsc"):
        return shutil.which("npx") is not None
    return shutil.which(cmd.split()[0]) is not None


def commands(wt: Path) -> tuple[list[str], int, bool, list[str]]:
    cmds, timeout = configured()
    auto = cmds == ["auto"]
    if not auto:
        return [c for c in cmds if c != "auto"], timeout, False, []
    found = detect(wt)
    return [c for c in found if installed(c)], timeout, True, [c for c in found if not installed(c)]


def run_one(cmd: str, wt: Path, timeout_min: int) -> tuple[int, str]:
    """Run in its own process group, no stdin, CI=1 (no watch modes); kill the whole group on timeout."""
    env = dict(os.environ, CI="1", PYTHONDONTWRITEBYTECODE="1")  # no __pycache__ litter in worktrees
    p = subprocess.Popen(cmd, shell=True, cwd=wt, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                         stderr=subprocess.STDOUT, text=True, errors="replace", env=env, start_new_session=True)
    try:
        out, _ = p.communicate(timeout=timeout_min * 60)
        code = p.returncode
    except subprocess.TimeoutExpired:
        try:
            os.killpg(p.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            p.kill()
        out, _ = p.communicate()
        out, code = (out or "") + f"\n[timed out after {timeout_min} min]", 124
    if code == 5 and "pytest" in cmd:  # pytest: no tests collected is not a failure
        out, code = out + "\n[pytest collected no tests: treated as a pass]", 0
    return code, out


def run(wt: Path, out: Path | None) -> int:
    cmds, timeout, auto, missing = commands(wt)
    lines = []
    if not cmds:
        lines = ["CHECKS: NONE", "",
                 "No checks found (auto-detect found nothing). List commands in factory/config.md, section Checks."]
        status = 0
    else:
        results = []
        for c in cmds:
            t0 = time.time()
            code, text = run_one(c, wt, timeout)
            results.append((c, code, round(time.time() - t0, 1), text))
            if code != 0:
                break  # later checks usually fail for the same reason; save the time
        failed = [r for r in results if r[1] != 0]
        status = 1 if failed else 0
        lines = [f"CHECKS: {'FAIL' if failed else 'PASS'}", "",
                 f"Source: {'auto-detected' if auto else 'factory/config.md Checks'}", "",
                 "| Command | Exit | Seconds |", "| --- | --- | --- |"]
        lines += [f"| `{c}` | {code} | {s} |" for c, code, s, _ in results]
        if missing:
            lines += ["", "Not installed here, so not run: " + ", ".join(f"`{c}`" for c in missing)]
        skipped = cmds[len(results):]
        if skipped:
            lines += ["", "Not run (an earlier check failed): " + ", ".join(f"`{c}`" for c in skipped)]
        for c, code, s, text in failed:
            tail = text.rstrip().splitlines()[-TAIL:]
            lines += ["", f"## `{c}` failed (exit {code})", "", "```", *tail, "```"]
    report = "\n".join(lines) + "\n"
    if out:
        out.parent.mkdir(parents=True, exist_ok=True)
        tmp = out.with_suffix(".tmp")
        tmp.write_text(report, encoding="utf-8")
        os.replace(tmp, out)  # the report appears whole or not at all
    print(report.splitlines()[0])
    return status


def main(argv: list[str]) -> int:
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__.strip())
        return 0 if argv else 2
    wt = Path(argv[0]).resolve()
    if not wt.is_dir():
        print(f"no such worktree: {wt}", file=sys.stderr)
        return 2
    if argv[1:] == ["--list"]:
        cmds, timeout, auto, missing = commands(wt)
        print(f"# {'auto-detected' if auto else 'from factory/config.md'}; limit {timeout} min each")
        print("\n".join(cmds) if cmds else "(nothing to run)")
        if missing:
            print("# not installed, skipped: " + ", ".join(missing))
        return 0
    if len(argv) > 2:
        print(__doc__.strip(), file=sys.stderr)
        return 2
    return run(wt, Path(argv[1]).resolve() if len(argv) == 2 else None)


if __name__ == "__main__":
    sys.exit(main(argv=sys.argv[1:]))
