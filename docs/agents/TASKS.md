# Open tasks

Each task is written to be done without reading the others. Read
[CONTRACT.md](CONTRACT.md) and [OWNERSHIP.md](OWNERSHIP.md) first.

Every task shares these requirements:

- Python 3.12+, `from __future__ import annotations`, full type annotations.
- Use the repository's virtualenv: `.venv/bin/python`, `.venv/bin/pytest`.
- Docstrings explain *why*, not *what*. Match the voice of `protocol.py` and
  `registry.py` — they are the house style.
- No vendor import at module level (contract rule 2).
- Tests pass with the vendor tool absent.

---

## Done, kept only as a record

Tasks 1–4 — the Codex and Claude Code adapters, `HarnessAgent` and
`build_fleet` — are landed and tested. Their full specifications were removed
once the code existed; the code and its tests are the specification now.

Task 5 (opencode) and Task 6 (a persistent precedent store) also landed.

A seventh, the hand-rolled Google Calendar harness, was written and then
**deleted**. ADK ships official Workspace toolsets, so wrapping Calendar in the
`Harness` protocol reimplemented them and gated at dispatch instead of per
operation. See `src/adk_harness/workspace.py`. It is recorded here because
"we built this and removed it, for this reason" is worth more to the next agent
than silence.


Both adapters, `HarnessAgent`, and `build_fleet` are landed, tested, and
deployed. See [OWNERSHIP.md](OWNERSHIP.md).

---

## Task 5 — the opencode adapter

**Owner:** unclaimed — claim it in `OWNERSHIP.md` before starting
**Files you write:** `src/adk_harness/adapters/opencode.py`,
`tests/test_adapter_opencode.py`

Two adapters can accidentally agree with each other. A third that is
structurally different is what turns "the protocol works" into evidence.
Codex is a CLI subprocess; Claude Code is a Python SDK; opencode is an HTTP
server with an OpenAPI spec. That third shape is the point of this task.

**Verify before you write.** Find out how opencode's server is actually
started and what its event stream looks like — from `opencode --help`, from its
OpenAPI document, from the installed binary. Do not write this from
recollection of the API. Record what you verified, and the version you verified
against, in the module docstring. If opencode is not installed on this machine,
say so and stop rather than guessing at an HTTP contract.

`httpx` is already declared as the `opencode` extra in `pyproject.toml`. Use it.
Everything in [CONTRACT.md](CONTRACT.md) applies unchanged — in particular,
import `httpx` inside `discover()`, and stream the response rather than reading
it to completion.

**Tests** must pass with no opencode server running. Fake the HTTP layer.

---

## Task 6 — a precedent store that survives a restart

**Owner:** unclaimed — claim it in `OWNERSHIP.md` before starting
**Files you write:** `src/adk_harness/stores.py`, `tests/test_stores.py`

This one matters more than it looks. `PrecedentStore` currently holds
precedents in memory. The demo runs on Cloud Run with `--min-instances=0`, so
the container scales to zero and forgets every answer a human ever gave.

The library's whole claim is "answer once, never be asked again". A precedent
that does not survive a restart is not a precedent.

**Do not edit `precedent.py`.** It is frozen, and its tests pin two safety
properties that must not be disturbed. Write a *subclass or wrapper* in a new
module that persists to SQLite (stdlib `sqlite3` — no new dependency), loading
existing precedents on construction and writing each one on `add()`.

Read `precedent.py` first. Note especially that `Applicability` is a frozen
dataclass with an `operator` drawn from a fixed `SUPPORTED` tuple, and that
`Precedent.review_after` is an optional datetime — round-tripping those
faithfully is most of the work. A precedent that comes back from disk with a
lost or altered predicate is worse than one that was never saved, because it
will silently admit calls the human never approved.

**Tests** must cover the round trip: save a precedent with several
`Applicability` predicates and a `review_after`, construct a fresh store over
the same file, and assert `match()` behaves identically to the in-memory store
for the same facts. Use `tmp_path`.

---

## Task 7 — the Antigravity adapter

**Owner:** integrator — landed
**Files:** `src/adk_harness/adapters/antigravity.py`,
`tests/test_adapter_antigravity.py`

Google Antigravity is a fourth integration shape and the only Google-native
one: a Python SDK that drives a compiled `localharness` binary shipped inside
its own platform wheel. That last part is why it earns a place rather than
being a second SDK adapter — "the package imports" and "the runtime exists" are
two different questions, and `discover()` has to answer both, plus a third
about credentials.

**What was verified**, against `google-antigravity==0.1.14` installed into
`.venv`, by reading the source under
`.venv/Lib/site-packages/google/antigravity/`:

- `Agent.chat()` returns a `ChatResponse` whose `.chunks` cursor is the only
  **ordered** view of the turn; `.thoughts` and `.tool_calls` are filtered
  views of it, and `ToolResult` appears on none of them but `.chunks`.
- `LocalAgentConfig.workspaces` is the file-access boundary and the closest
  thing the SDK has to `cwd`.
- `conversation_id` + `session_continuation_mode=RESUME` is genuine resume,
  but only against a stable `save_dir` — the config mints a throwaway
  `tempfile.mkdtemp()` otherwise. The adapter advertises `session_resume` only
  when it was given a `save_dir`, for that reason.
- Credentials are validated by the SDK's own `ModelEndpoint.validate_endpoint`,
  which `discover()` calls rather than reimplementing which environment
  variable means what.

No live `agent.chat()` was run: that spends real Gemini quota, the same line
task 1 draws for `codex exec`.

---

## Reporting back

When your task is done, report:

1. The files you created, and confirmation you touched nothing else.
2. The exact `pytest` command you ran and its output.
3. What you verified against the machine, and the versions you verified against.
4. Anything you wanted to change in a frozen file but did not.
5. Anything you had to guess, and what would confirm it.
