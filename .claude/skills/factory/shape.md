# /factory shape <idea>

You and the user turn an idea into a spec and tickets the factory can build
without asking a single question. This is the only human-in-the-loop part of a
job, so spend the effort here: every decision settled now is an escalation or a
failed review round avoided later.

Keep the whole shape in one unbroken session. Don't suggest `/clear` until the
spec gate has passed.

## 1. Create the job

Follow **Creating a job** in [run.md](run.md) with `mode: "shaped"`.

No worktree yet: shaping reads the main checkout and changes nothing in it.

## 2. Learn the ground

Read `AGENTS.md` (or `CLAUDE.md`), `GLOSSARY.md` and `docs/adr/` if they exist.
Facts are your job, never the user's: when you need to know how something works
in the code, dispatch an `Explore` subagent (model `sonnet`) with a narrow
question rather than asking the user. Use the glossary's terms from now on.

## 3. Grill in rounds

Map the idea as a **design tree**: every decision branches into the decisions
that depend on it. The **frontier** is every decision whose prerequisites are
settled. Ask the whole frontier in one round, numbered, each with your
recommended answer, worded so "yes" accepts it:

```
❓ **Q1** - **<title>**: <question, with options where useful>

➡️ <recommended answer>
```

**Sketch as you go.** From the second round on, open each round with a text
sketch of your current understanding, headed `What I understand so far`: the
actors, the parts involved and the main flow, drawn by the rules in **Pictures
in the conversation** in [visuals.md](visuals.md) (at most 76 columns and 14
lines). Draw it yourself; launch no agent for it. Tag the parts a question is
about with its number (`(Q2)`), so each answer maps to a place in the picture.
Redraw only when an answer changed the structure; otherwise say `picture
unchanged`. When a question is a structural choice (where a check lives, sync
or async, which part owns the data), draw each option as a small sketch labelled
**A** and **B**, with your recommendation under them.

Wait for answers, recompute the frontier, ask the next round. A question that
depends on another open question waits for a later round. While an Explore
subagent is still running, ask the questions that don't depend on it.

Cover at least: who the actors are, the happy path, empty/error/permission
states, data and schema effects, anything that is a one-way door, what is out
of scope, and every product or business call (copy, pricing, defaults, what
users see). Product calls settled here become **Decisions**; the approver would
otherwise escalate them as **[product]** assumptions.

Stop when the frontier is empty and the user confirms you share an
understanding.

## 4. Record the domain

As terms settle, challenge fuzzy or overloaded words against `GLOSSARY.md` and
sharpen them. Don't edit the repo. Instead write:

- `factory/jobs/<job-id>/domain/GLOSSARY.additions.md`: new or changed entries as
  `**Term**: definition. _Avoid_: synonyms not to use.` No implementation detail.
- `factory/jobs/<job-id>/domain/adr-<slug>.md` (referenced in the spec as `adr-<slug>`): only for a decision that is hard
  to reverse, surprising without context, and a real trade-off. Format: a title
  line `# <decision>`, then 1-3 sentences of context, decision and consequence.

`run` commits these onto the job branch, so they merge with the feature.

## 5. Agree the testing seams

Propose where the tests will go: existing seams before new ones, the highest
seam possible, as few as possible (ideally one). Give each a one-line note on
what it catches and what it misses. Ask the user to confirm. Implementers will
test only at these seams, without asking.

## 6. Write spec.md

Write `factory/jobs/<job-id>/spec.md` in the template from
[templates.md](templates.md). When the job changes existing behaviour, fill the
**Behaviour delta**: find today's behaviour in the code (its callers and the
tests that reach it) and list only what is ADDED, MODIFIED or REMOVED,
with the existing tests that pin each. If MODIFIED or REMOVED behaviour is
untested, suggest running `/factory characterize <area>` first. Then check it
yourself:

- Every user story has at least one acceptance criterion; every criterion names
  how to verify it with only the repo.
- Every seam is marked `confirmed by human`.
- Nothing in **Assumptions** is a product call the user already answered.

## 7. Slice into tickets

Draft tracer-bullet tickets (template in [templates.md](templates.md)). Show
them as a numbered list: title, blocked by, what it delivers, which criteria.
Ask: is the granularity right, are the blocking edges real, merge or split
anything? Iterate until approved, then write `tickets/<NN>-<slug>.md` and set
`job.json` `tickets` to every ticket `pending`.

Wide mechanical refactors are the exception to vertical slicing: sequence them
expand, migrate in batches, contract, each its own ticket.

## 8. Spec gate

First spawn `visualizer` with
`Job folder: <repo>/factory/jobs/<job-id>/. Mode: plan.` and wait for it.

Lead with the pictures, not the text: follow **Showing visuals at a decision
point** in [visuals.md](visuals.md), pasting `visuals/chat.md` into the chat and
opening the job's Visual view with `./factory/show.sh <job-id>`. Then give a
five-line summary: title, story count, criteria count, ticket graph
(`01 → 02, 03`), open assumptions. Ask: reply `approve`, or say what to change.
Feedback on a picture is feedback on the spec: fix the spec or tickets, re-run
the visualizer, and show the new pictures the same way.

- Approved: set `title` from the spec's heading and `stage: "ready"`. Offer `/factory run <job-id>` now, or tell
  them any session in this repo can run it later.
- Not approved: return to whichever step their feedback reopens.

## Optional: mirror to an issue tracker

If `AGENTS.md`/`CLAUDE.md` points at `docs/agents/issue-tracker.md` (set up by
`/setup-matt-pocock-skills`), offer to publish the spec as an issue and each
ticket as a sub-issue with its blocking edges, labelled `ready-for-agent`. The
job folder stays the factory's source of truth.
