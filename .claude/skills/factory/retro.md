# /factory retro [job-id or all]

Look back over finished jobs and propose changes to the **environment** so the
next jobs need fewer rounds and fewer escalations. You propose; the user decides.
Change nothing until they say which proposals to apply.

## 1. Gather

Default to every job merged, delivered as a PR, or escalated since the last file in
`factory/retros/` (all jobs if there is none). For each, read `job.json`,
`decision.md`, any `approval.md` and `rework-*.md`, every `build/*.md` with
`BLOCKED` or `FAILED`, and every `round-*/review-*.md` with `CHANGES` or Notes.

Count the signals:

- findings that recur across jobs or rounds (same lens, same kind of problem);
- review rounds per job and which lens forced each extra round;
- escalations by policy line, and which ones the human then approved unchanged;
- blocked tickets and their causes;
- notes a reviewer raised that later turned into a real finding.
- token use from each `job.json` `tokens` ledger: per job, per agent role, and
  per review round, and which roles dominate.

## 2. Propose, most impactful first

| Signal | Proposal |
| --- | --- |
| A mechanical mistake recurs (banned API, import shape, file location, formatting) | A deterministic check: a lint rule, pre-commit hook or CI job. Prefer this over a written rule. |
| A judgement call recurs | A rule in `CODING_STANDARDS.md` (reviewer-code reads it). |
| Implementers kept searching for the same thing | A one-line navigation pointer in `AGENTS.md`. Keep that file small. |
| The repo has no guardrail running lint/type-check/tests | Wire one up. This is always a finding. |
| A policy line escalates things the human always approves | Narrow that line in `factory/config.md`. |
| A risk reached a human only by luck | Add a policy line, or turn on a lens. |
| A lens never finds anything in this repo | Turn it `off`. |
| One agent role dominates token use | Narrow its reading (map-first rule, smaller tickets), or move it to a cheaper model in its frontmatter. |
| A ticket blocked on a missing decision | Add that question to shape.md step 3's coverage list. |
| Specs keep producing unverifiable criteria | Tighten the spec template or spec-writer guidance. |
| A word caused confusion between agents | A `GLOSSARY.md` entry. |

For each proposal give: the evidence (job ids and file paths), the exact change
(a diff or the new lines), and the expected effect.

## 3. Record

Write `factory/retros/<YYYY-MM-DD>.md` with the proposals and, after the user
answers, which were applied. Apply accepted proposals to the main checkout only
with the user's go-ahead, and tell them to commit those changes and the retro
file: the merge step needs a clean main checkout (it ignores only
`factory/backlog.md`, `factory/jobs/` and `factory/retros/`).
