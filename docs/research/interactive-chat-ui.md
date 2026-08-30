# Interactive HTML UI in AI agent chat clients — landscape research

Research date: 2026-08-29. Purpose: before improving our human-approval card
(rendered via Antigravity's `<agent-embed src="file:///...">`, served by
`src/adk_harness/workspace/approval_page.py`), survey what already exists so
we adopt conventions instead of reinventing them.

**Bottom line up front:**

- The industry has converged on one open standard for this exact problem:
  **MCP Apps (SEP-1865)**, built on the **mcp-ui** project. It is now
  implemented by Claude, ChatGPT, VS Code Copilot, Goose, Postman, Cursor,
  Microsoft 365 Copilot, and others.
- **Antigravity 2.11.0 does not implement it.** Confirmed by our own prior
  binary audit (`docs/research/antigravity-capabilities.md`, §6): zero
  occurrences of `ui://`, `mcp-ui`, `mcpApps`, `outputTemplate` anywhere in
  the language-server binary. The only generative-UI path Antigravity has is
  the agent-authored `<agent-embed src="file:///...">` local-file mechanism.
- We cannot adopt MCP Apps' transport today, but we **can and should adopt
  its visual/interaction conventions** (card sizing, action limits, payload
  display rules, CSS-variable theming) so a future port — either to
  Antigravity if it ever adds `ui://` support, or to Claude/ChatGPT/Goose
  directly — is nearly free. Our card already does some of this (Tailwind +
  host theme vars); it can do more.
- For the concrete "make it look better" ask: **Claude's official MCP Apps
  design guidelines** (item 4 below) give exact pixel/token values that map
  directly onto Tailwind classes and are usable in our card verbatim today,
  with no protocol changes.

---

## 0. What we currently have

`/Users/datta/Documents/Projects/adk-harness/src/adk_harness/workspace/approval_page.py`
(272 lines). `ApprovalServer` runs a loopback-only `ThreadingHTTPServer` on
`127.0.0.1:0`; `widget()` renders an HTML template to a temp file and returns
that path for `<agent-embed src="file://...">`. The embedded page's own JS
does `fetch('http://127.0.0.1:{port}/approve/{token}/{yes|no}', {method:
'POST'})`. This is the mechanism the task description refers to as "just
proved."

The card itself (the `_WIDGET` template) already follows several of
Antigravity's own `generative_ui` skill conventions: Tailwind via the
allowlisted `gstatic.com/antigravity` CDN script, `bg-transparent` root,
host theme CSS variables (`--card`, `--border`, `--foreground`, `--primary`,
`--secondary`, `--muted-foreground`), a card wrapper, two buttons
(Approve/Decline), a `<pre>` block for the JSON arguments, and a short hash
badge. It is ~54 lines of HTML/JS. There's a separate plain
`do_GET`/form-based fallback page for non-embedded (real browser) use.

This means the redesign work is about applying tighter visual-hierarchy and
payload-display rules to an already-sound foundation, not a rewrite.
(A separate, much larger and unrelated system, `ui/approval/` — a Firebase/
Google-Workspace-OAuth consent flow — also exists in this repo; it is not
the card in question.)

---

## 1. MCP Apps extension / SEP-1865 / mcp-ui

**Status:** Final / stable as of 2026-01-26. Extension identifier:
`io.modelcontextprotocol/ui`.

- SEP text (historical record of the accepted design):
  https://modelcontextprotocol.io/seps/1865-mcp-apps-interactive-user-interfaces-for-mcp
- Live/current spec: https://github.com/modelcontextprotocol/ext-apps/blob/main/specification/2026-01-26/apps.mdx
- Announcement blog post: https://blog.modelcontextprotocol.io/posts/2026-01-26-mcp-apps/
  (an earlier proposal post from 2025-11-21 also exists at a similarly-named URL)
- PR discussion: https://github.com/modelcontextprotocol/modelcontextprotocol/pull/1865
- Reference implementation: https://github.com/MCP-UI-Org/mcp-ui (formerly
  `idosal/mcp-ui`; GitHub redirects the old path) and a prototype in
  https://github.com/modelcontextprotocol/ext-apps

### What a `ui://` resource looks like

