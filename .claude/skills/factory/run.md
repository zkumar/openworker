# Running jobs

Covers `quick`, `import`, `run`, `next`, `approve` and `rework`. You orchestrate;
agents do the work. Formats are in [templates.md](templates.md), limits and
policy in `factory/config.md`.

## Names and paths

- `<repo>`: the main checkout, `git rev-parse --show-toplevel`. `<name>`: its folder name.
- `<base>`: `base_branch` from config (usually `main`).
- `<base ref>`: what jobs branch from and are compared against. With
  `merge_mode: local` it is `<base>`. With `merge_mode: pr` it is `origin/<base>`,
  refreshed with `git fetch origin <base>` at preflight and before delivery, so
  jobs start from what the team has merged, not from a stale local branch.
- Job worktree: `<parent of repo>/<name>-factory/<job-id>` on the **integration
  branch** `factory/<job-id>`.
- Ticket worktree: `<parent of repo>/<name>-factory/<job-id>--t<NN>` on branch
  `factory/<job-id>--t<NN>`. (Not `factory/<job-id>/t<NN>`: git cannot hold a
  branch and a folder of branches with the same name.)
- `<paths>` in a prompt means this sentence with absolute paths:
  `Job folder: <repo>/factory/jobs/<job-id>/. Worktree: <worktree>. Branch: <branch>. Base: <base ref>.`
- Ports come from the **Ports** section of config.
- **Quote every path** in shell commands (`git worktree add -b ... "<worktree>" ...`,
  `cd "<worktree>"`): repo folders often contain spaces.

Every `job.json` change: rewrite the whole file, set `updated`.

**Token ledger.** Every time an agent you spawned finishes (or a resumed one
returns), add the token count its result reports to `job.json` → `tokens`, keyed
by agent and step: `spec-writer`, `visualizer-plan`, `impl-t01`, `merger-t02`,
`review-r1-code`, `fixer-r1`, `visualizer-as-built`, `approver`, and so on (sum
repeats under the same key). Keep `tokens_total` as the sum. If a result carries
no count, record `null` for that key rather than guessing. This is how
`/factory retro` and the dashboard show where tokens go.

**Superseding outcome files.** Before spawning the approver, and before a
rework, rename any existing `decision.md` to `decision-<k>.md`, `pr.md` to
`pr-<k>.md` and `approval.md` to `approval-<k>.md` (`k` the next unused number).
Only fresh outcome files are ever read, so a human sign-off never carries over
to code it didn't see, and the history stays for audit.

**Worktree present?** Several steps need the job worktree. If its path is
missing (PR mode removes it after delivery), re-create it from the kept branch
before going on: `git worktree add "<worktree>" factory/<job-id>`; in PR mode
first `git fetch origin factory/<job-id>` and then
`git -C "<worktree>" merge --ff-only origin/factory/<job-id>` to pick up commits
others pushed to the PR. If the fast-forward fails (someone rebased or
force-pushed the PR branch), stop and ask the user how to proceed.

**Is `pr_url` a PR?** Only when it matches `/pull/<number>`. A compare link (saved
when `gh` was unavailable) is not; look the PR up with
`gh pr list --head factory/<job-id> --state all --json url,state` before
creating or editing one.

---

## Creating a job (shared by shape, quick, import)

1. `mkdir -p factory/jobs`.
2. Pick the next 3-digit number after the highest numbered folder in
   `factory/jobs/` (`001` if none) and a 2-4 word kebab-case slug.
3. Claim it with `mkdir factory/jobs/<job-id>` (no `-p`). If that fails because
   the folder exists, another session took the number: take the next and retry.
4. Write `job.json`: `id`, `feature` (the request verbatim), `title` (the slug in
   words until the spec has a heading), `mode`, `branch: "factory/<job-id>"`,
   `worktree: ""`, `stage: "shape"`, `round: 0`, `tickets: {}`, and `reviews`
   with every lens from config: `pending` if `on`, `skipped` if `off`.

When `spec.md` is written, set `title` from its first heading and fill
`tickets` with every ticket file stem as `pending`.

