# Google Antigravity — Official & Queryable Documentation Sources

Research date: 2026-08-29. Target app: Antigravity 2.11.0 (macOS).

The goal of this document is narrow: **what can an AI agent query at runtime**
to answer questions about Google Antigravity and its plugin/extension system,
without reverse-engineering the binary. Short answer up front: there is a real,
official, machine-readable index (`llms.txt`) plus a fully static docs site
that any HTTP client can fetch, a real Apache-2.0 SDK repo, and a real (but
undocumented as an API) CLI repo. There is **no** official docs MCP server, no
official JSON Schema files for the config formats, no `llms-full.txt`, and no
Antigravity-specific presence on `developers.google.com`, `cloud.google.com`,
or `ai.google.dev`.

---

## Recommended reading order

1. **`https://antigravity.google/llms.txt`** — start here. It's the official
   sitemap-for-agents: one small, plain-text file enumerating every doc page.
   Fetch it once, then fetch only the specific `/docs/...` pages you need.
2. **`~/.gemini/antigravity/builtin/skills/agy-customizations/docs/*.md`**
   (local, already on disk) — ground truth for what the *installed 2.11.0
   binary* actually implements for rules/skills/plugins/hooks/MCP. Prefer this
   over the live site when the two disagree, since the live site documents the
   latest web release, which can be ahead of an installed app build.
3. **`https://antigravity.google/docs/mcp`**, **`/docs/plugins`**,
   **`/docs/skills`**, **`/docs/hooks`**, **`/docs/rules-workflows`** — live,
   fetchable, currently richer than the bundled docs (e.g. `authProviderType`,
   `cwd`, OAuth headers for MCP are documented live but not in the local
   skill).
4. **`https://github.com/google-antigravity/antigravity-sdk-python`** (README
   + `skills/` + `examples/`) — for anyone embedding Antigravity agents in
   Python rather than driving the desktop app/CLI.
5. Everything else below (changelog, codelabs, community sites) is
   supplementary — consult only for the specific gaps called out per-source.

---

## 1. Official Antigravity product documentation

| Source | Covers | Official | Agent-queryable |
|---|---|---|---|
| `https://antigravity.google/llms.txt` | Full machine-readable index of every doc/product/use-case page on the site (~11 KB plain text, Markdown-link format) | Yes | **Yes** — plain HTTP GET, no auth, no rendering needed |
| `https://antigravity.google/docs` (and every `/docs/...` page) | Full docs site: getting started, Antigravity 2.0, IDE, CLI (incl. per-command reference under `/docs/cli/commands/*`), SDK docs, MCP, skills, rules/workflows, plugins, hooks, sidecars, permissions, subagents, artifacts | Yes | Yes — statically generated (Astro + Starlight), plain HTML, no JS execution needed to get the content. Verified by `curl` (see Notes). |
| `https://antigravity.google/sitemap.xml` (and `/sitemap-index.xml`) | Standard XML sitemap, ~184 URLs across docs, blog, product, use-cases | Yes | Yes — standard XML sitemap format |
| `https://antigravity.google/changelog` and `/releases` | Version history / release notes | Yes | Yes (static HTML) |
| `https://antigravity.google/docs/mcp` | `mcp_config.json` schema. **Confirmed by raw fetch**: transports are `command`/`args`/`env`/`cwd` (stdio) and `serverUrl` (SSE/Streamable HTTP/WebSocket). The page explicitly states: *"Legacy fields like `url` or `httpUrl` are not supported."* Also documents `authProviderType: "google_credentials"`, OAuth client credentials, and custom headers for API keys/bearer tokens — none of which appear in the locally bundled skill docs, so this is a case of the live docs being ahead of the installed 2.11.0 build. | Yes | Yes |
| `https://antigravity.google/docs/plugins` (and `/docs/ide/plugins/`, `/docs/cli/plugins/`) | `plugin.json` schema and directory layout | Yes | Yes |
| `https://antigravity.google/docs/skills` | `SKILL.md` frontmatter (`name`, `description`), directory layout, progressive disclosure | Yes | Yes |
| `https://antigravity.google/docs/rules-workflows` | `GEMINI.md`/`AGENTS.md` rule loading | Yes | Yes |
| `https://antigravity.google/docs/hooks` | `hooks.json` schema, lifecycle events (`PreToolUse`, `PostToolUse`, `PreInvocation`, `PostInvocation`, `Stop`), matcher syntax, decision values | Yes | Yes |
| `https://antigravity.google/docs/sidecars` | Sidecar processes (not covered in local skill docs at all — live-only) | Yes | Yes |
| `https://codelabs.developers.google.com/getting-started-with-antigravity-skills` | Step-by-step skill-authoring tutorial (routing → assets → few-shot → scripts) | Yes — Google Codelabs branding, CC-BY-4.0 footer | Yes (static page) |
| `https://codelabs.developers.google.com/getting-started-google-antigravity` | General onboarding codelab | Yes | Yes |

