# /factory setup

Make this repo ready for its first job. `install.sh` copied the files; this
step checks the things only someone who reads the repo can check, and fixes
them with the user. Run it once after installing, and again whenever the
build, test or deploy setup changes.

Work through the sections in order. Facts are your job: find them in the repo
or by running commands, and only ask the user for decisions. Ask in rounds,
numbered, each with your recommended answer, worded so "yes" accepts it.
Show every file change as a short diff and apply it only when the user agrees.

## 1. Read the ground

Read `factory/config.md`, `AGENTS.md` (or `CLAUDE.md`), `COMPLIANCE.md` if it
exists, `.gitignore`, and the repo's build files (`package.json`,
`pyproject.toml`, `Makefile`, CI workflows and similar). Note the base branch
and whether the factory files are committed on it
(`git ls-files .claude/skills/factory factory/config.md`).

## 2. AGENTS.md has what every agent needs

Agents read these four things and nothing else about the repo, so each must be
present, exact and working:

| Section | What the agents do with it |
| --- | --- |
| Setup for a fresh checkout | run once in every new worktree |
| Validate: tests, lint, type-check, build | implementers and reviewer-code run them; a failing check blocks |
| Dev server on a given port | implementers and the UX/UI reviewers start it with `<PORT>` |
| Conventions, or a pointer to CODING_STANDARDS.md | implementers follow; reviewer-code enforces |

For each command, **run it** in the main checkout to prove it works (for the dev
server: start it on a free port, confirm it answers, stop it). Replace any TODO
or wrong command with one that ran. Lint commands should accept a list of files,
because agents lint only what they changed. Keep AGENTS.md short: pointers, not
copies of other docs.

## 3. Config matches the repo

Walk `factory/config.md` with the user:

- `base_branch` exists and is where finished work should land.
- `ux` and `ui` are on only if the app has pages. If they are on, check that the
  `agent-browser` CLI is installed (`agent-browser --version`); if not, say the
  page reviewers will fall back to reading code, and point at
  github.com/vercel-labs/agent-browser.
- `max_parallel_implementers`: lower it to 1 for a small repo or a tight budget.
- **Merge policy**: read the list aloud and ask what else must always reach a
  human in this repo (for example "touches PHI", "changes a FHIR resource
  profile", "edits a migration"). Add each as a policy line.
- `auto_merge`: recommend `false` for regulated or production-critical repos.
- `merge_mode`: recommend `pr` when the repo has a shared remote, a protected base
  branch, or required CI/reviews; `local` for solo repos. For `pr`, check
  `git remote get-url origin` and `gh auth status`; if `gh` is missing, say
  delivery will push the branch and give a compare link to open the PR by hand
  (install: https://cli.github.com, then `gh auth login`).

## 4. COMPLIANCE.md (only if the compliance lens is on)

Fill every TODO in `COMPLIANCE.md` by interview: which regulations apply, the
regulated data classes and where they must never go, the controls as checkable
statements, the evidence each change must leave, and the change classes. Turn
vague answers into statements a reviewer can verify against a diff. Remove
example lines that don't apply.

## 5. Optional extras

Offer, don't push:

- `CODING_STANDARDS.md` for judgement-call rules reviewer-code should enforce,
  if the repo has none and the user has rules in mind.
- `GLOSSARY.md` is created during `/factory shape`; nothing to do now.
- If the user also uses Matt Pocock's skills, `/setup-matt-pocock-skills` lets
  `shape` mirror specs to GitHub issues.

## 6. Readiness check

Run a dry run of the mechanics without spending an agent:

```bash
git worktree add -b factory/setup-check <tmp path> <base>
# run the AGENTS.md setup in it, then the test command
git worktree remove --force <tmp path> && git branch -D factory/setup-check
```

Then print a checklist, one line each, ✓ or ✗ with the fix:
factory files committed on base · setup works in a fresh worktree · tests pass ·
PR mode: origin reachable, `gh` signed in, and the factory files pushed to `origin/<base>` (or merge_mode local) ·
lint runs on a single file · dev server starts (or none needed) · browser tool
present (or page lenses off) · COMPLIANCE.md complete (or lens off) ·
`factory/jobs/` ignored by git.

Finally, tell the user to commit whatever setup changed (AGENTS.md, config,
COMPLIANCE.md) on the base branch, and suggest a first small job:
`/factory quick <something small>`.