## /factory quick <feature>

1. Create the job with `mode: "quick"`.
2. Spawn `spec-writer` with the prompt
   `Job folder: <repo>/factory/jobs/<job-id>/. Mode: quick. Feature: <feature, verbatim>`.
3. Check that `spec.md` and at least one `tickets/*.md` exist. Set `title` and
   `tickets`.
4. Spawn `visualizer` with `Job folder: <repo>/factory/jobs/<job-id>/. Mode: plan.`
   and wait for it.
5. Set `stage: "ready"`. If `quick_spec_gate` is true, hold a spec gate: follow
   **Showing visuals at a decision point** in [visuals.md](visuals.md) (paste
   `visuals/chat.md`, run `./factory/show.sh <job-id>`), give the title, story
   and criteria counts and the ticket graph, and stop until the user replies
   `approve` (then run) or asks for changes. Otherwise continue with
   **/factory run**.

## /factory characterize <area>

A safety-net job for existing code: pin what `<area>` (a module, path or
feature) does today, with no product change. See `characterizer.md`.

1. Create the job with `mode: "characterize"`, `feature: "Characterize <area>"`.
2. Write `spec.md` yourself, short: title `Characterize <area>`; Problem: changes
   to this area are risky because its current behaviour isn't pinned; Solution:
   characterisation tests at its public entry points; one acceptance criterion
   per rule: (1) the diff touches test files only, (2) every new test is named
   `currently_…` (or, after a rework, the requirement name the human gave it) and
   passes three runs in a row, (3) every test has a row in
   `captures.md`, (4) the full suite still passes. Out of scope: any change to
   product code. Write `tickets/01-characterize.md` (blocked by none, criteria 1-4).
3. Skip the visualizer. Set `stage: "ready"` and continue with **/factory run**,
   with these differences:
   - In the ticket loop, spawn `characterizer` (not `implementer`), named
     `char-<job-id>`, with the same prompt plus ` Area: <area>.`
   - Review lenses: `spec` and `code` only, plus `compliance` if it is on (test
     data can contain regulated data); mark the rest `skipped`.
   - **Approve:** don't spawn the approver. Write `decision.md` yourself:
     `ESCALATE`, a blank line, then
     `Characterisation captures need your verdict: keep, flag or delete each row in captures.md.`
     and go to **Needs human**.
4. The human answers with `/factory approve <job-id>` (keep every row as is) or
   `/factory rework <job-id> <verdicts>`, for example
   `delete 5, 7; flag 3; keep 2 as "gold members get 10% off"`. The fixer applies
   the verdicts (delete tests, add `FLAG:` comments, rename kept ones to real
   requirement names) and updates `captures.md`; after review the job returns to
   **Needs human** (see **Approve**) for `/factory approve`.

## /factory import <path or issue>

1. Create the job with `mode: "imported"` and `feature` set to the source's
   title or path.
2. Save the source verbatim to `source.md`: copy a file path; for a GitHub issue
   use `gh issue view <n> --comments`, and include its sub-issues if it has any;
   for anything else, ask the user to paste it.
3. Spawn `spec-writer` with the prompt
   `Job folder: <repo>/factory/jobs/<job-id>/. Mode: import. Source: source.md`.
4. Set `title` and `tickets`. Spawn `visualizer` with
   `Job folder: <repo>/factory/jobs/<job-id>/. Mode: plan.` and wait for it.
   Always hold a spec gate: follow **Showing visuals at a decision point** in
   [visuals.md](visuals.md) first (paste `visuals/chat.md`, run
   `./factory/show.sh <job-id>`), then show the title, story and criteria
   counts, the ticket graph, and every line under **Assumptions**. On approval
   set `stage: "ready"` and offer to run.

---

## /factory run <job-id>

The job must be `ready` (or mid-run; see **Resuming** at the end).

### 0. Preflight