Resources are **predeclared**, not embedded in tool results — the host
fetches and reviews them at connection time, before any tool runs:

```ts
interface UIResource {
  uri: string;           // must use the "ui://" scheme
  name: string;
  description?: string;
  mimeType: string;      // MUST be "text/html;profile=mcp-app" (HTML-only MVP)
  _meta?: { ui?: UIResourceMeta };  // CSP + rendering config, see below
}
```

A tool links to its UI via `_meta.ui` on the **tool** definition, not the
resource:

```ts
interface McpUiToolMeta {
  resourceUri?: string;                 // which ui:// resource renders this tool's result
  visibility?: Array<"model" | "app">;  // ["app"] = UI-only tool, hidden from the model
}
```

CSP is declared per-resource and the host is required to enforce it
(default is `default-src 'none'`, i.e. nothing external loads unless you ask):

```json
{
  "_meta": {
    "ui": {
      "csp": {
        "connectDomains": ["https://api.example.com"],
        "resourceDomains": ["https://cdn.example.com"],
        "frameDomains": [],
        "baseUriDomains": []
      }
    }
  }
}
```

### The postMessage / JSON-RPC handshake

The iframe acts as its own MCP **client**, talking to the host over a
`postMessage` transport, using ordinary MCP JSON-RPC message shapes (not a
bespoke event protocol):

1. `View → Host`: `ui/initialize` — declares `appCapabilities` (e.g. which
   display modes it supports).
2. `Host → View`: initialize result — `hostCapabilities`, `hostInfo`,
   `hostContext` (safe-area insets, theme, etc.).
3. `View → Host`: `ui/notifications/initialized`.
4. `Host → View`: `ui/notifications/tool-input` — the arguments the model
   is about to call the tool with (sent *before* the result, useful for
   showing a "pending" state — this is how ChatGPT delivers
   approval-gated arguments once a user has already approved the call).
5. `Host → View`: `ui/notifications/tool-result` — `content`,
   `structuredContent`, `_meta`.
6. Interactively, the view can then issue its own `tools/call` back through
   the host, which proxies it to the real MCP server and returns a normal
   `tools/call` response.

All communication is auditable JSON-RPC — the design rationale explicitly
rejected a "global API object" precisely because it isn't loggable/portable
across hosts.

### Security model