### What does *not* exist (stated plainly, since you're reverse-engineering the binary)

- **No official JSON Schema files.** A community blog post
  (`aibuilderclub.com`) claims `plugin.json` supports a
  `"$schema": "https://antigravity.google/schemas/v1/plugin.json"` key. That
  URL returns a plain **404** — verified directly. Treat that specific claim
  as fabricated/unverified; the official docs never show a `$schema` field.
- **No `llms-full.txt`.** `https://antigravity.google/llms-full.txt` → 404.
- **No official docs MCP server.** Nothing on `antigravity.google` exposes an
  MCP endpoint for querying its own documentation. (See §3 for the
  community-built bridge pattern that fills this gap.)
- **No Discovery API entry.** Querying Google's API Discovery Directory
  (`https://www.googleapis.com/discovery/v1/apis?name=antigravity`) returns an
  empty directory listing — Antigravity has no registered Google API.
- **No presence on `developers.google.com/antigravity`** (404), and no
  `llms.txt` on `developers.google.com`, `cloud.google.com`, or
  `ai.google.dev` root (all checked, all 404). `ai.google.dev/api/llms.txt`
  exists but is scoped to the Gemini API and makes **no mention of
  Antigravity**.

### Notes on how the docs site actually works (relevant to "queryable")

The docs site (`antigravity.google/docs/*`) is built with **Astro v7 +
Starlight v0.41.5**, a static-site generator — confirmed via the page's
`<meta name="generator">` tags. This means the full text content is present in
the raw HTML returned by a plain `curl`/HTTP GET; no headless browser or JS
execution is required for an agent to extract the config schemas, examples, or
prose. This is good news for programmatic access: a simple fetch-and-strip-tags
pipeline is sufficient.

---

## 2. The Antigravity SDK (Python, Apache-2.0)

- **Repo**: `https://github.com/google-antigravity/antigravity-sdk-python`
  (GitHub org is `google-antigravity`, all-lowercase — case-insensitive on
  GitHub, so the `Google-Antigravity` capitalization in the task also
  resolves). Confirmed via GitHub API: public, not a fork, not archived,
  license file present, Apache-2.0.
- **PyPI**: `pip install google-antigravity` — confirmed live on PyPI, current
  version `0.1.15`, project URL points back to the same GitHub repo.
- **License**: Apache License 2.0, confirmed by fetching the raw `LICENSE`
  file via the GitHub API.
- **Queryable programmatically**: Yes, several ways —
  - GitHub REST API (`api.github.com/repos/google-antigravity/antigravity-sdk-python/...`) for README, file contents, releases, issues.
  - `raw.githubusercontent.com/google-antigravity/antigravity-sdk-python/main/...` for direct file fetches (README.md, any file under `skills/`, `examples/`).
  - PyPI JSON API (`https://pypi.org/pypi/google-antigravity/json`) for version/metadata.
  - The installed package itself ships docstrings/README files under
    `google/antigravity/` once `pip install`ed.