Run `python3 factory/preflight.py <job-id>` from the repo root, on every run and
every resume, before launching any agent. It checks the config (numbers,
booleans, every `on` lens has its agent, the cross-vendor CLI if that lens is
on), the job (stage, spec, tickets match `job.json`, every **Blocked by** names
a real ticket, no cycles), git (version, base ref, factory files committed on
it, `COMPLIANCE.md` when that lens is on) and, in PR mode, the remote and `gh`.
Any `FAIL` line: stop, show the output, and say what to fix; nothing has been
spent yet. `warn` lines: mention them and continue. Then, in PR mode,
`git fetch origin <base>`. If `python3` is missing, do the checks below by hand.

- `git --version` must be 2.38 or newer (`git merge-tree --write-tree` needs it).
- `merge_mode: pr` only: `git remote get-url origin` must succeed (otherwise stop:
  PR mode needs a remote), then `git fetch origin <base>`. Check `gh auth status`;
  if `gh` is missing or not signed in, warn that delivery will push the branch
  and give a compare link instead of opening the PR itself.
- `git rev-parse --verify <base ref>` must succeed, and `<base ref>` must contain
  the factory files: `git cat-file -e <base ref>:.claude/skills/factory/SKILL.md`.
  In PR mode, if this fails the install commit was never pushed: tell the user to
  push it (or merge its PR) first.
- If the `compliance` lens is `on` and `COMPLIANCE.md` is not committed on
  `<base ref>` (`git cat-file -e <base ref>:COMPLIANCE.md`), stop and tell the
  user: the lens has no checklist.

### 1. Integration worktree

```bash
git worktree add -b factory/<job-id> "<worktree>" <base ref>
```

In the worktree, run the fresh-checkout setup `AGENTS.md` gives. If it fails,
stop and tell the user.

If `domain/` exists, record the shaped decisions on the integration branch:
append `domain/GLOSSARY.additions.md` to the worktree's `GLOSSARY.md` (create it
with a `# Glossary` heading if missing) and copy each `domain/adr-<slug>.md` to
`docs/adr/adr-<slug>.md` (slugs, not numbers, so parallel jobs never collide).
Then `git add` exactly those paths and commit `Record domain decisions for <job-id>`.

Set `worktree`, `stage: "build"`.

### 2. Ticket loop

The **frontier** is every `pending` ticket whose **Blocked by** tickets are all
`done`.

Loop:

1. **Start** frontier tickets while fewer than `max_parallel_implementers` are
   `building`. For each, from `<repo>`:
   ```bash
   git worktree add -b factory/<job-id>--t<NN> <ticket worktree> factory/<job-id>
   ```
   run the setup in it, mark the ticket `building`, and spawn `implementer`
   **in the background**, named `impl-<job-id>-t<NN>`, with
   `<paths for the ticket worktree and branch> Integration branch: factory/<job-id>. Ticket: tickets/<NN>-<slug>.md. Port: <port base + free slot>.`
2. **When one finishes**, read the first line of `build/t<NN>.md`:
   - `STATUS: READY`: merge it (one merge at a time, never two at once):
     ```bash
     git -C <worktree> merge --no-ff factory/<job-id>--t<NN> -m "Merge ticket <NN>: <title>"
     ```
     - Clean: mark `done`, then
       `git worktree remove <ticket worktree>` and
       `git -C <worktree> branch -d factory/<job-id>--t<NN>` (run from the
       integration worktree, where the branch is merged).
     - Conflict: `git -C <worktree> merge --abort`, then spawn `merger` with
       `<paths for the job worktree> Ticket branch: factory/<job-id>--t<NN>. Ticket: tickets/<NN>-<slug>.md.`
       On `STATUS: MERGED`, mark `done` and clean up as above. On
       `STATUS: FAILED`, mark `blocked`.
   - `STATUS: BLOCKED`: mark `blocked`. Keep its worktree and branch.
3. Report one line per transition: `004-csv-export: ticket 02 merged (2/3)`.
4. **Exit** when nothing is `building` and the frontier is empty. Then:
   - every ticket `done`: go to **Review round 1**;
   - otherwise (some `blocked`, and their dependents stuck `pending`): go to
     **Needs human** and quote each blocked ticket's `## Blocked` section.