- **Mandatory iframe sandboxing** or restricted permissions.
- **Predeclared templates** so the host can review the HTML for malicious
  content before ever rendering it (this is *the* stated reason resources
  are predeclared rather than returned inline in tool results, which is
  what mcp-ui's older/legacy approach did).
- **CSP built from resource metadata**: `connectDomains` → `connect-src`,
  `resourceDomains` → `script-src`/`style-src`/`img-src`,
  `frameDomains` → `frame-src`, `baseUriDomains` → `base-uri`. Hosts MUST
  block undeclared domains and SHOULD warn on external-domain access.
- **User consent for UI-initiated tool calls** is explicitly a host-level
  requirement, not left to server discretion — directly relevant to our
  approval-card use case, since the spec assumes hosts will gate
  write-triggering tool calls originating from inside a UI resource.

### Who implements it today

Authoritative source — the protocol's own community-maintained matrix:
https://modelcontextprotocol.io/extensions/client-matrix

As of this research, clients marked as supporting `io.modelcontextprotocol/ui`:
**Claude (web)**, **Claude Desktop**, **VS Code GitHub Copilot**,
**Microsoft 365 Copilot**, **Goose**, **Postman**, **MCPJam**, **ChatGPT**,
**Cursor**, **Archestra.AI**, **PostHog Code**.

Not on that list (i.e. not verified as supporting it): **LibreChat** — an
open feature request exists
(https://github.com/danny-avila/LibreChat/issues/10641) but as of this
research it is unimplemented, so treat "LibreChat supports mcp-ui" as false
until that issue closes. I could not verify Antigravity being on any
roadmap for this at all — our own binary audit found zero traces of it.

### Is this usable from our Python MCP server today?

**No, not for Antigravity.** Antigravity doesn't speak the `ui://`/
`ui/initialize` protocol at all, so declaring `_meta.ui` on our tools or
shipping `ui://` resources would simply be ignored. The extension is
negotiated (`extensions` capability field); a client that never asks for it
never gets it.

**Cost to adopt (for a future non-Antigravity host, or if Antigravity ever
adds support):** Low-to-medium if we're already using the `mcp-ui` Python
SDK (see §2) to build the HTML — the main new work is capability
negotiation and wiring `ui/notifications/tool-input` /
`ui/notifications/tool-result` instead of our own bespoke
loopback-HTTP-POST bridge. Our approval semantics (token, change hash,
approve/decline) port over almost unchanged; only the transport envelope
changes.

**What's worth copying now, for cheapness later:** name our resource/tool
metadata fields the same way MCP Apps does (`resourceUri`, `visibility`),
keep the HTML self-contained and CSP-narrow (no external calls except our
own loopback server, which maps cleanly onto a future `connectDomains`
declaration), and keep the interaction surface to "show data + at most two
buttons" so it fits either model without a redesign.

---

## 2. The `mcp-ui` open source project

- Repo: https://github.com/MCP-UI-Org/mcp-ui (moved from `idosal/mcp-ui`;
  the old URL 301-redirects here — same maintainer, `idosal` = Ido Salomon,
  the SEP-1865 author). Apache License 2.0 (confirmed via GitHub API
  `license.spdx_id: "Apache-2.0"`).
- Docs/homepage: https://mcpui.dev

### Packages

| Language | Package | Purpose |
|---|---|---|
| TypeScript | `@mcp-ui/server` | build `UIResource` objects server-side |
| TypeScript | `@mcp-ui/client` | `<UIResourceRenderer>` / `<AppRenderer>` React components, `onUIAction` handling |
| **Python** | **`mcp-ui-server`** (PyPI, `pip install mcp-ui-server`, latest **1.0.0**) | server-side resource creation — no Python client/renderer package exists; rendering is a host/frontend concern |
| Ruby | `mcp_ui_server` | same server-side role, Ruby |

Repo layout confirms this: `sdks/{python,ruby,typescript}/server`.

### Resource content types

- `rawHtml` — inline HTML string (what we'd use).
- `externalUrl` — point at a hosted app (iframe `src`), not reviewable
  the same way, deferred from the MCP Apps MVP for that reason.
- `remoteDom` — a React/DOM diffing protocol for richer, framework-driven
  UI without shipping raw HTML.

### Minimal Python example

```python
from mcp_ui_server import create_ui_resource

resource = create_ui_resource({
    "uri": "ui://my-server/approval-card",
    "content": {
        "type": "rawHtml",
        "htmlString": "<h1>Approve this change?</h1>",
    },
    "encoding": "text",
})

tool_result = {"content": [resource.to_dict()]}
```

### Is this usable from our Python MCP server today?

**Directly as a protocol: no** (same reason as §1 — Antigravity doesn't
consume `ui://` resources or the `content` shape mcp-ui produces for a
tool result).

**As an HTML-generation helper: yes, trivially, and cheaply.** Nothing
stops us from calling `create_ui_resource(...)` purely to get back a
sanitized/well-formed HTML string, extract `.text` out of it ourselves, and
write that string to the temp file our `ApprovalServer.widget()` already
serves via `<agent-embed>` — throwing away the MCP resource envelope and
keeping only the HTML. This buys us: a library-maintained escaping/
encoding path instead of hand-rolled `html.escape`, and free future
compatibility if we ever also want to expose the same card as a real
`ui://` resource for a host that supports it (Claude, Goose, etc.), without
maintaining two separate HTML templates.

**Cost:** adding `mcp-ui-server` as a dependency (pure-Python, no native
deps per PyPI page) plus a thin wrapper function; under an hour of work,
optional, and not required to improve the card's visual design (that's
CSS/markup, orthogonal to which library assembles the string).

---

## 3. Existing approval / confirmation / human-in-the-loop UI components

None of these are drop-in for Antigravity's static-HTML-file-over-loopback
model — they're all React components meant for a client that renders
tool-call state itself. They're useful as **design references and
copy-paste starting points for markup/CSS**, not as installable
dependencies for our Python MCP server.

### MUI X `ChatConfirmation`

https://mui.com/x/react-chat/ai-and-agents/tool-approval/

Part of `@mui/x-chat` (MUI's AI/agent-chat component set). Renders as an
**inline, non-modal** element — the docs explicitly call out that it is
"deliberately not an `alertdialog`," i.e. don't trap focus or block the
rest of the conversation for an approval prompt. Two buttons with
customizable labels (`confirmLabel`/`cancelLabel`, e.g. "Send email"
instead of generic "Approve") rather than hardcoded verbs. Good takeaway
even without adopting the library: **make the action verbs specific to the
operation**, not just "Approve/Decline" (e.g. "Send email" / "Don't send").
Licensing (MUI X commercial tiers) not confirmed from this page alone — not
relevant since we wouldn't be installing it anyway.

### beUI `tool-approval`

https://beui.dev/components/agents/tool-approval

React + Tailwind + `motion/react`, installable via shadcn CLI
(`bunx --bun shadcn add @beui/tool-approval`) or copy-paste (shadcn-style
components ship as source you own, not an opaque npm dependency — the
normal way to "adopt" a shadcn component is to read its source and adapt
it). Card layout: shield icon + title ("Allow this tool to run?") + tool
identifier + status badge, a description line, an **expandable** details
section with parameters in a narrow two-column grid, and **three** buttons
at the base: "Allow once" (primary), "Always allow" (secondary), "Deny"
(tertiary). Animated state transitions (approving → approved → running →
complete), respects `prefers-reduced-motion`. beUI Pro is paid
($179 lifetime per the page) but the base component set is also on GitHub
(noted ~1.3k stars) — I did not independently verify the free-tier license
terms; treat "free to copy" as unverified without checking the GitHub repo
directly.

**Directly relevant idea for our card**: the two-column parameter grid
instead of a raw `<pre>{JSON}</pre>` dump, and the three-tier action set
(once / always / deny) as a pattern to consider if our approval flow ever
needs a "remember this decision" option.

### Goose's native `ToolConfirmation`

Goose (Block's open-source agent, https://block.github.io/goose/) does
**not** use mcp-ui/MCP Apps for its own built-in tool-approval prompt —
that's a separate, native Desktop-app React component. Sources:
https://deepwiki.com/block/goose/6.2-permission-modes-and-tool-approval and
https://goose-docs.ai/docs/guides/managing-tools/goose-permissions/
(secondary/community-maintained pages, not the primary Goose repo docs —
flagged as such). Pattern: an `ActionRequired` message suspends the agent
loop; the UI renders Allow/Deny; permission modes are Auto / Approve (with
optional "Smart Approve" risk-based auto-approval of low-risk actions) /
Chat-only. A known, documented UX gap
(https://github.com/aaif-goose/goose/issues/2371) is that when several
tool calls queue up, it's hard to tell which approval prompt maps to which
call — worth avoiding in our own design by always showing the operation
name and a short unique hash directly on the card, which our current
template already does.

### Diff / structured-payload display

For "show a proposed change compactly," relevant open-source components
(all frontend/JS, not something a Python MCP server would run, but the
patterns are the point):

- `react-diff-view` (https://www.npmjs.com/package/react-diff-view) — unified
  or split diff rendering with **collapsed unchanged hunks** exposed via
  `expandCollapsedBlockBy`; the "collapse everything that didn't change,
  expand on demand" pattern is the single most reusable idea for a JSON
  payload display.
- `virtual-react-json-diff` (https://www.npmjs.com/package/virtual-react-json-diff)
  — JSON-specific: collapses unchanged regions, per-hunk accept/reject
  controls, virtualized (doesn't mount the whole tree) for large payloads.
- `react-jsondiff` (https://github.com/johnwdunn20/react-jsondiff), a thin
  wrapper over `jsondiffpatch` — the search results themselves note
  jsondiffpatch's raw output is "extremely dense... unusable for
  non-technical users," which is a useful caution: don't reach for a
  generic diff algorithm's default rendering without a UI pass on top.

None of these are worth taking on as dependencies for a single-file static
HTML card with no build step. The actionable takeaway is the **pattern**:
truncate/collapse by default, show a count of hidden/unchanged
fields, expand on click — applicable with ~20 lines of vanilla JS in our
existing `<pre>` block instead of a library.

---

## 4. Design references — concrete, copyable guidance

### Claude's official MCP Apps design guidelines (best source found)

https://claude.com/docs/connectors/building/mcp-apps/design-guidelines

This is the single most directly reusable source for our redesign — exact
tokens, not vibes. Also links a Figma kit:
https://www.figma.com/community/file/1597641111449594397/mcp-apps-for-claude

**Inline card constraints (their "Inline card" display mode — this is our
use case):**

- Height: **auto-fits to content, no nested scrolling** (our current
  `<pre>` has `max-h-40 overflow-auto` — this is exactly the pattern
  Claude's guidelines call an anti-pattern: "nested scrolling... inline
  cards should auto-fit content height." Worth fixing: truncate the JSON
  text itself with an expand affordance instead of a scrollable box.)
- **Max 2 actions**, placed at the bottom of the card (we already do this:
  Approve/Decline).
- **Max 4-5 data points** shown at once.
- No drill-ins, breadcrumbs, multiple views, menus, or popovers — "prefer
  visible controls like segmented buttons, toggles, or inline options."
- Mobile: full-width, **44×44pt minimum tap targets**.

**Exact design tokens** (CSS custom properties Claude injects; directly
portable as reference values even though Antigravity injects its own,
differently-named set):

- Border radius scale: `4px / 6px / 8px / 10px / 12px / full(9999px)` for
  xs/sm/md/lg/xl/full — "a limited set of corner radii... keeps your app
  feeling native." Antigravity's own skill doc doesn't specify a radius
  scale at all; adopting one (e.g. `rounded-md` for buttons, `rounded-xl`
  for the card, consistent with what Antigravity's own boilerplate
  template already uses) is free and immediately applicable.
- Typography: **three-level scale (heading/body/caption), two weights
  (regular, emphasized)** — "creates clear hierarchy without visual
  noise." Sizes: `12/14/16/20px` (text), up to `36px` (largest heading).
  Our card currently uses `text-[15px]`, `text-[13px]`, `text-[11.5px]`,
  `text-[11px]`, `text-[10.5px]` — five distinct sizes for a single small
  card, more granularity than the guidance recommends.
- Border width: `0.5px` (hairline) is their standard, not `1px`.
- Shadows: `shadow-hairline` through `shadow-lg`, all very low-opacity
  (`rgba(0,0,0,0.05–0.1)`), i.e. barely-there elevation, not the heavier
  default Tailwind shadow scale.
- Color: **use only host tokens for structural surfaces** (background,
  text, border) and reserve brand/accent color for identity elements
  only — this matches what Antigravity's own skill doc already tells us
  ("use semantic variables... instead of hardcoded dark/light utility
  classes").

**What to do about long JSON payloads** — not addressed with a specific
mechanism beyond the general "max 4-5 data points" / "no nested scrolling"
rule above; the implication is: **don't dump raw JSON at all** in an inline
card — extract the 3-5 fields a human actually needs to decide (e.g.
"file: path/to/x.py", "lines changed: +12/-4", "target: prod") and push the
full raw payload to an expand/fullscreen view if it's ever needed. This is
a stronger and more specific answer than "truncate the `<pre>` block,"
and is a genuine design change worth making to our card.

### OpenAI Apps SDK design guidance

https://developers.openai.com/apps-sdk/concepts/design-guidelines (and
reference: https://developers.openai.com/apps-sdk/reference)

Less numerically precise than Claude's page, but consistent direction:
inline cards should auto-fit content ("prevent internal scrolling"),
**max two actions per card** ("one primary CTA and one optional secondary
CTA") placed at the card's bottom, carousels capped at 3-8 items with
max-3-line text per item. Styling is meant to come from
`@openai/apps-sdk-ui` (Tailwind + CSS variable tokens, exact variable names
not published on this page) plus "system colors for text/icons," reserving
brand accents for primary buttons only. Community reports
(https://community.openai.com/t/android-chatgpt-blocks-apps-sdk-widget-app-destructive-tool-before-mcp-while-web-ios-show-confirmation-modal-and-work/1380943)
note that ChatGPT's own native confirmation modal (not an app-authored
widget) is what actually gates destructive tool calls on web/iOS, and that
Android currently blocks such tools before the MCP server is even reached
— i.e. even in a mature host, approval UX is still visibly inconsistent
across platforms. Useful caution against assuming "we'll get a native host
confirmation for free" — we don't have one, ours has to do this itself, and
even hosts that do have one don't apply it uniformly.

### Convergent guidance across both

Both major hosts independently arrived at: **inline card auto-fits content
(no internal scroll), maximum two actions at the bottom, keep the surface
area small, push detail to an expand/fullscreen affordance.** That's a
strong, cross-vendor signal, not a single vendor's opinion — worth treating
as close to ground truth for this UI pattern.

---

## 5. Antigravity's own `<agent-embed>` conventions

### The built-in skill (read in full)

`~/.gemini/antigravity/builtin/skills/generative_ui/SKILL.md` — summarized
faithfully (not reproduced verbatim beyond short quotes, per copyright
practice):

- Mechanism: write a self-contained `.html` artifact (`UserFacing: true`),
  optionally embed with `<agent-embed src="file:///<path>">`.
- Only one external asset is allowlisted: the Tailwind CDN script at
  `https://www.gstatic.com/antigravity/web/dev/tailwindcss.min.js`; all
  other external CDNs are CSP-blocked.
- Host injects semantic theme CSS variables: `--background`, `--content`,
  `--card`, `--sidebar`, `--border`, `--foreground`, `--muted-foreground`,
  `--placeholder`, `--primary`/`--primary-foreground`,
  `--secondary`/`--secondary-foreground`, `--accent`. Do **not** declare
  local `:root` fallbacks for these.
- **Inline embeds are hard-capped at 500px height** — the `height`
  attribute on `<agent-embed>` is ignored; past 500px content scrolls
  inside a small box, which the skill explicitly says is usually the wrong
  call ("a scrolling inline widget is usually wrong — full-height in the
  side pane beats cropped in the chat"). This is the same "no nested
  scroll" rule Claude's official guidance states independently, which is
  reassuring convergence, not coincidence — Antigravity's generative_ui
  skill and MCP Apps' design guidance are solving the same problem.
- Never use viewport-relative units (`h-screen`, `100vh`, `height: 100%`)
  on the top-level container — the frame sizes itself to content, so these
  self-reference and collapse.
- Recommended boilerplate matches what our card already does: Tailwind CDN
  script tag, `bg-transparent` body, a `bg-[var(--card)]` card wrapper with
  `border-[var(--border)]`, `rounded-xl`, `shadow-sm`.

### Community write-ups

I searched specifically for third-party coverage of `<agent-embed>` and of
whether its iframe can reach `http://127.0.0.1:PORT`, and found **nothing
substantive**. A dedicated Antigravity-security community article
(https://readysetcompute.com/antigravsec/) does not mention `agent-embed`
at all despite covering Antigravity's sandboxing model broadly — I fetched
and checked this directly, it is not a case of missing the right search
term. General "what is Antigravity" coverage
(https://developers.googleblog.com/build-with-google-antigravity-our-new-agentic-development-platform/,
https://antigravity.google/blog/introducing-google-antigravity, and similar
listicle/SEO posts) exists in volume but is all product-marketing level,
not implementation detail.

**This repo's own prior research is the best source that exists** on the
open question of whether `fetch()` from inside the iframe can reach
`127.0.0.1`:
`/Users/datta/Documents/Projects/adk-harness/docs/research/antigravity-capabilities.md`,
§5. That audit (binary strings analysis, dated the same day as this
research) found **no CSP/sandbox strings anywhere in the language-server
binary** governing the embed iframe (the CSP/sandbox logic lives in the
separate Electron/Chromium shell, out of scope for that audit) and
concluded the loopback-fetch question was **empirically unresolved from
static analysis alone** — it recommended exactly the live test the task
description says we've since run and confirmed works. I could not find any
independent (non-Google, non-us) documentation of this behavior — flag it
as **verified only by our own direct experiment**, not by any published
source, official or community. If Antigravity ever tightens this (e.g. adds
a `connect-src` restriction to the embed iframe in a later release), our
card's core mechanism would break without an upstream changelog
necessarily calling it out — worth a smoke test in CI or on version bumps.

### Is any of this "reusable" beyond what we already do?

Mostly, we're already following the documented convention (Tailwind CDN,
theme vars, transparent root, card wrapper, two bottom-aligned buttons,
sub-500px height budget). The gaps against the *combined* guidance from
Antigravity's own skill + Claude's + OpenAI's design pages are:

1. **Kill the internal `max-h-40 overflow-auto` scroll** on the JSON block
   — every source above calls nested/internal scrolling in an inline card
   an anti-pattern. Replace with: show a short human-readable summary of
   the operation (not raw JSON) plus a collapsed/truncated raw-payload
   toggle that, if expanded, still fits under 500px or triggers a
   fullscreen artifact instead.
2. **Tighten the type scale** — we currently use 5 distinct font sizes in
   one small card; Claude's guidance recommends 2-3 (heading/body/caption).
3. **Consider a third action state** (beUI's "always allow" idea) only if
   our approval model actually wants to support remembered decisions —
   otherwise stay at 2 actions per every design source above.
4. **Show the operation name and hash prominently** (we already do) —
   this directly avoids the ambiguity problem Goose users hit when
   multiple approvals queue up.

---

## Summary table — usable today, cost, sources

| Item | Usable from our Python MCP server today? | Adoption cost | Primary source |
|---|---|---|---|
| MCP Apps / SEP-1865 protocol | No (Antigravity doesn't implement `ui://`) | N/A now; medium later if porting to Claude/Goose/etc. | https://modelcontextprotocol.io/seps/1865-mcp-apps-interactive-user-interfaces-for-mcp |
| `mcp-ui` TS/Python/Ruby SDKs (transport) | No, same reason | N/A now | https://github.com/MCP-UI-Org/mcp-ui |
| `mcp-ui-server` Python package (HTML-gen only) | Yes, optionally, as a string-builder | Low (~1hr, optional dependency) | https://pypi.org/project/mcp-ui-server/ |
| MUI X `ChatConfirmation`, beUI `tool-approval` | No (React components, wrong runtime) | N/A as dependency; free as design reference | https://mui.com/x/react-chat/ai-and-agents/tool-approval/, https://beui.dev/components/agents/tool-approval |
| Goose native `ToolConfirmation` pattern | No (native Desktop component) | Free as design reference | https://deepwiki.com/block/goose/6.2-permission-modes-and-tool-approval (secondary source, unverified against Goose's own primary docs) |
| Diff/JSON-collapse libraries (react-diff-view, virtual-react-json-diff) | No (JS, and no build step in our card) | Free as a UX *pattern* to hand-roll in vanilla JS | https://www.npmjs.com/package/react-diff-view, https://www.npmjs.com/package/virtual-react-json-diff |
| Claude MCP Apps design guidelines | Yes — directly copyable CSS values | Very low (rewrite Tailwind classes) | https://claude.com/docs/connectors/building/mcp-apps/design-guidelines |
| OpenAI Apps SDK design guidelines | Yes — directional guidance, few exact values | Very low | https://developers.openai.com/apps-sdk/concepts/design-guidelines |
| Antigravity `generative_ui` skill | Already largely followed | None — verify against gaps above | `~/.gemini/antigravity/builtin/skills/generative_ui/SKILL.md` (local) |

## Things flagged as unverified / could not confirm

- beUI's free-tier license terms for the base component set (only the paid
  "Pro" price was stated on the page fetched; did not check the GitHub repo
  license file directly).
- Whether MUI X Chat's `ChatConfirmation` is available on a free/community
  tier or requires a commercial MUI X license.
- Any Antigravity roadmap intent to adopt `ui://`/MCP Apps — found no
  evidence either way, not even a feature request.
- Whether Antigravity's `<agent-embed>` iframe's ability to `fetch()`
  `127.0.0.1` is a deliberate, stable design decision versus an
  unenforced gap that could close in a future release — no published
  source (official or community) discusses this; only our own direct test
  and our own prior binary audit exist as evidence.
- LibreChat MCP Apps support — confirmed **not yet implemented** (open
  issue), included above only to rule it out explicitly since the task
  asked about it by name.
