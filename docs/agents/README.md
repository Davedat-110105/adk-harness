# Working on adk-harness as a coding agent

This folder is the coordination surface for every agent that writes code in this
repository — Claude Code, Codex, opencode, or a human driving one of them.
Several agents work here at the same time. These documents are what keep them
from overwriting each other.

Read these before writing anything:

1. **[CONTRACT.md](CONTRACT.md)** — the rules that do not change. The adapter
   protocol is frozen; the rules exist so that adapters written independently
   still compose.
2. **[OWNERSHIP.md](OWNERSHIP.md)** — who owns which file right now, and which
   files nobody may touch without clearing it first.
3. **[TASKS.md](TASKS.md)** — the open work, each task written so it can be done
   without reading the others.

## The short version

- Claim your task in `OWNERSHIP.md` before you start. If a file you need is
  already claimed, stop and say so rather than editing it anyway.
- Write only the files your task names. If your change seems to require editing
  a file outside your claim, report that instead of doing it — the integrator
  will handle it.
- Do not run `git commit`, `git push`, or any other git write. The integrator
  commits.
- Verify facts against the machine, not against memory. Run `--help`, import the
  package, read the installed source. Documentation about a vendor SDK written
  from recollection has already been wrong once in this repository.
- Every test must pass on a machine where the vendor tool is **not** installed.
  Live tests that need real credentials are gated behind an environment
  variable.

## What this project is

`adk-harness` turns any coding-agent harness — Claude Code, Codex, opencode —
into a Google ADK agent, and puts one governance gate in front of all of them.

The gate is a Coactra `Policy`. When policy says a human must decide, the gate
first checks whether a human already decided this exact question under
conditions that still hold. If so, it applies that precedent instead of
interrupting. That precedent loop is the centerpiece of the project, and it
lives in `src/adk_harness/precedent.py`. Adapters do not participate in it and
must not try to.