### 3. Review round N

1. Set `stage: "review"`, `round: N`, every `on` lens `pending`, every `off`
   lens `skipped`. Create `round-<N>/`. For `mode: "characterize"` jobs only
   `spec`, `code` and (if on) `compliance` count as `on`; every other lens is
   `skipped`.
2. Spawn every `on` reviewer **in the background, all at once**:
   `reviewer-<lens>` with `<paths for the job worktree> Review round N.`, plus
   ` Port: <port>.` for `ux` and `ui`. If config `serial_browser_lenses` is
   true, start `ui` only after `ux` has finished.
3. **Wait for all.** As each finishes, read the first line of its file and write
   the verdict to `job.json` at once, so the dashboard fills in. The round is
   done only when every `on` lens has its `review-<lens>.md`. Never start fixes
   mid-round. If a reviewer ends without its file, or its first line is not a
   verdict, give it one correction (see **One correction** in SKILL.md); if it
   still fails, stop and tell the user.
4. Decide. Fix rounds used = review rounds since this run (or the last rework)
   started, minus one.
   - **All PASS**: go to **Approve**.
   - **Any CHANGES and fix rounds used < `max_fix_rounds`**: set
     `stage: "build"`. Send the fixer
     `Fix round N: address every review with VERDICT: CHANGES in round-<N>/, then write build/fix-round-<N>.md.`
     After the first review round of a run (or of a rework) spawn a fresh
     `implementer` named `fixer-<job-id>-<attempt>` (attempt = 1, then the
     rework number) with `<paths for the job worktree> ` + that message +
     ` Port: <port base + 8>.` After later rounds, resume the same fixer with
     `SendMessage`. If it can't be resumed (for example after a restart), spawn a
     fresh one the same way; it reads the earlier `build/fix-round-*.md`.
     Read its first line: `READY` → **Review round N+1**; `BLOCKED` → **Needs human**.
   - Every fix is reviewed: a round always ends on a review, never on a fixer.
     When the budget is spent, the last fixer has already been reviewed, and no
     further fix is started.
   - **Any CHANGES and no fix rounds left**: supersede any old `decision.md`,
     then write a new one yourself: `ESCALATE`, a blank line,
     `Review rounds exhausted. Outstanding CHANGES in round-<N>/ from: <lenses>.`
     Go to **Needs human**.

### 4. Approve

Set `stage: "approve"`. Supersede old outcome files.

**Characterize jobs** (`mode: "characterize"`) never use the approver or the
visualizer, in the first run or after any rework: write `decision.md` yourself
(`ESCALATE`, a blank line, then
`Characterisation captures need your verdict: keep, flag or delete each row in captures.md.`)
and `pr.md` (a `## Summary` with the area, the number of tests and test files,
and "see captures.md for every pinned behaviour"; `## Merge danger`:
**Door:** two-way, **Blast radius:** tests), then go to **Needs human**. Only a
human `/factory approve` delivers a characterize job.

Other jobs: if `as_built` is `on` in
config **Visuals**, first spawn `visualizer` with
`<paths for the job worktree> Mode: as-built.` and wait for it (it rewrites
`visuals/as-built/`, including `drift.md`). Then spawn `approver` with
`<paths for the job worktree> Final round: N.` Read the first line of the new
`decision.md` (missing or not `APPROVE`/`ESCALATE`: one correction, then stop
and tell the user):

- `APPROVE` and `auto_merge: true`: go to **Deliver**.
- `APPROVE` and `auto_merge: false`: go to **Needs human**; say the agent approved
  and human sign-off is required by policy.
- `ESCALATE`: go to **Needs human**.

### 5. Deliver

How an approved job lands depends on `merge_mode` (a config without the key means
`local`).

#### merge_mode: local

The main checkout must be on `<base>` and clean apart from factory state:
`git branch --show-current` prints `<base>`, and
`git status --porcelain -- . ':!factory/backlog.md' ':!factory/jobs' ':!factory/retros'`
prints nothing. If not, set `needs-human` and say the job is approved but the
main checkout is busy: run `/factory approve <job-id>` once it is clean.

