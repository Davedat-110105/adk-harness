---
name: governed-workspace
description: Use when working with the user's Google Workspace, or when a Workspace operation comes back held or blocked.
---

# Working in Google Workspace, under a policy gate

The `adk-harness` MCP server exposes one tool per Google API operation. Every
call is judged before it runs.

## Do not go looking

The tools and their parameters are already in your context. Reading schema
files under `~/.gemini`, listing the plugin directory, or opening this file
again tells you nothing new and costs the person tokens.

Do not run `gcloud`, hunt for credential files, or inspect the environment. If
something is not connected, call `workspace_status`. It reports the account,
the granted scopes, the tools, whether this client can be asked questions, and
the reason when there is nothing connected.

## Calling the tools

Parameters use Google's own REST names: `calendarId`, `maxResults`, `timeMin`.
Each tool declares which are required. Pass them as ordinary arguments.

Use `calendarId: "primary"` unless the person names another calendar.

Never invent a date, a time, or a recipient. Ask instead. A plausible guess
that lands in someone's calendar is worse than a question.

## The three answers

Every call returns an `outcome`, a `reason`, and an `evidence` record holding
the change hash.

**allowed** — it ran. Report what happened, with the id or link if there is one.

**held** — nothing ran. The server asked the person directly and they declined,
or this client cannot ask. Say what was about to happen in their terms: who
would see it, what it would say, when. Do not retry it, and do not approve it
yourself. You cannot; the question does not pass through you.

**blocked** — nothing ran, and nothing will. A decision, not an error. Report
the reason and stop. Do not rephrase it, and do not reach for a different tool
that achieves the same thing.

## What is deliberately refused

Sending mail. You can draft; a person sends. Drafting is reversible.

Changing who can see a calendar or a document. Access is granted by people.

## The audit trail

`governance_audit` lists every decision this session with its change hash, who
approved it, and the approval id. An approval is bound to the exact arguments
that were shown, so it cannot cover a different call.

`connect_ledger` points those records at a shared Google Cloud project. Never
guess the project id and never pass one you found somewhere. The person picks
it, or an administrator set it and nobody is asked.

## Connecting an account

`connect_workspace` opens Google's consent screen and the approved operations
become tools. Ask for the services the person named and no others. Requesting
Gmail when they asked about their calendar sends them through a consent screen
they did not want.
