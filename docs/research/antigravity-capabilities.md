# Google Antigravity 2.11.0 (macOS) — MCP & in-chat UI capability audit

Research date: 2026-08-29. Method: read-only. Primary evidence source is
`strings -a` output of the Go language-server binary:

```
/Applications/Antigravity.app/Contents/Resources/bin/language_server
```

(Mach-O arm64, 146 MB, built 2026-08-26; contains a vendored copy of
`github.com/modelcontextprotocol/go-sdk` under
`google3/third_party/golang/github_com/modelcontextprotocol/go_sdk/v/v0/mcp`,
plus Google-internal protobuf packages `exa.cascade_plugins_pb` and
`exa.cortex_pb`.) Secondary sources: the local config/skill files listed in
the task. **No code was executed** — no `execve`, no attach, no network
calls to the binary. All "line N" references below are line numbers in a
`strings -a` dump of the binary, reproducible with the commands quoted in
each section (§8 has the full setup).

Caveat that applies to every finding below: **strings are evidence of
presence, not proof of behavior.** A string appearing in the binary confirms
the code path exists in the compiled program; it does not confirm the path
is reachable, enabled by default, or wired to the UI the way its name
suggests. Where I could not find a string that would let me distinguish
those, I say so.

---

## Summary table

| # | Question | Verdict |
|---|---|---|
| 1 | MCP protocol revision(s) | **CONFIRMED** (presence): a single string blob lists `2026-07-28`, `2025-11-25`, `2025-06-18`, `2025-03-26`, `2024-11-05` immediately adjacent to `roots/list`, `tools/list`, `tools/call` — almost certainly the client's supported-version list. Independently **CONFIRMED**: features that only exist in the `2025-06-18` revision (elicitation, `resource_link` content blocks) are implemented, so the effective floor is `2025-06-18`. Which single version is sent as `protocolVersion` in `initialize` is **INFERRED**, not directly observed (strings don't show negotiation logic). Note: `2026-07-28` is not one of the four candidate dates given in the task — it looks like a newer/draft revision vendored into this SDK copy.
| 2 | MCP client methods/notifications | **CONFIRMED** for all of: `tools/list`, `tools/call`, `notifications/tools/list_changed`, `elicitation/create`, `sampling/createMessage`, `resources/read`, `resource_link`, `roots/list`, `prompts/list`, `prompts/get`. Also confirmed present: `resources/list`, `resources/subscribe`, `completion/complete`, `logging/setLevel`, `notifications/resources/list_changed`, `notifications/prompts/list_changed`, `notifications/roots/list_changed`, `notifications/progress`, plus two strings not in the public spec: `notifications/elicitation/complete` and `notifications/subscriptions/acknowledged`.
| 3 | Elicitation shape | **CONFIRMED**: `ElicitParams{Mode, Message, RequestedSchema, URL, ElicitationID}` from the go-sdk's own reflect metadata. Two `Mode` values are exercised in error strings: `"form"` (schema-driven) and `"url"`. **CONFIRMED** `elicit_url`/URL-mode elicitation exists and is capability-negotiated separately from form mode. **CONFIRMED** enum-with-titles (`const`/`title` pairs) is validated. String/number/boolean support is **INFERRED** (generic JSON-Schema validator is reused, not elicitation-specific type checks) rather than directly quoted. No evidence of *how* the form is rendered (no HTML/CSS strings tied to elicitation).
| 4 | MCP server config schema | **CONFIRMED**, two distinct schemas found: (a) the plugin-*marketplace* templates `CascadePluginLocalConfig` / `CascadePluginRemoteConfig` (proto pkg `exa.cascade_plugins_pb`) named in the task, and (b) the actual runtime config `McpServerSpec` / `McpOAuthConfig` (proto pkg `exa.cortex_pb`), which is far richer. **CONFIRMED absent**: `authorization_url`, `token_url`, `redirect_uri`, `scopes` do not appear as fields of either schema, or anywhere else attached to MCP. `McpOAuthConfig` has exactly two fields: `client_id`, `client_secret`. `auth_provider_type` exists only on the *remote* config types (`CascadePluginRemoteConfigTemplate`, `McpServerSpec`), never on the local/stdio ones, and its enum (`McpAuthProviderType`) has exactly two values: `MCP_AUTH_PROVIDER_TYPE_UNSPECIFIED` and `MCP_AUTH_PROVIDER_TYPE_GOOGLE_CREDENTIALS`.
| 5 | `<agent-embed>` mechanism | **CONFIRMED** (from `SKILL.md`, quoted in full): file-based iframe embed, 500 px inline height cap, theme CSS variables injected, all external CDNs blocked by CSP except one allowlisted `gstatic.com/antigravity` Tailwind script. In the binary itself: only 4 occurrences of the string `agent-embed`, and all 4 are inside this same `SKILL.md` text baked into the binary as a prompt/doc string — **CONFIRMED no separate spec exists elsewhere in the binary.** **CSP mechanics (size limits beyond 500px, `connect-src`, sandbox flags): NOT FOUND.** The binary contains no `connect-src`/`script-src`/`frame-src`/`default-src`/`allow-scripts`/`allow-same-origin` strings at all. The single `Content-Security-Policy` string in the whole binary has no MCP/embed-specific context around it. **The `fetch()`-to-`127.0.0.1` question is UNRESOLVED** — I found no string in this binary that allows or forbids it either way; the enforcement point (if any) is most plausibly the Chromium/Electron shell that hosts the iframe, which is a separate binary/JS bundle outside the one specified for this audit. Treat this as an open question, not a "yes."
| 6 | MCP Apps / resource-based UI extension | **CONFIRMED absent**: `ui://`, `mcp-ui`, `mcpApps`, `outputTemplate` all return 0 matches. **CONFIRMED**: the only generative-UI path found anywhere is the local-file `<agent-embed src="file://...">` mechanism from `generative_ui/SKILL.md` — there is no MCP-server-hosted (`ui://` resource) UI-template mechanism.

