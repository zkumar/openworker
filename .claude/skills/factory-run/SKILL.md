---
name: factory-run
description: Software Factory+ job runner. Only invoked by the /factory command (or typed as /factory-run <command> <job-id>) to run one job's build, review and approval in a fresh forked context that never sees the main conversation.
context: fork
agent: factory-runner
---

# Factory runner task

Arguments: `$ARGUMENTS`

The first word is the command (`run`, `next`, `quick`, `watch`,
`characterize` or `rework`); the rest is its argument (a job id, a feature line or an
area). You run that one command for one job, from start to the next point where
a person must decide, and then you stop.

0. **Only those six commands.** Anything else (`approve`, `shape`, `setup`,
   `onboard`, `import`, `show`, `status`, `retro`, or no command) belongs to
   the root: change nothing and hand back at once with
   `<arguments> · not a runner command` / `Waiting for: the root to run it itself` /
   `Next: root runs /factory <arguments> in the conversation` / `Tokens: 0`.
1. Read `.claude/skills/factory/SKILL.md`, `.claude/skills/factory/run.md` and
   `factory/config.md`, then follow the playbook section for the command:
   **/factory run**, **/factory next**, **/factory quick**, **/factory watch** or
   **/factory characterize**. Read `templates.md` and `visuals.md` when a step
   points to them.
2. Everything you know comes from the repo and the job folder
   `factory/jobs/<job-id>/`. You don't see the conversation that started you; if
   something you need isn't in the files or the arguments, stop and say so.
3. Follow the rules in `.claude/agents/factory-runner.md`: never ask the user,
   stop at decision points, and leave delivery to the root conversation when
   config says `delivery_control: root`.
4. Your last message is the hand-back described there. Keep it short: the root
   conversation pays for every line of it.
