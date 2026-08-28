---
name: orchestrating-a-fleet
description: Use when a coding task would be better done by delegating to another coding agent — Codex, Claude Code, or opencode — rather than doing it here. Also use when a delegation comes back held or blocked, to explain what happened and record an approval.
---

# Orchestrating a fleet of coding agents

You have tools that hand work to other coding agents running on this machine.
Each one is a different model with a different harness, and every dispatch
passes a policy gate before anything runs.

## When to delegate rather than do it yourself

Delegate when the work is **self-contained and mechanical** — a rename across
many files, a test suite to run and fix, a migration applied consistently. Those
agents have their own file access and their own tools; handing over a whole task
is cheaper than narrating one.

Do it yourself when the work needs **the conversation you are already in**. A
delegated agent cannot see this thread. If explaining the task takes longer than
doing it, that is the answer.

Prefer **one agent doing a whole task** over several doing fragments. Splitting
work across agents that cannot see each other produces contradictory edits.

## Writing the instruction

The receiving agent sees only what you send. Give it:

- the goal, stated as an outcome rather than a series of steps
- the paths it should look at, if you know them
- what "done" looks like, so it can check its own work

Do not send it a summary of this conversation. Send it the task.

## What the gate does, and what to do about each answer

Every dispatch is judged before it runs. Three answers:

**Allowed** — the work happens, and you get the transcript back.

**Held for approval** — the reply begins `HELD FOR APPROVAL — nothing has run.`
That is literal: nothing happened. Tell the person what was going to run and why
it was held, and ask whether to proceed. If they approve, call
`remember_decision` with a short rationale in their words. The same question
will not be asked again.

**Blocked** — the reply begins `BLOCKED by policy — nothing has run.` This is a
decision, not an error. Report the reason and stop. Do not retry it, do not
rephrase the instruction to get past it, and do not route the same work to a
different agent. Working around a refusal is worse than the refusal.

## Recording a decision

`remember_decision` turns one human answer into a standing precedent. Two things
to get right:

- **Use their reasoning, not yours.** The rationale is the record of why a person
  agreed. "Dave said test files are safe to edit without review" is useful in six
  months; "approved" is not.
- **Do not offer to record a decision nobody made.** A precedent is recorded in
  answer to a question that was actually asked. If nothing is outstanding, the
  tool will say so.

## Seeing what happened

`governance_audit` lists every decision this session — what was allowed, held,
blocked, or applied from an earlier precedent, with reasons. Reach for it when
someone asks why something did or did not run, rather than guessing.
