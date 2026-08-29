# MCP servers with runtime elicitation and dynamic tool lists

Scope: the installed `mcp` Python SDK **1.29.1** at
`.venv/lib/python3.12/site-packages/mcp/`, cross-checked against the MCP spec
(`2025-11-25` revision) at modelcontextprotocol.io. All line numbers below are
relative to that installed package on this machine
(`/Users/datta/Documents/Projects/adk-harness/.venv/lib/python3.12/site-packages/mcp/...`).
Every claim is either a direct quote/paraphrase of source I read, or a spec
quote with URL. Anything I could not verify is called out explicitly in a
"Not verified" note.

---

## 1. Elicitation

### 1.1 `Context.elicit` — exact signature

`mcp/server/fastmcp/server.py:1206-1238`

```python
async def elicit(
    self,
    message: str,
    schema: type[ElicitSchemaModelT],
) -> ElicitationResult[ElicitSchemaModelT]:
    ...
    return await elicit_with_validation(
        session=self.request_context.session,
        message=message,
        schema=schema,
        related_request_id=self.request_id,
    )
```

`ElicitSchemaModelT` is a `TypeVar("ElicitSchemaModelT", bound=BaseModel)`
(`mcp/server/elicitation.py:14`) — `schema` must be a **Pydantic model
class**, not an instance, not a plain dict.

### 1.2 `Context.elicit_url` — exact signature

`mcp/server/fastmcp/server.py:1240-1273`

```python
async def elicit_url(
    self,
    message: str,
    url: str,
    elicitation_id: str,
) -> UrlElicitationResult:
    ...
    return await _elicit_url(
        session=self.request_context.session,
        message=message,
        url=url,
        elicitation_id=elicitation_id,
        related_request_id=self.request_id,
    )
```

`_elicit_url` is `mcp.server.elicitation.elicit_url` imported under an alias
(`mcp/server/fastmcp/server.py:49`).

### 1.3 What schema types are actually allowed

The spec (`https://modelcontextprotocol.io/specification/2025-11-25/client/elicitation`)
allows a fairly rich flat JSON Schema for form mode: string (with
`minLength`/`maxLength`/`pattern`/`format` in `email|uri|date|date-time`),
number/integer (`minimum`/`maximum`), boolean, and **enums** — both
single-select (`enum: [...]` or `oneOf` with `const`/`title` pairs) and
multi-select (`array` of the above). All of these are legal top-level
properties of a flat object schema per spec.

**The installed SDK's `Context.elicit()` enforces a strictly narrower
subset than the spec allows.** `mcp/server/elicitation.py:48-102`:

```python
# Primitive types allowed in elicitation schemas
_ELICITATION_PRIMITIVE_TYPES = (str, int, float, bool)

def _validate_elicitation_schema(schema: type[BaseModel]) -> None:
    """Validate that a Pydantic model only contains primitive field types."""
    for field_name, field_info in schema.model_fields.items():
        annotation = field_info.annotation
        if annotation is None or annotation is types.NoneType:
            continue
        elif _is_primitive_field(annotation):
            continue
        elif _is_string_sequence(annotation):
            continue
        else:
            raise TypeError(
                f"Elicitation schema field '{field_name}' must be a primitive type "
                f"{_ELICITATION_PRIMITIVE_TYPES}, a sequence of strings (list[str], etc.), "
                f"or Optional of these types. Nested models and complex types are not allowed."
            )
```

`_is_primitive_field` (lines 87-102) only accepts `str | int | float | bool`,
`Optional[...]` of those, or a `Union` of those plus string sequences.
`_is_string_sequence` (lines 71-84) accepts `list[str]`/`Sequence[str]`
only.

**Consequence: `Literal["a", "b"]` fields (Python's natural way to express an
enum) are rejected with `TypeError` at elicit-call time**, because
`get_origin(Literal[...])` is `Literal`, not `Union`, and it isn't a
`Sequence` subclass either — it falls straight into the `else: raise
TypeError` branch. So the high-level `ctx.elicit()` helper cannot produce the
spec's `enum`/`oneOf` form-field UI. If you need that, you must bypass
`ctx.elicit()` and call `ctx.session.elicit_form(message, requestedSchema=<raw
JSON-Schema dict you build by hand>)` directly (signature in §1.5), and do
your own `action`/`content` handling instead of getting an `ElicitationResult`.

The actual JSON payload sent over the wire is produced by
`schema.model_json_schema()` (`elicitation.py:124`) — i.e. whatever Pydantic
emits for your (primitive-only) model, sent verbatim as
`requestedSchema`.

### 1.4 The three response actions

`mcp/server/elicitation.py:17-45`:

```python
class AcceptedElicitation(BaseModel, Generic[ElicitSchemaModelT]):
    action: Literal["accept"] = "accept"
    data: ElicitSchemaModelT

class DeclinedElicitation(BaseModel):
    action: Literal["decline"] = "decline"

class CancelledElicitation(BaseModel):
    action: Literal["cancel"] = "cancel"

ElicitationResult = AcceptedElicitation[ElicitSchemaModelT] | DeclinedElicitation | CancelledElicitation
```

`elicit_with_validation` (lines 105-142) maps the raw `ElicitResult` from the
client into one of these:

```python
if result.action == "accept" and result.content is not None:
    validated_data = schema.model_validate(result.content)
    return AcceptedElicitation(data=validated_data)
elif result.action == "decline":
    return DeclinedElicitation()
elif result.action == "cancel":
    return CancelledElicitation()
```

Handle each by branching on `isinstance`/`.action`:

- **accept** — `result.data` is a validated instance of your schema model.
  Proceed with the operation.
- **decline** — user explicitly said no. Per spec
  (`.../client/elicitation`): "Handle explicit decline (e.g., offer
  alternatives)". Do not retry with the same prompt; treat as a real refusal.
- **cancel** — user dismissed without choosing (closed dialog, Escape, etc).
  Per spec: "Handle dismissal (e.g., prompt again later)". Safe to retry
  later, but don't assume refusal.

Note validation is **re-run server-side**: `schema.model_validate(result.content)`
will raise `pydantic.ValidationError` if the client's returned `content`
doesn't actually satisfy the schema (spec says clients "SHOULD" validate, so
the server cannot fully trust them). That exception is not caught by
`elicit_with_validation`, so a malformed client response currently propagates
as an unhandled `ValidationError` out of `ctx.elicit()` — wrap the call in
your own `try/except ValidationError` if you want to degrade gracefully
instead of the tool call failing with a stack trace.

### 1.5 `elicit_form` on the session (what `Context.elicit` calls into)

`mcp/server/session.py:391-418`:

```python
async def elicit_form(
    self,
    message: str,
    requestedSchema: types.ElicitRequestedSchema,   # = dict[str, Any]
    related_request_id: types.RequestId | None = None,
) -> types.ElicitResult:
    return await self.send_request(
        types.ServerRequest(
            types.ElicitRequest(
                params=types.ElicitRequestFormParams(
                    message=message,
                    requestedSchema=requestedSchema,
                ),
            )
        ),
        types.ElicitResult,
        metadata=ServerMessageMetadata(related_request_id=related_request_id),
    )
```

`ServerSession.elicit()` (lines 369-389) is kept only for backward
compatibility and forwards to `elicit_form`.

### 1.6 What happens when the client does not support elicitation

**Nothing built-in stops you from calling `ctx.elicit()`.** There is no
capability check inside `Context.elicit`/`Context.elicit_url` or inside
`ServerSession.elicit_form`/`elicit_url`. The request is sent unconditionally
via `BaseSession.send_request` (`mcp/shared/session.py:240-308`), which
simply:

1. Serializes the request, writes it to the client, and waits for a
   response (with a timeout that raises `McpError` with a `REQUEST_TIMEOUT`
   code, lines 290-303).
2. If the client returns a JSON-RPC error object, raises `McpError(response_or_error.error)`
   (line 306).

A client that doesn't implement `elicitation/create` will reply with a
standard JSON-RPC "Method not found" error (or, per spec, `-32602` "Invalid
params" if it declared the capability but not the requested mode — see
`.../client/elicitation#error-handling`). Either way, on the Python-SDK
server side that surfaces as an **`mcp.shared.exceptions.McpError`** raised
out of `ctx.elicit()` / `ctx.elicit_url()`. Your tool code must catch it
explicitly:

```python
from mcp.shared.exceptions import McpError

try:
    result = await ctx.elicit("Confirm?", ConfirmSchema)
except McpError:
    # client has no elicitation support (or doesn't support the mode used)
    ...  # fall back to a default / auto-decline behavior
```

**Recommended pattern: check first, so you never even try.**
`ServerSession.check_client_capability` (`mcp/server/session.py:132-169`)
lets you test this proactively:

```python
if ctx.session.check_client_capability(
    types.ClientCapabilities(elicitation=types.ElicitationCapability())
):
    result = await ctx.elicit(...)
else:
    result = None  # fall back
```

Caveat (verified by reading the method body, lines 153-154): the built-in
check only tests **presence** of `elicitation` capability —
`if capability.elicitation is not None and client_caps.elicitation is None: return False`
— it does **not** distinguish `form` vs `url` sub-capabilities even though
both `ElicitationCapability.form` and `ElicitationCapability.url`
(`mcp/types.py:319-331`) exist as separate optional fields. To specifically
check URL-mode support (needed before calling `elicit_url`), you must inspect
`client_caps` yourself — see §2.3.

### 1.7 Minimal working server: confirmation elicitation

```python
from mcp.server.fastmcp import FastMCP, Context
from mcp.shared.exceptions import McpError
from pydantic import BaseModel, Field

mcp = FastMCP("elicitation-demo")


class ConfirmDeletion(BaseModel):
    confirmed: bool = Field(description="Type yes to confirm deletion")
    reason: str = Field(default="", description="Optional reason for the audit log")


@mcp.tool()
async def delete_resource(resource_id: str, ctx: Context) -> str:
    """Delete a resource, asking the user to confirm first."""
    try:
        result = await ctx.elicit(
            message=f"Really delete resource {resource_id!r}? This cannot be undone.",
            schema=ConfirmDeletion,
        )
    except McpError:
        # Client declared no elicitation support at all.
        return f"Refused: cannot confirm deletion of {resource_id} (client has no elicitation support)"

    match result:
        case _ if result.action == "accept" and result.data.confirmed:
            # ... actually delete resource_id here ...
            return f"Deleted {resource_id} (reason: {result.data.reason or 'none given'})"
        case _ if result.action == "accept":
            return f"User declined via the confirmation field for {resource_id}"
        case _ if result.action == "decline":
            return f"User explicitly declined to delete {resource_id}"
        case _:  # "cancel"
            return f"User dismissed the confirmation dialog for {resource_id}; nothing deleted"


if __name__ == "__main__":
    mcp.run(transport="stdio")
```