Write the merge message to a temporary file outside the repo: first line
`Merge factory/<job-id>: <title>`, a blank line, then `pr.md`. Then:

```bash
git merge --no-ff factory/<job-id> -F <message file>
git worktree remove "<worktree>"
git branch -d factory/<job-id>
```

Set `stage: "merged"`, and show the user what landed: the **Solution** block of
`visuals/as-built/chat.md` (if it exists) and one line per drift. If the merge
fails, `git merge --abort`, set `needs-human`, and say why. If removing the worktree fails (for example untracked
build output), the job is still merged; report what git printed. **Never push.**

#### merge_mode: pr

The main checkout is not touched. Only the job branch is pushed; never push to
`<base>`, never merge or approve the PR yourself. Every step is safe to repeat,
so a resumed Deliver just runs it again.

1. Make sure the job worktree is present (see **Worktree present?**).
2. `git fetch origin <base>`, then
   `git merge-tree --write-tree origin/<base> factory/<job-id>`. On conflicts, set
   `needs-human` and say the branch conflicts with `origin/<base>`; suggest
   `/factory rework <job-id> Merge origin/<base> and resolve conflicts`.
3. Write the PR body to a temporary file outside the repo: `pr.md`, then a line
   `---`, then
   `<details><summary>Factory record: <job-id></summary>` with a blank line,
   `decision.md`, `approval.md` if it exists, the final-round verdicts as one line
   (`spec PASS · code PASS · ...`), and `</details>`. Before that record, add a
   `## Diagrams` section with each of `solution.mmd`, `interaction.mmd` and
   `context.mmd` that exists (from `visuals/as-built/`, else `visuals/`) in its
   own ` ```mermaid ` block under a short heading; GitHub renders them.
4. `git -C "<worktree>" push -u origin factory/<job-id>`, then set `pushed_sha`
   in `job.json` to `git -C "<worktree>" rev-parse HEAD`. If the push is rejected
   (someone pushed to the branch since), set `needs-human`, keep the worktree, and
   say so: `/factory rework <job-id> --from-pr` will pick their commits up.
5. Find the PR for this branch: `pr_url` if it is a PR (see **Is `pr_url` a PR?**),
   else `gh pr list --head factory/<job-id> --state all --json url,state`.
   - An **open** PR: `gh pr edit <url> --body-file <body file>`; the push already
     updated its commits.
   - **None**, or only a **closed** one: `gh pr create --base <base> --head factory/<job-id> --title "<title>" --body-file <body file>`,
     adding `--draft` when `pr_draft: true`. Use the URL it prints.
   - `gh` missing or not signed in: build the compare link from the remote URL,
     `https://github.com/<owner>/<repo>/compare/<base>...factory/<job-id>?expand=1`,
     and tell the user to open the PR there (paste `pr.md`).
   - Any `gh` failure: set `needs-human`, keep the worktree, quote the error.
6. Set `stage: "pr-open"` and `pr_url` (the PR URL, or the compare link).
7. `git worktree remove "<worktree>"`. Keep the local branch; a rework needs it.
   If removal fails, the job is still delivered; report what git printed.
8. Tell the user the PR link, and offer `/factory watch <job-id>`: it waits for
   CI, repairs failing checks, and brings new review comments back.
   `/factory status` notices when the PR is merged.

### Needs human

Set `stage: "needs-human"`. Leave every branch and worktree in place. (In PR mode
the branch may already have an open PR from an earlier delivery; say so and give
`pr_url`.) Show the user what they are deciding on, in this order:

1. The pictures: follow **Showing visuals at a decision point** in
   [visuals.md](visuals.md) with `visuals/as-built/chat.md` (else
   `visuals/chat.md`), so the drift lines come before any text. For a
   characterize job, paste the `captures.md` table instead (it is the picture)
   and don't run `show.sh`.