---

## 1. MCP protocol revision

### Evidence

```
grep -n "2024-11-05" ls_strings.txt
grep -n "2025-03-26" ls_strings.txt
grep -n "2025-06-18" ls_strings.txt
grep -n "2025-11-25" ls_strings.txt
```
(`ls_strings.txt` = `strings -a /Applications/Antigravity.app/Contents/Resources/bin/language_server`)

All four hits land on the same physical line, because `strings` merges runs
of printable bytes with no intervening NUL, and Go pads short literal
constants back-to-back in `.rodata`. The literal quoted verbatim (line
53200 of the dump) is:

```
```tool_callsTargetFile- Filenamefile:\.%s$hook_%s_%sstep count2026-07-282025-11-252025-06-182025-03-262024-11-05roots/listtools/listtools/call{"uri":%q}session_idsending %q...
```

Reading off the five consecutive 10-character date tokens in order:
`2026-07-28`, `2025-11-25`, `2025-06-18`, `2025-03-26`, `2024-11-05`,
**immediately** followed by `roots/list`, `tools/list`, `tools/call`. This
ordering (newest→oldest, directly abutting MCP method-name constants with no
unrelated tokens between the last date and the first method name) is the
signature of a Go slice literal such as
`[]string{"2026-07-28","2025-11-25","2025-06-18","2025-03-26","2024-11-05"}`
compiled adjacent to the method-dispatch constants of the same file — i.e.
almost certainly the client's `supportedProtocolVersions` list.

**CONFIRMED (presence)**: all five date strings exist together in MCP
context. **Not directly observable**: which version(s) go into the
`initialize` request's `protocolVersion` field or how version negotiation
falls back — that requires either disassembly or live capture, neither of
which was in scope.

Independent corroboration of a `2025-06-18`-or-later floor: two features
that were *introduced* in the `2025-06-18` spec revision are implemented:

- Elicitation (`elicitation/create`, see §2/§3) did not exist before
  `2025-06-18`.
- `resource_link` (a tool-result content-block type added in `2025-06-18`)
  is present as a literal (line 53287, in a blob containing
  `call_mcp_toolhintomitemptyresource_linkLast-Event-ID` — `hint` and
  `omitempty` are JSON-tag fragments and `resource_link` sits among them
  the way a content-block `type` enum value would).

Also worth flagging: **`2026-07-28` is not one of the four dates the task
listed as candidates.** The binary file itself is dated 2026-08-26 (`ls -la`
mtime), so this reads as a newer/draft protocol revision that has been
added to the vendored go-sdk copy since the four candidate dates were
catalogued. I did not find a string identifying it as "draft" vs. "final" —
noted as INFERRED, not CONFIRMED, that it is a newer draft rather than,
say, an internal build tag that happens to look like a date.

One more piece of direct evidence for per-feature version gating (not just
a flat supported-versions list): line 53969, in the same elicitation-error
region as §3, contains the literal `%q is only supported in protocol
version >= %s` — i.e. the codebase gates at least one feature by minimum
negotiated protocol version at runtime, which is consistent with (though
doesn't by itself prove) the theory that the four-or-five dates form an
ordered, negotiable version list rather than a single hardcoded constant.

---

## 2. MCP client methods and notifications

### Evidence (windowed grep — see §8 for the `wingrep.py` helper)

```
python3 wingrep.py ls_strings.txt "sampling/createMessage" "resources/read" "resource_link" \
  "prompts/list" "prompts/get" "tools/call" "roots/list" "resources/list" \
  "resources/subscribe" "logging/setLevel" "completion/complete"