(`result.action`/`result.data` pattern matches the union defined in
`mcp/server/elicitation.py:17-36`; `match`/`case` works because each variant
is a distinct Pydantic `BaseModel` subclass with a `Literal` `action` field.)

---

## 2. `elicit_url` specifically

### 2.1 Purpose

Per spec (`.../client/elicitation`, "URL Mode Elicitation Requests"): URL mode
"enables servers to direct users to external URLs for out-of-band
interactions that must not pass through the MCP client. This is essential
for auth flows, payment processing, and other sensitive or secure
operations." The docstring on `Context.elicit_url` in the installed SDK
(`mcp/server/fastmcp/server.py:1246-1257`) echoes this and lists: collecting
sensitive credentials, third-party OAuth flows, payment/subscription flows,
and "any interaction where data should not pass through the LLM context."

This is exactly the shape of a "hand the user a link to a local approval
page" use case: the approval UI runs out-of-band (e.g. a local HTTP server
you already run), and only the fact that the user *consented to open the
link* — not any data collected on that page — flows back through MCP.

### 2.2 How it differs from `elicit` (form mode)

| | `elicit` (form mode) | `elicit_url` (URL mode) |
|---|---|---|
| Request params type | `ElicitRequestFormParams` (`mcp/types.py:1836-1855`), `mode: Literal["form"]` | `ElicitRequestURLParams` (`mcp/types.py:1858-1880`), `mode: Literal["url"]` |
| Data exposed to the MCP client / LLM | Yes — `requestedSchema` + the submitted `content` both cross the MCP channel | No — only `message` and `url` cross the channel; whatever the user does on that page never touches the client or the LLM context |
| Client behavior on accept | Client shows a rendered form, collects field values, and returns them in `ElicitResult.content` | Client shows a consent prompt ("open this link?"), and on consent **opens the URL in a real browser/webview it does not let the LLM inspect** (spec: "MUST open the URL... in a secure manner that does not enable the client or LLM to inspect the content or user inputs", e.g. `SFSafariViewController` not `WKWebView`) |
| `ElicitResult.content` | populated on accept | **omitted** on accept — `AcceptedUrlElicitation` (`mcp/server/elicitation.py:39-43`) carries no data field at all |
| Completion signal | none needed — the response *is* the data | server-initiated: server must separately call `session.send_elicit_complete(elicitation_id)` once the out-of-band flow finishes (see §2.4) |

`mcp/types.py:1895-1912`, `ElicitResult`:

```python
class ElicitResult(Result):
    action: Literal["accept", "decline", "cancel"]
    content: dict[str, str | int | float | bool | list[str] | None] | None = None
    """
    The submitted form data, only present when action is "accept" in form mode.
    ...
    For URL mode, this field is omitted.
    """
```

### 2.3 What the client does with the URL (and what "accept" means)

Critically — and this is easy to get wrong — **`action: "accept"` on a URL
elicitation means only "the user consented to navigate to the URL," not
"the interaction is complete."** Spec quote (`.../client/elicitation`,
"Example: Request Sensitive Data"):

> The response with `action: "accept"` indicates that the user has
> consented to the interaction. It does not mean that the interaction is
> complete. The interaction occurs out of band and the client is not aware
> of the outcome until and unless the server sends a notification
> indicating completion.

The spec's client-side MUST/SHOULD list for handling the URL
(`.../client/elicitation`, "Safe URL Handling"):

- MUST NOT pre-fetch the URL or its metadata.
- MUST NOT open it without explicit user consent.
- MUST show the full URL for examination before consent.
- MUST open it in a way that doesn't let the client/LLM inspect page content
  or user input (named example: `SFSafariViewController` good, `WKWebView`
  bad).
- SHOULD highlight the domain to mitigate subdomain spoofing, warn on
  Punycode, and not render other elicitation fields as clickable links.

Server-side safety requirements you (the tool author) are responsible for
(spec, "Safe URL Handling" + "Phishing"): never put sensitive user data or a
pre-authenticated URL in the link; use HTTPS outside dev; and — because
anyone with the link can open it — **the server must independently verify
that the person who opens the URL is the same identity that triggered the
elicitation** (e.g. via a session cookie bound to the same `sub` claim from
your MCP auth layer), or you're exposed to the cross-user phishing/account-
takeover scenario the spec walks through in detail.

### 2.4 `send_elicit_complete` — signaling the out-of-band flow finished

`mcp/server/session.py:497-519`:

```python
async def send_elicit_complete(
    self,
    elicitation_id: str,
    related_request_id: types.RequestId | None = None,
) -> None:
    """Send an elicitation completion notification.
    This should be sent when a URL mode elicitation has been completed
    out-of-band to inform the client that it may retry any requests
    that were waiting for this elicitation.
    """
    await self.send_notification(
        types.ServerNotification(
            types.ElicitCompleteNotification(
                params=types.ElicitCompleteNotificationParams(elicitationId=elicitation_id)
            )
        ),
        related_request_id,
    )
```

