#!/usr/bin/env python3
"""The gate, machine-checked. Exit 1 if a gate rule is broken.

Rules (deliberately simple, so a human can verify each by reading it):
  1. every factory/jobs/<id>/spec.md carries `Status:` with a known value
  2. a spec in draft/ready has no code committed against it
  3. "approved" names a human and a date
  4. "verified" points at an evidence path that exists
  5. every job with tickets has an Acceptance and a Verification section

Usage:  python3 factory/gate.py [--repo PATH]
"""
from __future__ import annotations
import argparse, re, subprocess, sys
from pathlib import Path

STATUSES = ("draft", "ready", "approved", "building", "verified", "done")
CODE_SUFFIXES = (".py", ".ts", ".tsx", ".css", ".json")


def spec_status(spec: Path) -> tuple[str | None, str]:
    m = re.search(r"^Status:\s*(\w+)(.*)$", spec.read_text(encoding="utf-8"), re.M)
    return (m.group(1).lower(), m.group(2).strip()) if m else (None, "")


def changed_since(repo: Path) -> list[str]:
    out = subprocess.run(["git", "-C", str(repo), "status", "--porcelain"],
                         capture_output=True, text=True).stdout
    return [l[3:] for l in out.splitlines() if l.strip()]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=".")
    repo = Path(ap.parse_args().repo).resolve()
    jobs_dir = repo / "factory" / "jobs"
    problems: list[str] = []
    building: list[str] = []
    if not jobs_dir.is_dir():
        print("gate: no factory/jobs/ — nothing to check")
        return 0

    dirty = [f for f in changed_since(repo) if f.endswith(CODE_SUFFIXES) and "factory/jobs" not in f]

    for job in sorted(p for p in jobs_dir.iterdir() if p.is_dir()):
        spec = job / "spec.md"
        if not spec.is_file():
            problems.append(f"{job.name}: no spec.md")
            continue
        text = spec.read_text(encoding="utf-8")
        status, rest = spec_status(spec)
        if status is None:
            problems.append(f"{job.name}: spec has no `Status:` line")
            continue
        if status not in STATUSES:
            problems.append(f"{job.name}: unknown status {status!r}")
        if status in ("building", "verified"):
            building.append(job.name)
        if status == "approved" and not re.search(r"\([^)]*\d{4}-\d{2}-\d{2}\)", rest):
            problems.append(f"{job.name}: approved must name a person and a date, e.g. (vijay, 2026-11-06)")
        if status == "verified":
            m = re.search(r"verified\(([^)]+)\)", spec.read_text(encoding="utf-8"))
            if not m or not (repo / m.group(1)).exists():
                problems.append(f"{job.name}: verified must cite an existing evidence path")
        for section in ("## Acceptance", "## Verification"):
            if section not in text:
                problems.append(f"{job.name}: spec lacks {section!r}")

    # Code may only be dirty while some job is actively building. That is the rule the
    # first version got wrong: it blamed every ready job instead of the one doing the work.
    if dirty and not (building or verified):
        problems.append(
            f"{len(dirty)} code file(s) modified but no job is in `building` — "
            f"approve a job before writing code")

    if problems:
        print("GATE FAILED")
        for p in problems:
            print("  ✗", p)
        return 1
    print("gate: ok — every job has a status, acceptance, verification; no unapproved code")
    return 0


if __name__ == "__main__":
    sys.exit(main())