```

Quoted hits (each is a distinct concatenated-strings blob; method names are
bold for scanability):

- Line 53200: `...step count2026-07-28...2024-11-05` **`roots/list``tools/list``tools/call`**`{"uri":%q}session_id...`
- Line 53233: `...target_file`**`prompts/get`**`nil contentbad session...`
- Line 53253: `...gen_metadata`**`prompts/list`**`%q before %qinvalid JSON...`
- Line 53287: `...call_mcp_toolhintomitempty`**`resource_link`**`Last-Event-ID...`
- Line 53312: `...arguments_jsonsed edit on %swal checkpoint...`**`resources/list``resources/read`**`nil connection...Mcp-Session-Id...`
- Line 53377: `...delete_knowledgeset user_versionload parent refs`**`logging/setLevel`**`subscriber_count...`
- Line 53487: `...invalidparams`**`completion/complete``resources/subscribe`**`noprotocolerrorbody...`
- Line 53571: `...load battle mode infos`**`sampling/createMessage`**`notifications/progress`Subscribe: missing URI...`
- Line 53791: `...tool call denied with reason: %s...`**`notifications/tools/list_changed``notifications/roots/list_changed`**`unsupported protocol version: %q...`**`unsupported elicitation mode: %q`**`AddTool %q: missing input schema...`
- Line 53828: `...unmarshal trajectory metadata blob`**`notifications/prompts/list_changed``notifications/elicitation/complete`**`io.modelcontextprotocol/clientInfo``io.modelcontextprotocol/serverInfo`...`
- Line 53855: `...PRAGMA journal_size_limit = 67108864`**`notifications/resources/list_changed`**`%w: malformed line in SSE stream: %q...`
- Line 53904: `...`**`notifications/subscriptions/acknowledged`**`URL must not be set for form elicitation`
- Line 53447: `elicitation/create` present as its own literal (`...delete old records`**`elicitation/create`**`nil Implementation...`)

### Verdicts

| Method / notification | Status |
|---|---|
| `tools/list` | CONFIRMED |
| `tools/call` | CONFIRMED |
| `notifications/tools/list_changed` | CONFIRMED |
| `elicitation/create` | CONFIRMED |
| `sampling/createMessage` | CONFIRMED (string + go-sdk `CreateMessageParams`/`CreateMessageResult`/`SamplingMessage`/`SamplingMessageV2` types, §3) |
| `resources/read` | CONFIRMED |
| `resource_link` | CONFIRMED |
| `roots/list` | CONFIRMED |
| `prompts/list`, `prompts/get` | CONFIRMED |
| `resources/list`, `resources/subscribe` | CONFIRMED (bonus, not asked but load-bearing context) |
| `completion/complete`, `logging/setLevel` | CONFIRMED (bonus) |
| `notifications/resources\|prompts\|roots/list_changed`, `notifications/progress` | CONFIRMED (bonus) |
| `notifications/elicitation/complete`, `notifications/subscriptions/acknowledged` | Present, but **not** part of the public MCP spec as of any of the candidate revisions — these look like Google-internal extensions layered on top of the go-sdk (or on a newer draft revision I don't have the spec text for). Flagged as CONFIRMED-present / INFERRED-custom. |

Further corroboration from Go symbol-table strings (fully-qualified generic
instantiations of the go-sdk's client dispatch table), which independently
confirm the SDK is the real
`github.com/modelcontextprotocol/go-sdk`, vendored at
`google3/third_party/golang/github_com/modelcontextprotocol/go_sdk/v/v0/mcp`,
and that it implements client-side handlers for (method names inferred from
Params-type names, which is the go-sdk's own naming convention):
`InitializeParams`, `PingParams`, `ListToolsParams`, `CallToolParamsRaw`,
`ListPromptsParams`, `GetPromptParams`, `ListResourcesParams`,
`ReadResourceParams`, `ListResourceTemplatesParams`, `SubscribeParams`,
`UnsubscribeParams`, `CompleteParams`, `SetLoggingLevelParams`,
`RootsListChangedParams`, `ProgressNotificationParams`,
`ResourceUpdatedNotificationParams`, `CancelledParams`, `InitializedParams`,
`ElicitParams`, `CreateMessageParams`, plus a non-spec `DiscoverParams` and
`SubscriptionsListenParams` (go-sdk internals or Google extensions — not
investigated further).

```
grep -n "modelcontextprotocol\|mark3labs\|mcp-go" ls_strings.txt   # confirms vendored SDK identity
```

---

## 3. Elicitation shape

### Request/response shape — CONFIRMED

From the go-sdk's compiled reflect metadata (line 285214 area of the dump),
the exact Go struct definition of `ElicitParams`:

```
struct {
  mcp.Meta            `json:"_meta,omitempty"`
  Mode          string `json:"mode"`
  Message       string `json:"message"`
  RequestedSchema interface{} `json:"requestedSchema,omitempty"`
  URL           string `json:"url,omitempty"`
  ElicitationID string `json:"elicitationId,omitempty"`
}
```

```
python3 wingrep.py ls_strings.txt "ElicitParams" "RequestedSchema" "CreateMessageParams" "CreateMessageResult" "SamplingMessage"
```

### Mode: `"form"` vs `"url"` — CONFIRMED, capability-negotiated separately

Error strings (line 53841, 53924, 53936, 53904, 54021 — quoted from the
concatenated blobs):

- `client does not support elicitation` (generic — no elicitation support at all)
- `client does not support "form" elicitation`
- `client does not support "url" elicitation`
- `unsupported elicitation mode: %q`
- `URL must be set for URL elicitation`
- `URL must not be set for form elicitation`
- `Schema must not be set for URL elicitation`
- `elicit schema must be of type 'object', got %q`
- `elicitation result content does not match requested schema: %v`
- `failed to apply schema defaults to elicitation result: %v`

This proves: (a) `"url"`-mode elicitation exists as a first-class,
separately-capability-gated mode alongside `"form"` — i.e. the "URL
elicitation" mechanism the task calls `elicit_url` **is present**; (b) the
client can advertise support for form-only, url-only, both, or neither, and
the server-side code checks per-mode before sending; (c) `RequestedSchema`
is required to be a JSON object schema for form mode and *forbidden* for URL
mode; (d) result content is schema-validated against `requestedSchema`
after the client responds.

### Schema type support (string/number/boolean/enum)

Direct evidence only covers **enum**: the validator enforces the
"enum-with-titles" idiom (each enum entry is an object with `const` and
`title`):

```
const is required for titled enum entries
title is required for titled enum entries
const cannot be empty for titled enum entries
const must be a string for titled enum entries
```
(lines 53924, 53962, 53969)

I did **not** find elicitation-specific strings naming `string`/`number`/
`boolean` support directly. What I *did* find is that the schema
validation for `requestedSchema` reuses a generic JSON-Schema
implementation (strings `jsonschema`, `applicator`, `validation`, `contains`
, `multipleOf`, `metaschemas/draft/2020-12/schema` all appear near the
elicitation error strings in the same region of the binary, line ~53200+).
Since that's a general-purpose validator rather than an elicitation-only
hand-rolled one, string/number/boolean support for elicitation schemas is
**INFERRED** (highly likely, given the generic engine underneath), not
directly CONFIRMED by a type-specific quote.

### Rendering — no evidence

No HTML/CSS/UI strings were found tied to elicitation forms. This binary is
the language server, not the UI shell; how the form is actually drawn is
outside what this artifact can show. **Not investigated further** (out of
scope per the task's evidence source).

A related, Google-internal struct exists purely for the UI side:
`exa.cortex_pb.ElicitationInteractionSpec` with a getter
`GetRequestedSchemaJson` (line 232772) — i.e. Antigravity's own IPC layer
carries the raw requested-schema JSON string to whatever renders the dialog,
but the renderer itself isn't in this binary.

---

## 4. MCP server config schema

Two genuinely different schemas exist. The task named the marketplace-plugin
one; the actually-more-relevant one for a hand-written `mcp_config.json`
turned out to be a separate, richer proto package. Both are documented
below with full field lists reconstructed directly from the binary's
embedded `FileDescriptorProto` bytes (which `strings` renders as a run of
field-name / JSON-name string pairs in file order — see §8 for how to
re-walk this yourself).

```
grep -n "CascadePluginLocalConfig\|CascadePluginRemoteConfig" ls_strings.txt
awk 'NR>=69020 && NR<=69100' ls_strings.txt     # cascade_plugins_pb descriptor dump
awk 'NR>=166710 && NR<=166996' ls_strings.txt   # cortex_pb McpServerSpec/McpOAuthConfig descriptor dump
```

### 4a. `exa.cascade_plugins_pb` — plugin *marketplace/template* config

This is the schema for `CascadePluginTemplate` objects served by
`GetAvailableCascadePlugins` / installed via `InstallCascadePlugin` — i.e.
the plugin **gallery**, with install-time variable substitution. Full
descriptor (line 69020–69097), field-for-field:

```
CascadePluginTemplate
  title, link, description
  commands: map<string, CascadePluginCommand>
  configuration (oneof):
    local:  CascadePluginLocalConfig
    remote: CascadePluginRemoteConfig
  installation_count, trust_level, readme