2. The reason: quote `decision.md` (or the blocking build files) and its
   **For the human** section.
3. The job id, the worktree path, and the replies that work:
   `/factory approve <job-id> [note]` (only when `decision.md` exists and no
   ticket is `blocked`) or `/factory rework <job-id> <note>`.

### Resuming

If a session ended mid-run, `/factory run <job-id>` picks up from `job.json`
and the files on disk:

- `build`, `round: 0`: a `building` ticket whose `build/t<NN>.md` exists is
  finished; handle it as in step 2.2. One with no build file: remove its
  worktree (`git worktree remove --force`) and branch (`git branch -D`), set it
  `pending`, and re-enter the loop.
- `build`, `round > 0`: a fix or rework was in flight. Make sure the worktree is
  present. If the newest `rework-<k>.md` has no `build/rework-<k>.md` yet, spawn a
  fresh rework fixer for it (rework step 2). Otherwise, if
  `build/fix-round-<round>.md` exists, act on its first line; else spawn a fresh
  fixer for that round.
- `review`: spawn only the `on` lenses (for characterize jobs: spec, code and,
  if on, compliance) missing a `round-<round>/review-<lens>.md`.
- `approve`: if `decision.md` exists and starts with `APPROVE`, the approver
  finished: continue from the `APPROVE` branch of **Approve** (Deliver is safe to
  repeat). Otherwise re-run **Approve**.
- `pr-open` / `merged`: nothing to resume; use `/factory status`.

---

## /factory next

Read `factory/backlog.md` and take the first line that starts with `- [ ]`.
A line `- [ ] characterize: <area>` runs as `/factory characterize <area>`;
any other line runs as `/factory quick <item>`.
Claim it with one Edit that turns it into `- [x] <item> → claimed`. If the Edit
fails because the line changed, another session claimed it: re-read and try the
next. If none is left, say so and stop. Run it, and once it has a job id,
replace `claimed` with the job id.

## /factory show <job-id>

Bring a job's pictures into the conversation at any stage, for example to
discuss it before deciding. Follow **Showing visuals at a decision point** in
[visuals.md](visuals.md) with `visuals/as-built/chat.md` if it exists, else
`visuals/chat.md`; then one line with the stage and what the job is waiting
for. If the job has no `visuals/` yet (still shaping), draw the current
understanding as in shape.md's **Sketch as you go**. Change nothing.

## /factory watch <job-id>

PR mode only, for a job in `pr-open` whose `pr_url` is a PR. It follows the PR
after delivery, so CI failures and review comments come back into the factory
instead of waiting for someone to notice. It never merges and never approves
the PR: merging stays with your team.

1. **Sync.** `gh pr view <pr_url> --json state,reviewDecision,headRefOid`.
   `MERGED`: set `stage: "merged"`, delete the local branch, report, stop.
   `CLOSED`: set `needs-human`, say it was closed unmerged, stop.