This is a fire-and-forget **notification** (`notifications/elicitation/complete`,
`mcp/types.py:1776-1790`), not a request/response. Per spec it's a MAY, not a
MUST, and delivery is not guaranteed, so clients "must not wait indefinitely"
on it — always give the user their own manual retry control too (spec,
"Completion Notifications for URL Mode Elicitation").

The `Context` class does **not** expose a `send_elicit_complete` wrapper —
you must go through `ctx.session.send_elicit_complete(elicitation_id)`
directly (there is no `Context.elicit_complete` convenience method as of
1.29.1; verified by grep — no such name appears anywhere under
`mcp/server/fastmcp/`).

### 2.5 There's also a dedicated protocol error for "you need to do URL elicitation first"

Spec feature, code `-32042` (spec constant name `URLElicitationRequiredError`,
`.../client/elicitation#url-elicitation-required-error`): instead of
proactively calling `elicit_url` mid-tool-call and blocking on the response,
a server can immediately fail a `tools/call` with this error, embedding one
or more required URL elicitations in `error.data.elicitations`; the client
then drives the consent+open UX and retries the original call once it's
notified (or on its own initiative) — useful for OAuth-gate-first patterns.

The installed SDK has a purpose-built exception for exactly this,
`mcp.shared.exceptions.UrlElicitationRequiredError`
(`mcp/shared/exceptions.py:21-71`):

```python
class UrlElicitationRequiredError(McpError):
    """Servers can raise this error from tool handlers to indicate that the
    client must complete one or more URL elicitations before the request
    can be processed."""

    def __init__(self, elicitations: list[ElicitRequestURLParams], message: str | None = None):
        if message is None:
            message = f"URL elicitation{'s' if len(elicitations) > 1 else ''} required"
        error = ErrorData(
            code=URL_ELICITATION_REQUIRED,   # = -32042, mcp/types.py:178
            message=message,
            data={"elicitations": [e.model_dump(by_alias=True, exclude_none=True) for e in elicitations]},
        )
        super().__init__(error)
```

Usage — raise it directly from a tool handler instead of calling
`ctx.elicit_url()` and awaiting the response inline:

```python
from mcp.shared.exceptions import UrlElicitationRequiredError
from mcp.types import ElicitRequestURLParams

@mcp.tool()
async def read_private_file(path: str, ctx: Context) -> str:
    if not user_has_authorized(ctx):
        raise UrlElicitationRequiredError([
            ElicitRequestURLParams(
                mode="url",
                message="Authorization required to access your files",
                url="https://example.com/oauth/authorize?...",
                elicitationId="auth-001",
            )
        ])
    ...
```

`mcp/server/fastmcp/tools/base.py:114` and
`mcp/server/lowlevel/server.py:587` both reference "error response with
code -32042" in comments, confirming the low-level request dispatcher
knows to translate an `McpError` carrying this code into a proper
JSON-RPC error response rather than a generic tool failure. There's also a
`from_error(error: ErrorData)` classmethod for reconstructing the exception
client-side from the wire error, and `ElicitationRequiredErrorData`
(`mcp/types.py:1915-1924`) is the corresponding Pydantic model
(`elicitations: list[ElicitRequestURLParams]`) if you want to validate the
`error.data` payload against a schema rather than building it by hand.

### 2.6 Minimal example: elicit_url for a local approval page

```python
import uuid
from mcp.server.fastmcp import FastMCP, Context
from mcp.shared.exceptions import McpError

mcp = FastMCP("approval-demo")

# In-memory record of approvals your own local HTTP server fills in
# out-of-band (e.g. a FastAPI/Starlette app on http://127.0.0.1:8787).
_pending: dict[str, bool] = {}


@mcp.tool()
async def run_privileged_command(command: str, ctx: Context) -> str:
    elicitation_id = str(uuid.uuid4())
    approval_url = f"http://127.0.0.1:8787/approve/{elicitation_id}?cmd={command}"

    try:
        result = await ctx.elicit_url(
            message=f"Approve running: {command!r}?",
            url=approval_url,
            elicitation_id=elicitation_id,
        )
    except McpError:
        return "Client does not support URL-mode elicitation; refusing."

    if result.action != "accept":
        return f"User did not consent to opening the approval page ({result.action})"

    # The user is now (maybe) filling out the local approval page.
    # Your local HTTP server sets _pending[elicitation_id] when it's done,
    # then calls back into this process to fire the completion notice:
    #   await ctx.session.send_elicit_complete(elicitation_id)
    return (
        f"Approval requested at {approval_url}; call is on hold until the "
        f"local approval page reports back."
    )
```

The realistic version of this needs your local approval server and the MCP
server process to share state (a DB row, a queue, or — if in the same
process — just an `asyncio.Event`) so that whichever one finishes the
approval page's POST handler can also reach `ctx.session` to call
`send_elicit_complete`.

---

## 3. Dynamic tool lists at runtime

### 3.1 The actual API

`mcp/server/fastmcp/tools/tool_manager.py:44-73` — `ToolManager`:

```python
def add_tool(
    self,
    fn: Callable[..., Any],
    name: str | None = None,
    title: str | None = None,
    description: str | None = None,
    annotations: ToolAnnotations | None = None,
    icons: list[Icon] | None = None,
    meta: dict[str, Any] | None = None,
    structured_output: bool | None = None,
) -> Tool:
    """Add a tool to the server."""
    tool = Tool.from_function(fn, name=name, title=title, description=description,
                               annotations=annotations, icons=icons, meta=meta,
                               structured_output=structured_output)
    existing = self._tools.get(tool.name)
    if existing:
        if self.warn_on_duplicate_tools:
            logger.warning(f"Tool already exists: {tool.name}")
        return existing
    self._tools[tool.name] = tool
    return tool

def remove_tool(self, name: str) -> None:
    """Remove a tool by name."""
    if name not in self._tools:
        raise ToolError(f"Unknown tool: {name}")
    del self._tools[name]
```

`FastMCP` exposes these directly as public methods
(`mcp/server/fastmcp/server.py:401-448`):

```python
def add_tool(self, fn, name=None, title=None, description=None,
             annotations=None, icons=None, meta=None, structured_output=None) -> None:
    self._tool_manager.add_tool(fn, name=name, title=title, description=description,
                                 annotations=annotations, icons=icons, meta=meta,
                                 structured_output=structured_output)

def remove_tool(self, name: str) -> None:
    """Raises ToolError if the tool does not exist."""
    self._tool_manager.remove_tool(name)
```

So: `my_fastmcp_instance.add_tool(fn, name="foo")` /
`my_fastmcp_instance.remove_tool("foo")` are the real, public, documented
entry points — call them from inside a tool handler (or from a background
task, a webhook handler, etc.) any time after the server object exists.

Every call to the `tools/list` handler re-reads the live dict —
`ToolManager.list_tools()` is `return list(self._tools.values())`
(`tool_manager.py:39-41`), and FastMCP's `list_tools` wraps that directly
(`mcp/server/fastmcp/server.py:319-323`, not shown above but confirmed by
reading around line 321: `tools = self._tool_manager.list_tools()`). There
is no separate cache to invalidate on the FastMCP side.

### 3.2 Emitting `notifications/tools/list_changed`

**This is entirely your responsibility — FastMCP's `add_tool`/`remove_tool`
never call it for you.** Verified with:

```
grep -rn "send_tool_list_changed\|ToolListChangedNotification\|list_changed" \
  mcp/server/fastmcp/ mcp/server/lowlevel/
```

which returns **zero matches** in either directory tree. The only place the
notification is actually sendable from is `ServerSession.send_tool_list_changed`
(`mcp/server/session.py:489-491`):

```python
async def send_tool_list_changed(self) -> None:
    """Send a tool list changed notification."""
    await self.send_notification(types.ServerNotification(types.ToolListChangedNotification()))
```

You must call `await ctx.session.send_tool_list_changed()` yourself,
immediately after mutating the tool set:

```python
from mcp.server.fastmcp import FastMCP, Context

mcp = FastMCP("dynamic-tools-demo")


def _secret_tool(x: int) -> int:
    """Only reachable after unlock_secret_tool is called."""
    return x * 2


@mcp.tool()
async def unlock_secret_tool(ctx: Context) -> str:
    mcp.add_tool(_secret_tool, name="secret_tool", description="Doubles a number")
    await ctx.session.send_tool_list_changed()
    return "secret_tool is now registered"


@mcp.tool()
async def lock_secret_tool(ctx: Context) -> str:
    try:
        mcp.remove_tool("secret_tool")
    except Exception:  # mcp.server.fastmcp.exceptions.ToolError if already removed
        return "secret_tool was already removed"
    await ctx.session.send_tool_list_changed()
    return "secret_tool removed"


if __name__ == "__main__":
    mcp.run(transport="stdio")
```

### 3.3 Caveat #1 (important, verified): FastMCP never advertises `tools.listChanged: true`

The server's own capability advertisement — what the client sees at
`initialize` time and is supposed to use to decide whether it should ever
expect this notification — comes from
`mcp.server.lowlevel.server.Server.get_capabilities`
(`mcp/server/lowlevel/server.py:193-237`):

```python
if types.ListToolsRequest in self.request_handlers:
    tools_capability = types.ToolsCapability(listChanged=notification_options.tools_changed)
```

`notification_options.tools_changed` defaults to `False`
(`NotificationOptions.__init__`, `mcp/server/lowlevel/server.py:112-121`).
FastMCP calls `create_initialization_options()` with **no arguments** in
both transports:

- stdio: `mcp/server/fastmcp/server.py:757-764`
- SSE: `mcp/server/fastmcp/server.py:842-854`

```python
await self._mcp_server.run(
    read_stream, write_stream,
    self._mcp_server.create_initialization_options(),   # <-- no NotificationOptions passed
)
```

I grepped the entire `mcp/server/fastmcp/server.py` for `NotificationOptions`
and got **zero matches** — there is no `FastMCP(...)` constructor argument
and no settings field that lets you turn `tools.listChanged` on. So, as
shipped, a FastMCP server that calls `add_tool`/`remove_tool` +
`send_tool_list_changed()` will send the notification, but will have told
the client during `initialize` that it never would
(`capabilities.tools.listChanged: false`). A strictly spec-compliant client
is allowed to ignore or not even listen for a notification it wasn't told to
expect.