CascadePluginLocalConfig
  commands: map<string, CascadePluginCommand>

CascadePluginCommand
  template:  CascadePluginCommandTemplate
  variables: []CascadePluginCommandVariable

CascadePluginCommandTemplate
  command, args, env: map<string,string>

CascadePluginCommandVariable
  name, title, description, link

CascadePluginRemoteConfig
  template: CascadePluginRemoteConfigTemplate

CascadePluginRemoteConfigTemplate
  server_url, headers: map<string,string>, auth_provider_type
```

**auth_provider_type appears only on `CascadePluginRemoteConfigTemplate`**,
never on `CascadePluginLocalConfig` (there is no `auth_provider_type` field
anywhere in the local-config message). No `client_id`, `client_secret`,
`authorization_url`, `token_url`, `redirect_uri`, or `scopes` field exists on
either message — CONFIRMED absent from this schema.

### 4b. `exa.cortex_pb` — the actual runtime server config

This is a different, larger message (`McpServerSpec`) discovered while
tracing `auth_provider_type`'s enum type
(`exa.cortex_pb.McpAuthProviderType`) back to its message — it is **not**
`CascadePluginRemoteConfigTemplate`, it's a sibling message in a different
proto package that backs the live, per-conversation/per-agent MCP server
list (i.e. closer to what `mcp_config.json` actually becomes once loaded).
Full descriptor (line 166715–166995):

```
McpServerSpec
  server_name
  command, args, env: map<string,string>      # stdio transport
  server_url                                   # remote transport
  disabled, disabled_tools, enabled_tools
  headers: map<string,string>
  server_index
  skip_tool_name_prefix, skip_tool_description_prefix
  tool_config: map<string, McpServerToolConfig>
  oauth: McpOAuthConfig
  auth_provider_type: McpAuthProviderType
  plugin_name
  timeout_seconds
  strict_argument_validation
  omit_from_system_prompt
  force_all_tools_eager
  disable_standalone_sse

