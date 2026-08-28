# adk-harness — an Antigravity plugin

Delegate coding work to Codex, Claude Code or opencode from inside Antigravity,
with one policy gate in front of every dispatch and a decision memory so you are
asked once rather than every time.

## Install

```bash
pip install adk-harness
mkdir -p ~/.gemini/config/plugins
cp -r plugin ~/.gemini/config/plugins/adk-harness
```

Restart Antigravity. Whichever harnesses are installed on your machine appear as
tools; the ones that are not are simply absent, with no error.

For one project rather than globally, copy it to `.agents/plugins/adk-harness`
in the workspace instead.

## What it adds

| Tool | What it does |
|---|---|
| `run_codex`, `run_claude_code`, `run_opencode` | delegate a task, under policy |
| `governance_audit` | every decision this session, with reasons |
| `remember_decision` | approve once; stop being asked |

Antigravity is deliberately not offered as a tool — you are already talking to
it.

## What the gate decides

Reading and ordinary edits inside the workspace proceed. Anything hard to undo —
deleting, force-pushing, publishing, deploying — asks a person first. Anything
touching credentials is refused outright.

That policy lives in `adk_harness.mcp_server.EditorPolicy` and is meant to be
replaced with your own. `Policy` in coactra is a protocol with one async method,
so a real policy is a small class, not a framework.

## Configuration

| Variable | Meaning |
|---|---|
| `ADK_HARNESS_WORKSPACE` | root the agents may work in; outside it is denied |
| `ADK_PRECEDENTS` | SQLite file for decisions, so approvals survive restarts |

## Honest limits

- **Approvals are text, not a modal.** MCP has no confirmation channel, so a held
  action returns "nothing has run" and you approve by saying so.
- **The gate covers dispatch, not what an agent then does inside its own
  process.** Those tool calls never return through MCP. They are visible in the
  transcript, not individually approved.
- **Precedents are per-machine.** The store is SQLite. Two people running this
  each answer their own questions; sharing them needs a shared backend.
