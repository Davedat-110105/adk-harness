---
name: governed-workspace
description: Use when working with the user's Google Calendar or Gmail through the adk-harness tools — scheduling, checking availability, drafting mail — and whenever a call comes back held or blocked, to explain it and record an approval.
---

# Working in Google Workspace, under a policy gate

Calendar and Gmail operations are available as tools. Each one is judged on its
own before it runs, so reading a calendar and writing to it are separate
decisions.

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
see it, what it would say, when it would be. Then ask. If they agree, call
`remember_decision` with their reasoning, and the same question stops being
asked.

**Blocked** — the reply begins `BLOCKED by policy — nothing has run.` A decision,
not an error. Report the reason and stop. Do not retry, do not rephrase to get
past it, and do not reach for a different tool that achieves the same thing.

## What is deliberately refused

- **Sending mail.** You can draft; a person sends. Drafting is reversible and
  sending is not, so say that plainly rather than treating it as a limitation to
  work around.
- **Changing who can see a calendar or mailbox.** Access is granted by people.

## Recording a decision

`remember_decision` turns one answer into a standing precedent. Write the
person's reasoning, not a restatement of the action: *"Dave said internal review
slots on our own calendar are routine"* is useful in six months; *"approved"* is
not.

Do not offer to record a decision nobody made. A precedent answers a question
that was actually asked.

## Seeing what happened

`governance_audit` lists every decision this session — allowed, held, blocked, or
applied from an earlier precedent, with reasons. Use it when someone asks why
something did or did not happen, rather than reconstructing it from memory.