McpOAuthConfig
  client_id
  client_secret

McpServerToolConfig
  background: McpToolBackgroundMode
  eager
  task_options: McpTaskOptions { suppress_completion_notification, display_name, description }

McpServerState   (runtime status, not config)
  spec: McpServerSpec
  status: McpServerStatus
  error
  tools, tool_errors
  server_info: McpServerInfo { name, version }
  instructions
  auth_url          # computed, not user-supplied
  has_auth_token
```

Enum values, confirmed at line 168288–168305:

```
McpAuthProviderType:
  MCP_AUTH_PROVIDER_TYPE_UNSPECIFIED
  MCP_AUTH_PROVIDER_TYPE_GOOGLE_CREDENTIALS

McpServerStatus:
  MCP_SERVER_STATUS_UNSPECIFIED
  MCP_SERVER_STATUS_PENDING
  MCP_SERVER_STATUS_READY
  MCP_SERVER_STATUS_ERROR
  MCP_SERVER_STATUS_DISABLED_BY_ADMIN
```

```
grep -n "MCP_AUTH_PROVIDER_TYPE\|McpServerStatus\b" ls_strings.txt
```

### On the task's specific auth-field question

**CONFIRMED ABSENT from the complete field lists**: `McpOAuthConfig` (lines
166787–166791) has exactly two fields, `client_id` and `client_secret`, and
nothing else — no `authorization_url`, `token_url`, `redirect_uri`, or
`scopes`. `McpServerSpec` (lines 166715–166760) — the message that embeds
`oauth: McpOAuthConfig` and `auth_provider_type` — has none of those four
fields either. `CascadePluginRemoteConfigTemplate` (lines 69087–69094) also
has none of them. These three descriptor dumps are complete, contiguous
field lists (every field of each message, in declaration order), so the
absence is a direct reading of the schema, not an inference from a keyword
search.

Separately, I did a keyword sweep for `client_id`, `client_secret`,
`authorization_url`, `token_url`, `redirect_uri` across the whole binary
(831 combined hits: `client_id`/`client_secret` account for most of it;
`authorization_url` and `redirect_uri` each had a handful) and spot-checked
representative clusters. Every cluster I inspected belongs to an unrelated
proto message: generic `google.api.AuthProvider` (API Gateway/ESP config),
Vertex AI `ApiAuth.ApiKeyConfig`, Slack/GitHub/Google-Drive "connector"
configs for an internal knowledge-base indexing feature
(`exa.opensearch_clients_pb`), and `RewriteUriResponse.redirect_uri` (an
HTTP proxy helper). None of the clusters I looked at attach to
`McpServerSpec`, `McpOAuthConfig`, `CascadePluginRemoteConfig`, or
`CascadePluginRemoteConfigTemplate` — but this sweep was a spot-check, not
an exhaustive review of all 831 hits, and I did not separately search for
`scopes` as a bare keyword (it's a common enough word that a keyword sweep
for it would be mostly noise; its absence from the three complete field
lists above is the load-bearing evidence for it too). Treat the descriptor
dumps as the CONFIRMED evidence and the keyword sweep as corroborating,
non-exhaustive support.

`MCP_AUTH_PROVIDER_TYPE_GOOGLE_CREDENTIALS` **is CONFIRMED to exist**
(line 168290) as the only non-default value of `McpAuthProviderType` — but
because there is no generic/custom OAuth provider enum value and no
authorization/token endpoint fields anywhere, the practical reading is:
Antigravity's *current* MCP OAuth support is narrower than a generic
"configure any OAuth provider" flow. It looks like exactly two paths exist:
(1) reuse the already-signed-in Google/Workspace identity
(`GOOGLE_CREDENTIALS`), or (2) supply a bare `client_id`/`client_secret`
pair (`McpOAuthConfig`) for a flow whose authorization/token endpoints are
presumably hard-coded elsewhere (not found as configurable strings). I did
not find evidence of a fully generic/BYO-OAuth-provider mode.

One extra, unrequested nuance worth recording: `mcp_cwd_workspace_relative_path`
exists (line 162789/164000) but as a field of `CustomAgentConfig`
(agent-level), not of `McpServerSpec` (per-server) — i.e. a working
directory override for launched MCP servers is set once per custom agent,
not per server entry, in this build. This is relevant if you were expecting
a per-server `cwd` field the way the task's premise implied.

### Cross-check against the bundled user-facing doc

`~/.gemini/antigravity/builtin/skills/agy-customizations/docs/mcp_servers.md`
(read in full) documents only the simple, user-authored JSON shape:

```json
{
  "mcpServers": {
    "sqlite-helper": { "command": "...", "args": [...], "env": {...} },
    "remote-service": { "serverUrl": "https://..." }
  }
}
```

No `oauth`, `client_id`/`client_secret`, or `authProviderType` field is
mentioned in this local doc at all — consistent with the binary evidence
that OAuth config is a narrow, recently-added, and seemingly
under-documented corner of the schema (the existing project doc
`docs/research/antigravity-official-docs.md` separately notes the *live*
antigravity.google/docs/mcp page mentions `authProviderType` even though the
bundled skill doesn't — I did not re-fetch that live page for this audit,
per the task's read-only/local scope).

---

## 5. `<agent-embed>` in-chat HTML rendering

### Full source — `~/.gemini/antigravity/builtin/skills/generative_ui/SKILL.md`

Read in full (122 lines); relevant points quoted directly:

- **Mechanism**: write a self-contained `.html` file via `write_to_file`
  with `ArtifactMetadata.UserFacing: true`, then optionally reference it
  inline with `<agent-embed src="file:///<artifact_path>/widget.html"></agent-embed>`.
- **CSP**: *"All external CDNs are blocked by CSP, except for one
  allowlisted gstatic Tailwind dependency that you **CAN** and **SHOULD**
  use"* — `https://www.gstatic.com/antigravity/web/dev/tailwindcss.min.js`.
  This is the **only** externally-reachable URL the doc names as permitted.