**Workaround** (bypasses `FastMCP.run()`/`run_stdio_async()`, drives the
underlying lowlevel `Server` yourself): `FastMCP._mcp_server` is the
`mcp.server.lowlevel.Server` instance (`mcp/server/fastmcp/server.py:209`,
attribute assigned in `__init__`). Reimplement the run loop:

```python
import anyio
from mcp.server.lowlevel.server import NotificationOptions
from mcp.server.stdio import stdio_server

async def run_stdio_with_tool_notifications(mcp: FastMCP) -> None:
    async with stdio_server() as (read_stream, write_stream):
        init_options = mcp._mcp_server.create_initialization_options(
            notification_options=NotificationOptions(tools_changed=True),
        )
        await mcp._mcp_server.run(read_stream, write_stream, init_options)

anyio.run(run_stdio_with_tool_notifications, mcp)
```

This relies on the private `_mcp_server` attribute (no leading-underscore
exemption documented, so treat it as an implementation detail that could
change between SDK versions — pin your `mcp` version if you take this
route).

### 3.4 Caveat #2: ordering relative to the client's next `tools/list`

Because FastMCP disables schema-cache validation
(`self._mcp_server.call_tool(validate_input=False)(self.call_tool)`,
`mcp/server/fastmcp/server.py:312`), a newly added tool is callable
**immediately** after `add_tool()` returns, even before any
`notifications/tools/list_changed` is sent and even before the client ever
calls `tools/list` again — FastMCP doesn't gate `tools/call` on the tool
being "known" to the client. The notification is purely advisory, to tell a
client's UI/tool-cache to re-fetch; it is not required for the new tool to
be invocable. (For reference, the lowlevel `Server`'s own generic path *does*
maintain a `_tool_cache` used for input validation and lazily refreshes it
on a cache miss — `mcp/server/lowlevel/server.py:160,449-496` — but FastMCP
opts out of that path via `validate_input=False`, so this cache is
irrelevant to FastMCP-based servers.)

Practical ordering guidance:

1. Mutate the tool set (`add_tool`/`remove_tool`) — takes effect
   immediately for `tools/call` purposes on FastMCP.
2. Send `notifications/tools/list_changed` right after, in the same
   handler, so any client that *is* listening refreshes its UI/cache
   promptly. There's no requirement to send it "before" anything else —
   it's a notification, not a request, so there's no response to wait for
   and no risk of a race with the client's next `tools/list` (that request
   will simply return whatever `self._tools` currently contains,
   independent of notification delivery timing).
3. If you rely on `tools.listChanged` semantics being honored by a strict
   client, apply the Caveat #1 workaround so the capability is actually
   advertised as `true`.
4. Removing a tool the client is mid-call on isn't guarded against by the
   SDK — there's no in-flight-call tracking in `ToolManager`. If you must
   support that, add your own bookkeeping.

---

## 4. Transports: stdio vs streamable-http

### 4.1 Server construction: what changes

With FastMCP, tool/resource/prompt registration code is **transport-agnostic
by construction** — you build one `FastMCP` instance and only the final
`run(...)` call (or entrypoint) differs:

```python
mcp = FastMCP("my-server")

@mcp.tool()
async def my_tool(x: int, ctx: Context) -> str:
    ...

# stdio
mcp.run(transport="stdio")

# streamable-http
mcp.run(transport="streamable-http")
```

`FastMCP.run` (`mcp/server/fastmcp/server.py:283-304`):

```python
match transport:
    case "stdio":
        anyio.run(self.run_stdio_async)
    case "sse":
        anyio.run(lambda: self.run_sse_async(mount_path))
    case "streamable-http":
        anyio.run(self.run_streamable_http_async)
```

- `run_stdio_async` (`server.py:757-764`) opens
  `mcp.server.stdio.stdio_server()` (wraps process stdin/stdout as anyio
  streams) and calls `self._mcp_server.run(read_stream, write_stream,
  self._mcp_server.create_initialization_options())` directly — no HTTP
  server, no auth middleware, no routes.
- `run_streamable_http_async` (`server.py:781-794`) builds a Starlette app
  via `self.streamable_http_app()` and serves it with `uvicorn`.
  `streamable_http_app()` (`server.py:955+`) constructs a
  `StreamableHTTPSessionManager` (`mcp/server/streamable_http_manager.py`)
  configured from `self.settings.json_response` /
  `self.settings.stateless_http`, wraps it in `StreamableHTTPASGIApp`, and —
  only if `self.settings.auth` is set — wraps the routes in
  `RequireAuthMiddleware` (`server.py:1020`, `mcp/server/auth/middleware/bearer_auth.py:76-152`)
  which enforces a Bearer token via a `TokenVerifier` you provide.

Constructor-level knobs that only matter for the HTTP transports
(`mcp/server/fastmcp/server.py:97-131`, `Settings`):
`host`, `port`, `mount_path`, `sse_path`, `message_path`,
`streamable_http_path`, `json_response`, `stateless_http`,
`max_request_body_size`, `auth`, `transport_security`. None of these exist
or matter for stdio.