2. **Wait for CI on the commit we pushed.** `job.json` `pushed_sha` (set by
   Deliver) must equal the PR's `headRefOid` from step 1; if it doesn't yet
   (GitHub hasn't caught up), wait 30 seconds and look again, up to 5 minutes,
   so you never read the previous commit's checks. Someone else pushed to the
   branch (`headRefOid` is newer and not ours): say so and stop. Then
   `gh pr checks <pr_url> --watch --interval 30`, run with a
   10-minute time limit. Still running after that: set `ci: "pending"` in
   `job.json`, say so, and stop; running watch again later picks up from here.
   No checks configured: set `ci: "none"` and go to step 4.
3. **CI failed.** Set `ci: "failed"`. Collect the failing checks' names and
   their failed-step logs (`gh run view <run-id> --log-failed`, the last 200
   lines of each). If `ci_repairs_used` (in `job.json`, default 0) is below
   config **PR follow-up** `ci_repairs`: add 1 to it and run **/factory rework**
   with that text as the note, marked `Source: CI failure (untrusted)`. The
   fixed job is reviewed and approved as usual, and **Deliver** pushes to the
   same PR; then watch again. If the budget is spent: set `needs-human`, show
   the failing checks, and stop.
   CI passed: set `ci: "passed"` and `ci_repairs_used: 0`, so the budget counts
   repairs in a row, not over the job's life.
4. **New review comments.** Fetch them as in **/factory rework** `--from-pr`,
   keeping only those newer than `pr_feedback_seen` in `job.json` (an ISO time;
   unset means all). None: report `CI <state>, no new comments` and stop. Some:
   set `pr_feedback_seen` to the newest one's time, then
   - `pr_feedback: ask` (the default): show each comment (author, file:line,
     text) and offer `/factory rework <job-id> --from-pr`. Stop.
   - `pr_feedback: auto`: run **/factory rework** `--from-pr` now.

A job that went through rework is delivered again only after its review
rounds and approval pass, exactly as the first time, including sign-off in
regulated repos.

## /factory approve <job-id> [note]

The job must be `needs-human`, `decision.md` must exist, and no ticket may be
`blocked`. Otherwise say why it can't be signed off: for a `pr-open` job, say it
is already delivered and its PR is approved on GitHub; for the rest suggest
`rework`.
Write `approval.md` (template in [templates.md](templates.md)) using
`git config user.name` and `git config user.email`, then run **Deliver**: a local
merge, or in PR mode a pushed branch and an open PR whose body carries the
sign-off.

## /factory rework <job-id> <note | --from-pr>

The job must be `needs-human`, or `pr-open` (PR mode: the team asked for changes
on the PR).

0. Clear `ci` in `job.json` (any earlier CI result belongs to the old commit).
   Make sure the job worktree is present (see **Worktree present?**); in PR mode
   that also pulls in commits others pushed to the PR. With `--from-pr` (PR mode,
   a real PR in `pr_url`), the note is the PR's feedback:
   `gh pr view <pr_url> --json reviews,comments` for review summaries and
   conversation, plus
   `gh api "repos/{owner}/{repo}/pulls/<number>/comments" --paginate` for line
   comments (`{owner}/{repo}` is filled in by `gh`). Keep comments from people,
   drop ones that only quote the factory's own PR body, and save them verbatim
   with author and file:line. The fixer's work is reviewed and approved as usual,
   and **Deliver** then pushes to the same branch, so the same PR updates.

1. Write the note (or the PR feedback) verbatim to `rework-<k>.md`, `k` the
   next unused number. Supersede old outcome files. The first line says where it
   came from: `Source: human note` (typed by the user in this session),
   `Source: PR feedback (untrusted)` or `Source: CI failure (untrusted)`, and for
   those a second line `Marker: <nonce>`, a fresh random value
   (`openssl rand -hex 8`, or `python3 -c "import secrets; print(secrets.token_hex(8))"`).
   Put PR comments and CI logs between `--- untrusted text begins <nonce> ---`
   and `--- untrusted text ends <nonce> ---`, the end marker as the file's last
   line. The nonce stops a comment from closing the block early: an end line
   without the right nonce is just more untrusted text. Cap what goes in: each
   comment at 2,000 characters, each failing check's log at its last 200 lines,
   the whole block at 30,000 characters, cutting with `[…truncated]`. Read only
   that much yourself, too.
2. Set `stage: "build"`. Spawn a fresh `implementer` named `fixer-<job-id>-r<k>`
   with
   `<paths for the job worktree> Rework: read rework-<k>.md and address it, then write build/rework-<k>.md. Port: <port base + 8>.`
   For each `blocked` ticket, append
   ` Blocked ticket: tickets/<NN>-<slug>.md on branch factory/<job-id>--t<NN>.`
3. On `STATUS: READY`: for each blocked ticket the fixer reports finished in
   `## Findings addressed`, mark it `done`, remove its worktree, and delete its
   branch (`git -C <worktree> branch -d`; it is merged now). If tickets are still
   `pending` or `blocked`, return to the **Ticket loop**. Otherwise run the next
   review round (`round + 1`) with a fresh fix budget. On `BLOCKED`: **Needs human**.