- **Theme variables injected into the iframe**: `--background`, `--content`,
  `--card`, `--sidebar`, `--border`, `--foreground`, `--muted-foreground`,
  `--placeholder`, `--primary`/`--primary-foreground`,
  `--secondary`/`--secondary-foreground`, `--accent`. Typography is applied
  to `body` automatically. Explicitly told not to declare local `:root`
  color fallbacks.
- **Size limit**: *"Inline embeds only have a **500px** height viewport.
  Past that the widget scrolls inside a small box."* The `height` attribute
  on `<agent-embed>` is explicitly documented as ignored. No `width`/byte
  size limit is mentioned anywhere in the doc.
- **No `h-screen`/`min-h-screen`/`100vh`/`height:100%`** on top-level
  containers — the frame's viewport is derived from content size, so
  viewport-relative units feed back on themselves.

### Binary occurrences of `agent-embed`

```
grep -c "agent-embed" ls_strings.txt   # => 4
grep -n "agent-embed" ls_strings.txt
```
All 4 hits (lines 78641, 78645, 78699, 78713) are inside this exact
`SKILL.md` text, which is baked into the binary verbatim (presumably as a
built-in prompt/skill resource). **CONFIRMED: there is no second,
undocumented `<agent-embed>` implementation detail anywhere else in the
binary** — the skill doc is the complete spec as far as this binary is
concerned.

### CSP/sandbox mechanics beyond the skill doc — NOT FOUND

```
grep -c "Content-Security-Policy" ls_strings.txt   # => 1
grep -c "connect-src" ls_strings.txt                # => 0
grep -c "script-src" ls_strings.txt                 # => 0
grep -c "default-src" ls_strings.txt                # => 0
grep -c "frame-src" ls_strings.txt                  # => 0
grep -c "allow-scripts" ls_strings.txt              # => 0
grep -c "allow-same-origin" ls_strings.txt          # => 0
```

The single `Content-Security-Policy` hit (line 53578) sits in an unrelated
blob (`...codeium-language-serverset up trajectory saver...`) with no
MCP/embed context around it — it reads like a generic HTTP-header-name
constant used somewhere else in the codebase (possibly the bundled
Playwright/CDP browser-automation library also present in this binary —
strings like `playwright`, `newContext`, `DOM.enable`, `Page.close` appear
nearby in the same region), not a CSP policy string specific to the chat
iframe.

