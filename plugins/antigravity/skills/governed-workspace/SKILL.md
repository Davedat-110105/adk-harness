---
name: governed-workspace
description: Use when working with the user's Google Workspace through the governed Antigravity application, especially when an operation is held or blocked.
---

# Working in Google Workspace, under a policy gate

Calendar, Gmail drafts, Docs, and Sheets operations are exposed only when the
local application has configured that service. Each operation is judged on its
own before it runs.

## Calling the tools

Parameters go in `arguments`, in **snake_case** — `calendar_id`, `max_results`,
`time_min` — not the camelCase used in Google's REST documentation. Sending
`calendarId` raises a `KeyError` on the field name.

Use `calendar_id: "primary"` unless the person names another calendar.

Never invent a date, a time, or a recipient. If one is missing, ask. A plausible
guess that lands in someone's calendar is worse than a question.

## The three answers, and what to do with each

**Allowed** — it ran. Report what happened, with the id or link if there is one.

**Held for approval** — the reply begins `HELD FOR APPROVAL — nothing has run.`
That is literal. Say what was about to happen, in the person's terms: who would
see it, what it would say, when it would be. Then ask. A trusted host may
record an approval after the person answers; the model cannot approve itself
or call a decision recording tool.

**Blocked** — the reply begins `BLOCKED by policy — nothing has run.` A decision,
not an error. Report the reason and stop. Do not retry, do not rephrase to get
past it, and do not reach for a different tool that achieves the same thing.

## What is deliberately refused

- **Sending mail.** You can draft; a person sends. Drafting is reversible and
  sending is not, so say that plainly rather than treating it as a limitation to
  work around.
- **Changing who can see a calendar or mailbox.** Access is granted by people.

## Recording a decision

The trusted host records the actor, exact request hash, scope, policy version,
resource versions, expiry, and reasoning. Do not offer to record a decision
nobody made. Activity events are evidence and do not grant permission.

## Current boundary

Local discovery and governed Workspace orchestration are supported. Use the
trusted local UI for setup handoff and consent gated preview, submission,
manual sync, result download, and unknown operation recovery. Cloud deployment,
popup login, and external Workspace execution remain live proof boundaries;
report them as awaiting authorization when not explicitly enabled.
