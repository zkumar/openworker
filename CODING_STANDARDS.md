# Coding standards

Judgement calls `reviewer-code` enforces. Everything mechanical is enforced by tooling —
`ruff` (line length 160, `build/` and `.venv/` excluded) and `make verify`.

## Errors
- A governed failure derives from `RegulatoryHalt` (compliance) or `RecoverableError`
  (operational). A bare `Exception` on a governed path is a defect.
- Never catch `RegulatoryHalt` to continue. `AwaitingSignoff` exists to stop a run; `pursue` must
  let it escape (`tests/regression/test_r14_candidate_hash.py` pins this).
- A refusal names what was refused: `UnknownRecord("unknown request_id 'PA-…' — not in the pack's
  records")`, not `"invalid input"`.
- An error a human must act on is a 4xx with a reason; a transient fault is a 5xx that may retry.

## Modules and seams
- `kernel/` never imports `packs/`; no pack imports another pack. Guarded by
  `tests/architecture/test_ownership.py` — if a change needs to break it, the seam is wrong.
- A new contract goes in `kernel/**/contract.py`, frozen, with a docstring saying what is frozen
  and what a caller may rely on.
- 400 lines per module is the soft ceiling; past it, split by responsibility, not by line count.
- Prefer a new module over widening an existing one: `runstore.py`, `ingress.py`, `receipts.py`
  were each extracted for that reason.

## State and IO
- Anything persisted and shared is SQLite with WAL and an explicit transaction. A whole-file
  rewrite is only acceptable for genuinely single-writer data.
- Regulated content is written `0600`, atomically (temp → fsync → replace).
- A store that can be read by a second process is read *from* that store, never from a cache that
  can go stale (see `build_receipt`: the receipt is derived, never stored).

## Naming
- A field says whose it is: `member_id` (subject) vs `request_id` (the work). Never let a subject id
  become a reference — `_record_ref` pins the preference order.
- Sealed things are named for what they seal: `envelope`, `chain_head`, `content_sha256`.
- User-facing labels are words, not enums (`"not found"`, not `not_found`).

## Tests
- Name the behaviour, not the function: `test_an_unknown_record_is_a_404_that_names_the_id`.
- One assertion family per test; the assertion message says what breaks if it fails
  (`"a revoked key must not authenticate"`).
- A regression test references the failure it prevents.
- Tests never touch the network, never need a live fabric, and never share a state directory.

## Docs
- A comment explains *why*, never *what*. "The sweeper must not re-dispatch runs this process still
  owns" — that's a why.
- Every design decision that cost something gets a line recording the alternative rejected.