**Conclusion on CSP**: this Go binary is the language server / backend; it
almost certainly does not itself set the CSP header or iframe `sandbox`
attribute for the chat webview — that is the job of the Electron/Chromium
UI shell, which is a separate binary/JS bundle not included in the scope of
this audit (`Contents/Resources/bin/language_server` only). I have **no
evidence either way** from this binary about `connect-src` rules or
`sandbox="allow-scripts ..."` flags on the embed iframe.

### The critical question: can `fetch()` inside a widget reach `http://127.0.0.1:PORT`?

**Not confirmed. Not refuted. No direct evidence found in this binary.**

What I found that's *adjacent* but does not answer the question:

- 13 occurrences of `127.0.0.1` in the binary, all belonging to unrelated
  subsystems: a debug pprof/profiler bind (`127.0.0.1:0`), a Chrome
  DevTools MCP debug server (`Chrome DevTools MCP debug server listening at
  http://127.0.0.1:%d`), a CDP websocket for the browser-automation tool
  (`ws://127.0.0.1:%s%s`), and one embedded Node.js source file (see next
  point). None of these are the chat/artifact iframe.
- An embedded Node.js script (line ~477645 onward) headed *"Node.js backend
  for Antigravity sidecars... Hosts a local HTTP server for the sidecar's
  Web UI"* explicitly binds `127.0.0.1` only, with a comment: *"Sidecars
  serve on loopback only. Remote access ... is provided by the platform's
  per-sidecar gateway, which authenticates each request and forwards it
  here."* It requires `ANTIGRAVITY_LS_ADDRESS`, `ANTIGRAVITY_CSRF_TOKEN`,
  and `ANTIGRAVITY_SIDECAR_WEB_PORT` env vars, and a per-request
  `ANTIGRAVITY_SIDECAR_UI_TOKEN`. **This is a different, unrelated feature**
  (a remote/cloud "sidecar" agent web UI, not the in-chat `<agent-embed>`
  generative-UI widget) — I'm flagging it only because it shows the
  *general architectural pattern* elsewhere in the codebase is "loopback
  server gated by a CSRF/UI token," which — if the same pattern is reused
  for the chat iframe's host bridge — would suggest a same-origin,
  token-gated channel is more likely than an open CSP allowing arbitrary
  `fetch()` to any local port. But this is INFERENCE BY ANALOGY, not
  evidence about `<agent-embed>` specifically, and should not be treated as
  confirmation either way.
- `srcdoc` (2 hits) and `postMessage` (3 hits) exist in the binary but in
  too little context to attribute to the agent-embed iframe specifically
  rather than to the bundled browser-automation library.

**Recommendation given the architecture decision this is gating**: this
binary cannot settle the question. The two ways to actually resolve it are
(a) build a real widget artifact with a `fetch('http://127.0.0.1:<port>')`
call, embed it with `<agent-embed>`, and observe in a real Antigravity
session whether the request succeeds or is blocked by CSP/CORS, or (b)
inspect the Electron/Chromium application bundle (outside
`Contents/Resources/bin/language_server`) for its `webPreferences` /
`session.webRequest.onHeadersReceived` CSP-injection code and any iframe
`sandbox=` attribute. Neither was in scope for this pass.

---

## 6. MCP Apps extension / resource-based UI — confirmed absent

```
grep -c "ui://" ls_strings.txt          # => 0
grep -c "mcp-ui" ls_strings.txt         # => 0
grep -c "mcpApps" ls_strings.txt        # => 0
grep -c "outputTemplate" ls_strings.txt # => 0
```

All four return zero matches — **CONFIRMED absent**, matching the task's
premise exactly.

**Alternative mechanism**: the only generative/rich-UI path found anywhere
in this binary or the local skill/config files is the local-file
`<agent-embed src="file:///...">` scheme documented in §5 — a
client-authored HTML file written to a local artifact directory and
embedded by file path, not a server-declared `ui://` resource or an
`outputTemplate` attached to a tool's `_meta`. There is no evidence of any
mechanism by which an MCP *server* can ship its own UI resource/template
that Antigravity would render — every generative-UI code path I found
originates from the agent's own `write_to_file` + `<agent-embed>`, not from
tool-call metadata or declared resources.

---

## 7. Config files inspected (as specified in the task)

