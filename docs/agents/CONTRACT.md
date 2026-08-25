# The contract

`src/adk_harness/protocol.py` is frozen. Everything else in the SDK is written
against it, so changing it breaks every adapter at once. If you believe it must
change, say so and stop; do not change it.

```python
@dataclass(frozen=True, slots=True)
class HarnessSpec:
    id: str
    version: str
    capabilities: tuple[str, ...] = ()
    available: bool = False
    detail: str | None = None


@dataclass(frozen=True, slots=True)
class HarnessTurn:
    kind: str                      # one of HarnessTurn.KINDS
    text: str | None = None
    tool_name: str | None = None
    tool_args: dict[str, Any] = field(default_factory=dict)
    raw: Any = None

    KINDS = ("text", "tool_call", "tool_result", "usage", "error")


@runtime_checkable
class Harness(Protocol):
    spec: HarnessSpec

    async def discover(self) -> HarnessSpec: ...
    def run(self, prompt: str, *, cwd: str,
            session_id: str | None = None) -> AsyncIterator[HarnessTurn]: ...
    async def aclose(self) -> None: ...
```

## The five rules

**1. An adapter never decides whether an action is permitted.**

Adapters stream what the harness does. They do not filter it, do not refuse
tools, and do not consult policy. `CoactraGovernance` in `governance.py` is the
only thing in this repository that decides anything, and it decides for every
harness identically. An adapter that enforces its own rules produces a system
where the answer depends on which harness happened to run — which is the exact
failure this SDK exists to prevent.

**2. Import the vendor SDK inside `discover()`, never at module level.**

`from adk_harness.adapters.codex import CodexHarness` must succeed on a machine
where Codex is not installed. That means no vendor import at the top of the
file. Import inside `discover()`, catch `ImportError` and `FileNotFoundError`,
and return `HarnessSpec(available=False, detail=...)`.

**3. `discover()` must not raise.**

A missing, broken, or unauthenticated harness reports `available=False` with the
reason in `detail`. It does not raise. `HarnessRegistry.discover_all()` runs
every adapter concurrently; one broken adapter must not take down a fleet that
has working ones. The registry catches exceptions as a backstop, but relying on
that backstop loses the useful `detail` string.

**4. `raw` is opaque.**

Put the vendor's own payload in `HarnessTurn.raw` untouched. Nothing in the core
branches on its shape. It exists so a caller who knows they are talking to a
specific harness can reach through without the protocol growing vendor fields.
Never make core behaviour depend on it.

**5. `run()` streams. It never buffers a whole session.**

`run()` is an async generator. Yield each turn as it arrives. Do not collect
output and yield it at the end — a coding agent's value is visible in progress,
and a fleet orchestrator needs to see a turn before the run finishes.

## Mapping vendor events onto `HarnessTurn.kind`

Only these five kinds exist. Map onto them; do not invent a sixth.

| kind | when |
|---|---|
| `text` | assistant prose, reasoning summaries, plans |
| `tool_call` | the harness is about to use a tool; set `tool_name` and `tool_args` |
| `tool_result` | output of a tool; set `tool_name`, put the payload in `text` and/or `raw` |
| `usage` | token counts, cost, duration |
| `error` | the harness reported a failure; put the message in `text` |

Anything the vendor emits that does not fit — session-start banners, heartbeats,
deltas that only repeat previous content — should be dropped rather than
force-fitted. Dropping is not lossy: `raw` is available on the turns you do
yield.

## Session continuity

`run()` takes `session_id: str | None`. If the vendor supports resuming a
session, use it. If the vendor does not, **ignore the argument and document that
it is ignored** in the adapter docstring. Do not simulate continuity by
replaying history into the prompt — a caller that believes it has continuity
when it does not is worse off than one that knows it does not.

## Testing

- Tests must pass on a machine where the vendor tool is **not installed**. Fake
  the subprocess or the SDK; assert on the turns your adapter produces.
- A test that needs a real harness or real credentials is gated:
  `pytest.mark.skipif(os.getenv("ADK_HARNESS_LIVE") != "1", ...)`. See
  `tests/test_governance_live.py` for the existing pattern.
- Cover at minimum: discovery when the tool is absent, discovery when present,
  the full kind mapping, and `aclose()` terminating cleanly mid-stream.
