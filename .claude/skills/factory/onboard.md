# /factory onboard

Bring an existing codebase onto the factory: assess it, write down its
unwritten rules, and plan the safety net, before any feature job touches it.
Run once per repo, after `install.sh` and `/factory setup`. It changes no
product code. It writes only `factory/onboarding/`, `CODING_STANDARDS.md`,
`GLOSSARY.md` and the backlog, each with the user's go-ahead.

Facts are your job (from git, the code, running commands); decisions are
the user's. Ask in rounds, numbered, each with a recommended answer worded so
"yes" accepts it.

## 0. Assess (no questions yet)

Gather, then summarise in `factory/onboarding/assessment.md`:

- **Health:** run the setup, test, lint and build commands from `AGENTS.md`
  (time-box each to a few minutes). Record pass, fail, or missing, and the
  pass/fail counts. Note CI config if present (`.github/workflows`, etc.).
- **Shape:** languages and size (file counts by extension), entry points (main
  modules, CLI or server start-up, routes), main packages, and the most-imported
  modules (count imports of each module across the repo with Grep).
- **Churn:** files changed most in the last 12 months:
  `git log --since=12.months --format= --name-only | grep -v '^$' | sort | uniq -c | sort -rn | head -30`.
- **Hot spots:** where churn and dependence meet: the top 10 files or modules
  that are both frequently changed and widely depended on. For each, note
  whether tests reach it (test files that import it or call its main functions).
- **Ownership:** `git shortlog -sn --since=12.months -- <path>` for the hot spots.

Rate the repo, with the reasons in one line each:

| Rating | Meaning |
| --- | --- |
| **ready** | builds, tests pass, hot spots mostly tested: start factory jobs now |
| **needs on-ramp** | builds, but hot spots lack tests or rules are unwritten: do steps 2–3 first |
| **not now** | does not build, tests broadly failing, or no owner: fix that first, by hand |

If **not now**, stop after the report: say what must be fixed and offer nothing else.

## 1. Capture the unwritten rules

Turn tribal knowledge into rules agents and reviewers can follow.

1. Propose 3–5 areas from the architecture and hot spots (for example "API
   handlers", "data access", "FHIR mapping", "error handling"). The user picks
   one; you can come back for more.
2. Pick 5–10 representative files in that area (most-imported
   modules, recently changed, different authors), and read them.
3. List patterns that are **repeated**, **non-obvious** to a newcomer, and
   **deliberate-looking**. Skip what a linter or the language already enforces.
4. For each pattern, ask the user one or two questions about *why* and *when it
   is allowed to differ*, one pattern at a time. Their answer decides the rule.
5. Draft the rule: lead with the rule in one line, then a short real example
   from the code (file:line), then the exception if any. Every rule cites at
   least two places in the code that follow it, so it is evidence, not
   invention. The user confirms, edits or skips each one.
6. Mechanical rules (a banned call, an import shape, a file location) are better
   as lint rules or CI checks: list them separately as proposals.
7. Write confirmed rules to `CODING_STANDARDS.md` under a heading per area, and
   domain terms that came up to `GLOSSARY.md` (`**Term**: definition. _Avoid_: …`).
   reviewer-code enforces CODING_STANDARDS.md; every agent reads GLOSSARY.md.

Offer another area, or move on.

## 2. Plan the safety net

For each hot spot without tests that the user expects to change in the next
few months, propose a characterisation job: one line per area in
`factory/backlog.md` as `- [ ] characterize: <area or module path>`.
`/factory next` (or `/factory characterize <area>`) runs them. Order by risk:
most changed and least tested first.

## 3. Report

Write `factory/onboarding/report.md`:

```markdown
# Onboarding: <repo>
Rating: ready | needs on-ramp | not now (date)

## Health
setup ✓ · tests 412 pass / 3 fail (known: ...) · lint ✓ · CI: GitHub Actions

## Hot spots
| Area | Changes (12 mo) | Depended on by | Tests reach it | Owner |

## Rules captured
- CODING_STANDARDS.md: <n> rules in <areas>; <n> lint proposals
- GLOSSARY.md: <n> terms

## Next
1. characterize: <area> (backlog)
2. first feature job suggestion: <small, well-tested area>
```

Show the user the rating and the next steps, and tell them to commit
`factory/onboarding/`, `CODING_STANDARDS.md`, `GLOSSARY.md` and the backlog on
the base branch so every job's worktree sees them.

## Many repos

Onboard one repo per session; the report's first line gives the rating, so a
folder of reports (or `grep -h '^Rating:' */factory/onboarding/report.md`) is a
portfolio view.