### What the SDK can do that the desktop app/IDE/CLI cannot

- Fully programmatic, headless agent orchestration from Python: spawn an
  `Agent`, stream tokens/thoughts/tool-calls, run multi-agent "round-based" or
  "async peer-to-peer" conversations (see `examples/deep_dives/round_based_chat.py`,
  `async_chat.py`), and register **arbitrary Python functions as tools** with
  no IDE/CLI in the loop.
- Deploy against **Vertex AI / Gemini Enterprise Agent Platform**
  (`LocalAgentConfig(vertex=True, ...)`) — a first-class, code-level path to
  enterprise GCP infra that the desktop products expose only via UI settings.
- Fine-grained, code-level **policy functions** (`deny()`, `allow()`,
  `ask_user()`, `enforce()`) and background **triggers** for event-driven
  agent invocation — a strictly more programmable surface than the desktop
  app's Settings-panel permission toggles.
- Runs anywhere Python + the compiled runtime binary run (CI pipelines, test
  suites, servers) — not tied to an interactive desktop session.

### What the desktop app/IDE/CLI can do that the SDK's docs don't claim

- The SDK's own docs (README + `skills/README.md`) make **no mention of the
  desktop app, `plugin.json`, `mcp_config.json` at `~/.gemini/config/`, or the
  `.agents/` workspace-discovery mechanism** described in §1. The SDK has its
  own, separate MCP integration (`McpStdioServer`, connecting *out* to
  external MCP servers as a client) and its own skill-loading mechanism
  (`examples/getting_started/agent_skills.md` shows loading `SKILL.md` files
  programmatically) — but nothing in the SDK docs ties this to the
  app/IDE/CLI's plugin bundle format (`plugins/<name>/plugin.json` +
  `mcp_config.json` + `hooks.json` + `skills/` + `rules/` all in one
  directory). No hooks.json-style lifecycle-hook system either — the SDK uses
  its own Python-level hook/middleware pattern instead (see
  `deep_dives/agent_middleware.py`, `host_tool_hooks.py`).
- Native UI affordances obviously specific to the desktop products: inline
  code lenses, visual diff overlays, Tab-to-jump/Tab-to-import autocomplete,
  the Manager view for orchestrating up to 5 parallel agents, Scheduled Tasks
  UI, and the browser-automation/artifact-review pipeline.
- **Conclusion**: the SDK and the desktop app/IDE/CLI are sibling products
  sharing a runtime and a conceptual vocabulary (skills, MCP, hooks, policies)
  but are **not documented as interoperable** — e.g. there's no stated way to
  point the SDK at a `plugins/` bundle built for the desktop app, or vice
  versa. If you need that bridge, it isn't documented; assume it doesn't
  exist rather than reverse-engineering it.