`stateless_http` (docstring: "Define if the server should create a new
transport per request") controls whether `StreamableHTTPSessionManager`
keeps a persistent `ServerSession` across requests or spins up a fresh one
per HTTP request — this has no stdio analog since stdio is inherently one
persistent session for the process's lifetime.

### 4.2 Reading a per-request `Authorization` header — the one-code-path approach

The task's goal — "one code path where only credential lookup differs" — is
achievable because of how `RequestContext.request` is populated per
transport. `RequestContext` (`mcp/shared/context.py:19-31`) carries a
generic `request: RequestT | None = None` field. Its value comes from
`ServerMessageMetadata.request_context`
(`mcp/shared/message.py:30-35`, `request_context: object | None = None`),
which is threaded through by `mcp.server.lowlevel.server.Server._handle_request`
(`mcp/server/lowlevel/server.py:741-775`):

```python
request_data = None
if message.message_metadata is not None and isinstance(message.message_metadata, ServerMessageMetadata):
    request_data = message.message_metadata.request_context
    ...
token = request_ctx.set(
    RequestContext(
        message.request_id, message.request_meta, session, lifespan_context,
        Experimental(...),
        request=request_data,   # <-- becomes ctx.request_context.request
        ...
    )
)
```

**In the streamable-http transport**, that `request_context` is a real
Starlette `Request` object. `mcp/server/streamable_http.py:246-276`,
`_create_session_message`:

```python
metadata = ServerMessageMetadata(request_context=request)  # `request: Request` (starlette.requests.Request)
return SessionMessage(message, metadata=metadata)
```

(confirmed import at `mcp/server/streamable_http.py:25`:
`from starlette.requests import Request`). This is populated for every
inbound POST — see the same pattern at lines 268-274, 543, and 566 of that
file.

**In the stdio transport**, no such metadata is ever attached —
`mcp/server/stdio.py:70`: `session_message = SessionMessage(message)` (no
`metadata=` argument at all), so `ctx.request_context.request` is always
`None` for stdio.

That difference is exactly the seam you want:

```python
import os
from mcp.server.fastmcp import FastMCP, Context

mcp = FastMCP("auth-demo")


def _resolve_credential(ctx: Context) -> str | None:
    """One code path: only the *lookup* differs by transport."""
    request = ctx.request_context.request  # starlette.requests.Request | None
    if request is not None:
        # streamable-http: read the header the client actually sent
        return request.headers.get("authorization")
    # stdio: no per-request header exists; fall back to a local/dev credential
    return os.environ.get("MY_TOOL_API_TOKEN")


@mcp.tool()
async def call_upstream_api(ctx: Context) -> str:
    token = _resolve_credential(ctx)
    if token is None:
        return "No credential available for this transport/session"
    # ... use `token` against the real upstream API ...
    return "called upstream with resolved credential"
```

This works whether the tool is invoked over stdio or streamable-http without
any `if transport == ...` branching in the tool body — the only thing that
changes is where `_resolve_credential` finds the value.

If you additionally configure `FastMCP(auth=AuthSettings(...),
token_verifier=...)`, the SDK's own `RequireAuthMiddleware`
(`mcp/server/auth/middleware/bearer_auth.py:76-152`) will already have
parsed and verified the `Authorization: Bearer <token>` header for you
*before* your handler runs, and stashed a `AuthenticatedUser` (with
`.access_token: AccessToken`, `.scopes`) on the ASGI `scope["user"]`
(`bearer_auth.py:13-19`, `54-73`). That's a second, higher-level way to get
at the same header, but it requires the full OAuth resource-server
machinery (`TokenVerifier`, `AuthSettings`) to be wired up; reading
`request.headers.get("authorization")` directly off
`ctx.request_context.request` (as above) works with zero additional
configuration and is the minimal one-path solution.

### 4.3 Summary table

| | stdio | streamable-http |
|---|---|---|
| Entry point | `mcp.run_stdio_async()` → `mcp.server.stdio.stdio_server()` | `mcp.run_streamable_http_async()` → `mcp.streamable_http_app()` + uvicorn |
| Transport-only `Settings` fields | none apply | `host`, `port`, `streamable_http_path`, `json_response`, `stateless_http`, `max_request_body_size`, `auth`, `transport_security` |
| `ctx.request_context.request` | always `None` (`mcp/server/stdio.py:70`) | a `starlette.requests.Request` (`mcp/server/streamable_http.py:268-274`) |
| Per-request Authorization header | not applicable (no HTTP request exists) | `ctx.request_context.request.headers.get("authorization")`, or via `RequireAuthMiddleware`/`TokenVerifier` if `auth=` configured |
| Sessions | one session = one process lifetime | one or many sessions per process, optionally stateless (new transport per request) via `stateless_http=True` |

---

## 5. Capability negotiation for elicitation (fallback pattern)

### 5.1 Where client capabilities land

During `initialize`, the client sends `InitializeRequestParams.capabilities:
ClientCapabilities`. The server session stores it:
`ServerSession._received_request`, case `types.InitializeRequest(params=params)`
→ `self._client_params = params` (`mcp/server/session.py:176-180`), exposed
via the `client_params` property (`session.py:107-109`).

`ClientCapabilities.elicitation` (`mcp/types.py:417-434`):

```python
class ClientCapabilities(BaseModel):
    ...
    elicitation: ElicitationCapability | None = None
    """Present if the client supports elicitation from the user."""
```

`ElicitationCapability` (`mcp/types.py:307-331`):

```python
class FormElicitationCapability(BaseModel):
    model_config = ConfigDict(extra="allow")

class UrlElicitationCapability(BaseModel):
    model_config = ConfigDict(extra="allow")

class ElicitationCapability(BaseModel):
    """Clients must support at least one mode (form or url)."""
    form: FormElicitationCapability | None = None
    url: UrlElicitationCapability | None = None
```

Per spec (`.../client/elicitation#capabilities`): an **empty**
`"elicitation": {}` object is, "for backwards compatibility," equivalent to
declaring `form`-only support. So `elicitation is not None` but both `.form`
and `.url` being `None` should still be read as "form mode is supported."

### 5.2 The built-in generic check (coarse — presence only)

`mcp/server/session.py:132-169`, the relevant branch:

```python
if capability.elicitation is not None and client_caps.elicitation is None:
    return False
```

Use it for a coarse "does this client support elicitation at all" gate:

```python
import mcp.types as types

if ctx.session.check_client_capability(
    types.ClientCapabilities(elicitation=types.ElicitationCapability())
):
    ...  # safe to try ctx.elicit()
else:
    ...  # fall back — client declared no elicitation support
```

Note `client_params` (and hence this check) is only populated **after**
`initialize` completes — inside a tool call it always will be, since
`tools/call` cannot arrive before `initialize` per the lifecycle spec, but
don't call this before initialization if you're doing anything unusual with
raw sessions.

### 5.3 Mode-specific check (needed for `elicit_url` specifically) — write this yourself

Because `check_client_capability` doesn't look at `.form`/`.url`
sub-fields, distinguishing "supports form" from "supports URL mode" needs a
small helper against the raw `client_params`:

```python
def supports_url_elicitation(ctx: Context) -> bool:
    params = ctx.session.client_params  # types.InitializeRequestParams | None
    if params is None:
        return False
    elicitation = params.capabilities.elicitation
    if elicitation is None:
        return False
    # spec: empty {} == form-only, so url support requires an explicit `url` object
    return elicitation.url is not None


def supports_form_elicitation(ctx: Context) -> bool:
    params = ctx.session.client_params
    if params is None:
        return False
    elicitation = params.capabilities.elicitation
    if elicitation is None:
        return False
    # empty {} is treated as form-only per spec backwards-compat rule
    return elicitation.form is not None or elicitation.form is None
```

(`supports_form_elicitation` above intentionally treats "elicitation present
but both `form` and `url` are `None`" as form-capable, per the spec's
explicit backwards-compatibility clause; adjust if you want to be stricter
than the spec requires.)

### 5.4 Recommended fallback structure

```python
@mcp.tool()
async def do_sensitive_thing(ctx: Context) -> str:
    if supports_url_elicitation(ctx):
        result = await ctx.elicit_url(
            message="Approve this action?",
            url="https://approvals.example.com/...",
            elicitation_id="...",
        )
        if result.action != "accept":
            return "not approved"
        return "approval flow started out-of-band"

    if supports_form_elicitation(ctx):
        result = await ctx.elicit("Confirm this action?", ConfirmSchema)
        if not (result.action == "accept" and result.data.confirmed):
            return "not confirmed"
        return "confirmed inline"

    # No elicitation support at all — degrade to a safe default,
    # e.g. refuse destructive actions outright rather than silently proceeding.
    return "cannot confirm: client has no elicitation support; refusing by default"
```

This mirrors the spec's own posture: it never promises elicitation is
available, and expects well-behaved servers to have a defined, safe
fallback rather than assuming any given mode (or elicitation at all) is
present.

---

## Sources

- Installed package: `mcp==1.29.1` at
  `/Users/datta/Documents/Projects/adk-harness/.venv/lib/python3.12/site-packages/mcp/`
  (all file:line citations above).
- Spec: `https://modelcontextprotocol.io/specification/2025-11-25/client/elicitation`
- Spec: `https://modelcontextprotocol.io/specification/2025-11-25/server/tools`

## Not verified (flagged, not asserted)

1. Whether any FastMCP `Settings`/constructor option in a *different* minor
   version than 1.29.1 exposes `NotificationOptions` (to advertise
   `tools.listChanged: true` without the workaround in §3.3) — I only
   verified its absence in this exact installed version (grep returned zero
   matches for `NotificationOptions` in `mcp/server/fastmcp/server.py`).
2. I did not test any of the example code in this document against a live
   MCP client; all examples are constructed directly from the read APIs
   (signatures, types, control flow) but not executed end-to-end.
3. The `Context` class exposes no `client_id`-based per-user auth helper
   beyond the raw `request` object described in §4.2 and the OAuth
   `AuthenticatedUser`/`AccessToken` machinery in §4.2's closing paragraph —
   I did not exhaustively audit `mcp/server/auth/` beyond
   `bearer_auth.py`, so there may be additional provider-specific helpers
   (e.g. for introspection-based verifiers) not covered here.