| Path | Result |
|---|---|
| `~/.gemini/settings.json` | Simple `mcpServers` map (`codebase-memory-mcp`, `clerk`), plus unrelated hook config. No OAuth/auth fields present in this instance's config (doesn't mean the schema doesn't support them — this file simply doesn't use them). |
| `~/.gemini/config/plugins/` | Contains `adk-harness` and `google-antigravity-sdk` plugin dirs. Both `plugin.json` files read in full: `adk-harness` (v0.1.0) — `"Govern Google Workspace from inside Antigravity. Named reads flow; writes are held for trusted host approval. Sending mail and changing sharing are refused. The model cannot authorize its own actions."`; `google-antigravity-sdk` (v0.0.7, author Google, Apache-2.0) — `"Using the Google Antigravity Python SDK to build AI agents"`. Neither `plugin.json` declares any MCP-server or auth-related fields itself (both are just name/version/description/metadata). No `mcp_config.json` file was present in either plugin directory at the time of this audit (the doc `agy-customizations/docs/mcp_servers.md` says plugin-scoped MCP config would live at `plugins/<name>/mcp_config.json`, but neither installed plugin currently ships one). |
| `~/.gemini/extensions/` | One extension installed (`caveman`), a large third-party toolkit unrelated to this audit's questions — not analyzed further as it's out of scope (not an Antigravity-authored MCP/UI mechanism). |
| `~/.gemini/antigravity/builtin/skills/generative_ui/SKILL.md` | Read in full — see §5. |
| `~/.gemini/antigravity/builtin/skills/agy-customizations/SKILL.md` + `docs/*.md` | `docs/mcp_servers.md` read in full — see §4 cross-check. `docs/json_configs.md`, `docs/skills.md`, `docs/plugins.md`, `docs/hooks.md`, `docs/rules.md` exist but were not needed to answer the six questions and were not read in full for this pass. |
| `~/.gemini/antigravity/builtin/skills/antigravity_guide/` | `SKILL.md` + `references/{app,cli,ide,sdk}.md` exist; not read for this pass (not required by the six questions; general product-usage guide, not MCP/UI internals). |

---

## 8. Reproducibility — exact commands

```bash
# 1. Dump every printable string in the binary (fast: <1s for 146MB, ~636k lines / 35MB text)
BIN=/Applications/Antigravity.app/Contents/Resources/bin/language_server
strings -a "$BIN" > ls_strings.txt

# 2. Simple presence/count checks
grep -c "agent-embed" ls_strings.txt
grep -c "ui://" ls_strings.txt
grep -c "mcp-ui" ls_strings.txt
grep -c "mcpApps" ls_strings.txt
grep -c "outputTemplate" ls_strings.txt
grep -c "Content-Security-Policy" ls_strings.txt
grep -c "connect-src" ls_strings.txt   # and script-src / default-src / frame-src / allow-scripts / allow-same-origin

# 3. Windowed search — IMPORTANT: because Go packs adjacent short string
#    constants with no separators, `strings` frequently merges dozens of
#    unrelated literals onto one "line". A plain `grep -n` on a hit line can
#    dump 50-100KB of unrelated text. Use a windowed extractor instead:

cat > wingrep.py <<'PYEOF'
import sys, re
path = sys.argv[1]
terms = sys.argv[2:]
before, after = 150, 150
with open(path, 'r', errors='replace') as f:
    for i, line in enumerate(f, 1):
        for t in terms:
            for m in re.finditer(re.escape(t), line):
                idx = m.start()
                start = max(0, idx-before)
                end = min(len(line), idx+len(t)+after)
                print(f"--- line {i} :: term={t!r} ---")
                print(line[start:end])
PYEOF

python3 wingrep.py ls_strings.txt "elicitation" "CascadePluginLocalConfig" \
  "CascadePluginRemoteConfig" "McpAuthProviderType" "client_id" "client_secret" \
  "authorization_url" "token_url" "redirect_uri" "127.0.0.1"

# 4. For full protobuf descriptor field lists (as used to reconstruct the
#    McpServerSpec / CascadePlugin* schemas in §4), the descriptor bytes are
#    laid out as one field-name/json-name pair per source line, in file
#    declaration order — dump a raw line range once you've located the
#    message name with grep -n, e.g.:
grep -n "McpServerSpec$" ls_strings.txt          # find the line number
awk 'NR>=166710 && NR<=166996' ls_strings.txt    # then read the surrounding raw range
```

---

## Appendix: things this audit could NOT determine from this binary alone

- Which single protocol version Antigravity actually sends in `initialize`
  (vs. merely supporting several) — needs a live MCP capture (e.g. point a
  logging stdio MCP server at it and read the `initialize` request body).
- Whether the `<agent-embed>` iframe's CSP permits `fetch()` to
  `127.0.0.1:<port>` — needs either a live test with a real widget, or
  inspection of the Electron/Chromium shell (a different binary/bundle than
  the one specified for this audit).
- How the elicitation form is actually rendered (widget/theme/interaction) —
  the rendering code is UI-shell-side, not in this Go binary.
- Whether `McpOAuthConfig{client_id, client_secret}` is wired to a
  hard-coded Google OAuth endpoint, a per-request dynamic discovery, or
  something else — no authorization/token endpoint strings were found
  anywhere in the binary tied to MCP, so the mechanism (if any) must be
  either hard-coded elsewhere in a way `strings` can't reveal (e.g. inside a
  compiled URL constant that happens to already be a plain
  `https://accounts.google.com/...` string indistinguishable from unrelated
  Google-auth strings elsewhere in this very large binary), or resolved by
  a separate service Antigravity talks to.