- **Bonus finding**: the GitHub org also publishes a second public repo,
  `https://github.com/google-antigravity/antigravity-cli` ("Antigravity CLI
  brings the reasoning, execution, and orchestration capabilities of
  Antigravity agent harness directly into your terminal"). Unlike the SDK repo
  it carries **no license file** (`license: null` from the GitHub API) — treat
  its code as All-Rights-Reserved/source-available rather than open-source
  until a LICENSE appears. It was not part of the task's explicit ask but is
  the other half of "every official GitHub repo," so it's noted here.
- The SDK repo also ships a `skills/` directory at its root (separate from the
  desktop app's skill system) containing a `google-antigravity-sdk` skill
  package — a SKILL.md-formatted teach-the-agent-about-this-SDK skill,
  installable via the Vercel skills CLI (`npx skills`) or the Context7 skills
  CLI. This is a skill *about* the SDK, not a bridge *to* the desktop app.

---

## 3. Machine-queryable knowledge bases an agent could call

| Candidate | Exists for Antigravity? | Detail |
|---|---|---|
| **`llms.txt`** | **Yes** — `https://antigravity.google/llms.txt` (confirmed live, 11,179 bytes, plain Markdown-link list of every doc/product/use-case page, explicitly labeled in its own text as "listing all available paths and resources for LLM processing") | This is the best answer to "official machine-queryable index." |
| **`llms-full.txt`** | No — 404 | — |
| **Official docs MCP server** | No | Nothing under `antigravity.google` exposes an MCP endpoint. The closest real-world pattern is the community **`mcpdoc`** tool, which wraps *any* `llms.txt` URL (including third-party ones like `adk.dev/llms.txt`) into MCP tools (`search_docs`, `get_page_content`). You could point `mcpdoc` at `antigravity.google/llms.txt` yourself, but that's a self-assembled bridge, not something Google ships. |
| **Discovery API entry** (`googleapis.com/discovery/v1/apis`) | No | Empty result when filtered by name `antigravity`; Antigravity has no registered Google API product. |
| **Google Cloud doc-search APIs** (Vertex AI Search / Discovery Engine) | Not Antigravity-specific | These are generic enterprise search products you could *point* at Antigravity's docs yourself (e.g. crawl `antigravity.google/docs` into a Vertex AI Search data store), but Google does not run one for you, and there is no ready-made Antigravity index to query. |
| **`ai.google.dev/api/llms.txt`** | Exists, but scoped to the Gemini API | Confirmed live; makes no mention of Antigravity. Not useful for this task beyond ruling it out. |
| **`developers.google.com`, `cloud.google.com` root `llms.txt`** | No | Both 404. |
| **Sitemap XML** | Yes | `antigravity.google/sitemap.xml` — ~184 URLs, standard machine-parseable format, a valid (if noisier) fallback index to `llms.txt`. |
| **GitHub REST API** | Yes, for the two org repos | Full programmatic access to README/file contents/releases/issues for `antigravity-sdk-python` and `antigravity-cli`. |
| **PyPI JSON API** | Yes | `https://pypi.org/pypi/google-antigravity/json` for SDK version/metadata. |

**Bottom line for §3**: the only thing Google itself publishes that is
purpose-built for agent consumption is the `llms.txt` index. Everything past
that (docs pages, sitemap, GitHub, PyPI) is "queryable" only in the generic
sense that it's plain HTTP/JSON — which is still genuinely useful, just not a
dedicated docs-search API.

---

## 4. Built-in skills shipped inside the app (local, read from disk)

Read directly from the installed 2.11.0 app at
`~/.gemini/antigravity/builtin/skills/`. These are the app's own
self-description and are the most authoritative source for what *this
specific installed build* actually does (as opposed to the live docs site,
which can describe newer/future behavior).

### `antigravity_guide/SKILL.md` + `references/{app,cli,ide,sdk}.md`

Positions itself as a sitemap/router: for each surface (CLI, IDE, "Antigravity
2.0" desktop app, SDK) it gives a compact reference and then explicitly
instructs the agent to fetch the live doc pages listed under a
`<!-- LINT.IfChange(sitemap) -->` block for anything beyond the basics — i.e.
the app's own built-in skill *tells the agent to go read
`antigravity.google/docs/*` live*, which independently corroborates that
those live pages are the intended authoritative source. Notably its own
embedded sitemap list (Skills, Rules, Hooks, Plugins, Sidecars, MCP, Browser
Automation, Permissions, Changelog, Support) matches what's actually live on
the site today.

Architecturally, it describes:
- **Antigravity 2.0** (desktop, Electron) as a parallel surface to the IDE, with a left sidebar (New Conversation, Projects, Scheduled Tasks, Skills & Customizations, Settings), a Chat Canvas (slash commands, @-mentions, media uploads), and global/project-level settings for tool execution policy, sandboxing, file/internet access policy, permission grants, and artifact review mode.
- **Antigravity IDE** (VS Code-based) as offering three AI modalities: passive Tab-completion (Autocomplete/Supercomplete), instructive inline Cmd/Ctrl+I edits, and collaborative Sidebar Chat/Agent mode with a Planning mode.
- **Antigravity CLI (`agy`)** as a terminal TUI, configured via `~/.gemini/antigravity-cli/settings.json`.
- **Antigravity SDK** as the public Python package for programmatic agent leasing/orchestration (matches §2 above).

### `agy-customizations/SKILL.md` + `docs/{rules,skills,plugins,hooks,mcp_servers,json_configs}.md`

This is the most detailed and load-bearing of the three — it's effectively the
canonical internal spec for the whole customization system. Key architectural
claims, all read verbatim from disk (full text captured during this
research):

- **Five customization types**, each with its own config surface: Rules
  (`GEMINI.md`/`AGENTS.md`), Skills (`skills/<name>/SKILL.md`), Plugins
  (`plugins/<name>/plugin.json`), Hooks (`hooks.json`), MCP Servers
  (`mcp_config.json`).
- **Discovery locations**: workspace (`.agents/`, `.agent/`, `_agents/`,
  `_agent/`, walked up to the repo root), directory-hierarchical rules
  (`GEMINI.md`/`AGENTS.md` walked from file location to repo root), and global
  (`~/.gemini/config/`). Built-ins are *mounted by name*, not discovered.
- **Precedence order** (highest to lowest): Workspace Project → Declared
  configs (`skills.json`/`plugins.json`) → Global Discovery → Built-in →
  Global Declared configs.
- **Progressive disclosure**: skills/model-decision rules are not loaded into
  context by default — only name+description — until the model or user
  activates them; only `always_on` rules load unconditionally.
- **`mcp_config.json`** supports Stdio (`command`/`args`/`env`) and SSE
  (`serverUrl`) transports; global at `~/.gemini/config/mcp_config.json` or
  per-plugin at `plugins/<name>/mcp_config.json`. (The live docs page adds
  `cwd` and auth fields not present in this bundled copy — see §1's
  version-drift note.)
- **`plugin.json`** is a thin marker file — only an optional `name` field,
  defaulting to the directory name if omitted. Plugins bundle skills, rules,
  hooks, and MCP config into `plugins/<name>/{plugin.json, mcp_config.json,
  hooks.json, rules/, skills/}`. Enable/disable state lives in `config.json`'s
  `plugins` map (keyed by directory name) and always overrides the plugin's
  own `"disabled"` declaration.
- **`hooks.json`** is the most fully specified surface: five lifecycle events
  (`PreToolUse`, `PostToolUse`, `PreInvocation`, `PostInvocation`, `Stop`),
  each with a documented stdin/stdout JSON contract (camelCase/protojson
  fields), a regex `matcher` for tool-scoped events, `decision` values
  (`allow`/`deny`/`ask`/`force_ask`), and a stated current limitation: only
  `type: "command"` (shell) hooks exist — no HTTP or prompt hooks, and hooks
  run **synchronously**, blocking the agent loop. Another version-drift data
  point: the live `/docs/hooks` page lists a fifth `decision` value,
  `deny_unless_prior_grant`, that is absent from this bundled 2.11.0 copy.
- **`skills.json`/`plugins.json`**: explicit registration files supporting
  `entries` (paths to scan, with `include_only`/`exclude` regex filters) and
  `inherits` (compose from other JSON configs) — the documented mechanism for
  sharing customizations via VCS across a team.

### `migrate-workflows/SKILL.md`

A narrower, mechanical skill: migrates legacy `workflows/*.md` files (and
`workflows.json` manifests) into the modern `skills/<name>/SKILL.md` format,
idempotently, archiving originals as `.md.bak`. Mainly useful as confirmation
that "workflows" is a deprecated predecessor concept to "skills" — not an
active extension point in 2.11.0.

### Also present but not asked about

Two other built-in skill directories exist alongside the three requested ones:
`~/.gemini/antigravity/builtin/skills/generative_ui/` and
`.../permissioned-github/`. Not read in depth for this task since they weren't
in scope, but worth knowing they exist if a future pass needs the full
built-in skill inventory.

---

## 5. Community / third-party references (clearly unofficial)

None of these are queryable APIs — they're human-readable pages, listed only
because the task asked for community references that "look accurate."
Accuracy varies; treat all of them as secondary to §1/§2/§4.

| Source | Notes |
|---|---|
| `https://medium.com/google-cloud/tutorial-getting-started-with-antigravity-skills-864041811e0d` and the "Documentation-Aware Agents" Medium post | Google Cloud Community-tagged Medium posts (author-published, not Google-authored) — generally consistent with official docs on skill structure. Unofficial. |
| `https://nikhilmiranda.medium.com/antigravity-how-to-set-up-skills-6e75496496ce` | Independent blogger walkthrough. Unofficial. |
| `https://www.freecodecamp.org/news/make-your-antigravity-agent-skills-configurable-without-forking-them/` | freeCodeCamp tutorial on skill configurability patterns. Unofficial but reputable outlet. |
| `https://github.com/rmyndharis/antigravity-skills` | Community-curated collection of Agent Skills. Unofficial, unaffiliated with Google. |
| `https://skillsmp.com/...` | Third-party skill marketplace/index that lists the official SDK's bundled skill. Unofficial. |
| `https://www.antigravity-ide.com/` | Self-described "Antigravity IDE Community — Guides, Tutorials & Reviews (**Unofficial**)" — the site's own name states its unofficial status. Returned HTTP 403 to automated fetch during this research, so content wasn't verified beyond the title. |
| `https://beginnersinai.org/google-antigravity/`, `https://www.aibuilderclub.com/blog/google-antigravity-complete-guide`, `https://antigravityide.org/`, `https://agentpedia.codes/...`, `https://www.cloudvyn.com/...`, `https://www.agensi.io/...` | Generic third-party "complete guide" / SEO-style blog content. **Caution**: the aibuilderclub.com post asserts a `$schema` field in `plugin.json` pointing at `antigravity.google/schemas/v1/plugin.json` — that URL 404s (verified directly). This specific claim is inaccurate/fabricated; don't trust config-schema details from this tier of source without cross-checking against §1. |
| `https://github.com/topics/google-antigravity` | GitHub topic tag aggregating community repos tagged `google-antigravity` — a discovery surface, not a doc source itself, but useful for finding more third-party tooling (e.g. `mcpdoc`-style bridges). |

---

## Appendix: verification methods used

- `antigravity.google/llms.txt`, `/llms-full.txt`, `/docs/mcp`, `/robots.txt`,
  `/sitemap.xml` fetched directly via `curl` (raw bytes, not AI-summarized) to
  confirm exact content/existence and resolve a summary discrepancy over
  `serverUrl` vs `url`/`httpUrl`.
- `developers.google.com/llms.txt`, `cloud.google.com/llms.txt`,
  `ai.google.dev/llms.txt`, `antigravity.google/docs/llms.txt`,
  `antigravity.google/schemas/v1/{plugin,mcp_config,hooks,skill}.json` all
  checked via `curl -o /dev/null -w "%{http_code}"` — all 404.
- GitHub org and repo metadata (`google-antigravity/antigravity-sdk-python`,
  `google-antigravity/antigravity-cli`, license file, org repo list) via the
  public GitHub REST API (`api.github.com`), unauthenticated.
- PyPI package metadata via `pypi.org/pypi/google-antigravity/json`.
- Google API Discovery Directory queried via
  `googleapis.com/discovery/v1/apis?name=antigravity`.
- Local built-in skill files read directly from
  `~/.gemini/antigravity/builtin/skills/{antigravity_guide,agy-customizations,migrate-workflows}/`.
