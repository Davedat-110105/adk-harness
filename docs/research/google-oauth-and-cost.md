# Google OAuth and API cost model for a self-serve Workspace MCP tool

Research date: 2026-08-29. Scope: the two shapes we're building — (a) a **local
server** that runs the browser OAuth flow itself on the user's machine, and
(b) a **hosted server** that receives a bearer access token per request. In
both shapes the tool list is generated dynamically from whatever OAuth scopes
the user actually granted, sourced from Google API discovery documents
(Gmail, Calendar, Docs, Sheets, Drive). Every claim below links to an
official Google source; where behavior depends on Workspace edition or admin
policy, that's called out explicitly.

---

## 1. Scope selection UX

### What the consent screen actually shows

When an app requests **more than one non-sign-in scope**, or a **mix of
sign-in scopes (`openid`, `email`, `profile`) and non-sign-in scopes**,
Google shows the **granular consent screen**: each requested permission
appears with its own checkbox, and the user can check/uncheck permissions
individually rather than accepting an all-or-nothing bundle. Apps that
request only sign-in scopes, or exactly one non-sign-in scope, don't trigger
this screen and instead get a simpler "Allow"/"Cancel" prompt.
- [How to handle granular permissions](https://developers.google.com/identity/protocols/oauth2/resources/granular-permissions)
- [Google Workspace Updates: Granular OAuth consent in HTTP Google Workspace add-ons](https://workspaceupdates.googleblog.com/2025/05/granular-oauth-consent-in-http-google-workspace-add-ons.html)

For our tool — requesting Calendar + Gmail + Docs + Sheets + Drive scopes in
one authorization request — this means the user will see a checkbox per
scope (or per logical grouping Google renders) and can approve, say, Calendar
and Sheets while declining Gmail and Drive. **Your code must not assume the
full requested set came back.** Google's own guidance: check which scopes
were granted and disable/gray out any tool or feature that depends on a
declined scope rather than erroring or crashing.
- [Granular permissions guide, "handle it in your code" section](https://developers.google.com/identity/protocols/oauth2/resources/granular-permissions)

Design implication for the MCP tool-list generator: build the tool list from
the *actually granted* scope set (see below), not from the scopes you
requested. A user who granted only Calendar + Sheets should see a Calendar-
and Sheets-shaped tool list, with no Gmail/Drive/Docs tools advertised (and
no confusing 403s when the model tries to call them).

### How the granted scope set comes back

Two mechanisms, both from Google's own OAuth libraries and endpoints:

1. **The `scope` field on the token response.** When you exchange the
   authorization code for tokens, the token response includes a `scope`
   parameter listing what was actually granted (space-delimited). This is
   the authoritative, cheapest way to know what the user approved at grant
   time. Google's incremental-authorization guidance explicitly tells apps
   to check the returned scope string rather than assume the requested set:
   "Your app should always check which scopes were granted by the user and
   handle any denial of scopes by disabling relevant features."
   - [Granular permissions guide](https://developers.google.com/identity/protocols/oauth2/resources/granular-permissions)
   - [Using OAuth 2.0 for Web Server Applications](https://developers.google.com/identity/protocols/oauth2/web-server)

2. **The tokeninfo endpoint**, for verifying an access token later (e.g. a
   hosted server checking a bearer token it just received, or re-checking
   scopes on a long-lived local token). Call:
   `https://www.googleapis.com/oauth2/v1/tokeninfo?access_token=<TOKEN>`
   (or `https://oauth2.googleapis.com/tokeninfo` — Google's newer host for
   the same endpoint). The response is JSON containing the token's `scope`
   string, `expires_in`, `audience` (client ID it was issued to), and, for
   ID tokens, identity claims. This is the right place to re-derive "what
   can this bearer token actually do" independent of what your own database
   thinks was granted — important for the hosted shape where a token might
   have been re-authorized or partially revoked since you last saw it.
   - Documented in context of [Using OAuth 2.0 to Access Google APIs](https://developers.google.com/identity/protocols/oauth2) (token validation/tokeninfo pattern)
   - Also exposed at the client-library level as `hasGrantedAllScopes` /
     `hasGrantedAnyScope` for JS apps: [Google Account Authorization JavaScript API reference](https://developers.google.com/identity/oauth2/web/reference/js-reference)

**Recommendation:** read `scope` from the token exchange response as the
primary signal at authorization time; use the tokeninfo endpoint as a
point-in-time re-check whenever the hosted server needs to validate a bearer
token it didn't mint itself (it can't trust an unverified claim of "these
are my scopes" from the caller). Cache the discovery-document scope
requirements per Google API, intersect with the tokeninfo `scope` string,
and regenerate the MCP tool list from that intersection.

---

## 2. Verification: sensitive vs. restricted, and what "unverified" limits you to

Google buckets every OAuth scope into three tiers. The tier of the *most
sensitive scope you request* determines what your OAuth consent screen and
publishing status must satisfy:

- **Non-sensitive** — no special review beyond basic app registration/branding.
- **Sensitive** — requires Google's standard OAuth app verification (brand
  verification + a "why do you need this scope" justification + a demo
  video), typically 3–5 business days.
- **Restricted** — requires the same verification *plus* an annual, paid
  third-party security assessment (CASA — Cloud Application Security
  Assessment, run under the App Defense Alliance framework) if your app
  stores or transmits the restricted-scope data on a server. Re-assessment
  is required roughly every 12 months from your assessor's Letter of
  Assessment date.
  - [Sensitive scope verification](https://developers.google.com/identity/protocols/oauth2/production-readiness/sensitive-scope-verification)
  - [Restricted scope verification](https://developers.google.com/identity/protocols/oauth2/production-readiness/restricted-scope-verification)
  - [OAuth App Verification Help Center overview](https://support.google.com/cloud/answer/13463073?hl=en)

### Per-scope classification (from Google's own scope reference pages)

Google now publishes the classification directly on each API's "choose
scopes" page (Gmail's is the most explicit; Sheets/Docs/Drive mirror the
same three-tier layout). Calendar's scopes page doesn't render the tier
table the same way, but Google's sensitive-scope-verification doc names
"reading events stored in Google Calendar" as its own canonical example of a
*sensitive* (not restricted) scope, consistent with third-party
cross-references.

| API | Scope | Tier |
|---|---|---|
| Gmail | `gmail.labels` | Non-sensitive |
| Gmail | `gmail.send` | **Sensitive** |
| Gmail | `gmail.readonly` | **Restricted** |
| Gmail | `gmail.compose` | **Restricted** |
| Gmail | `gmail.modify` | **Restricted** (does *not* permit permanent delete, bypassing trash) |
| Gmail | `gmail.insert` | **Restricted** |
| Gmail | `gmail.metadata` | **Restricted** |
| Gmail | `gmail.settings.basic` / `gmail.settings.sharing` | **Restricted** |
| Gmail | `https://mail.google.com/` (full access, incl. permanent delete) | **Restricted** |
| Calendar | `calendar`, `calendar.events` | **Sensitive** (per Google's own worked example) |
| Calendar | `calendar.readonly`, `calendar.events.readonly` | Treated as sensitive-tier by the same logic (read access to private event content) |
| Sheets | `spreadsheets`, `spreadsheets.readonly` | **Sensitive** |
| Docs | `documents`, `documents.readonly` | **Sensitive** |
| Drive | `drive` (full), `drive.readonly` | **Restricted** |
| Drive | `drive.metadata`, `drive.metadata.readonly`, `drive.activity`, `drive.activity.readonly` | **Restricted** |
| Drive | `drive.apps.readonly` | **Sensitive** |
| Drive | `drive.file` | **Non-sensitive** (per-file access — the app only ever sees files the user explicitly opened/created with it or picked via the file picker) |
| Drive | `drive.appdata` | Non-sensitive |

Sources for the table:
- [Choose Gmail API scopes](https://developers.google.com/workspace/gmail/api/auth/scopes) (explicit three-tier breakdown)
- [Choose Google Sheets API scopes](https://developers.google.com/workspace/sheets/api/scopes)
- [Choose Google Docs API scopes](https://developers.google.com/workspace/docs/api/auth)
- [Choose Google Drive API scopes](https://developers.google.com/workspace/drive/api/guides/api-specific-auth)
- [Choose Google Calendar API scopes](https://developers.google.com/workspace/calendar/api/auth) + [Sensitive scope verification examples](https://developers.google.com/identity/protocols/oauth2/production-readiness/sensitive-scope-verification)

**Practical takeaway for our tool:** requesting the full Calendar + Gmail +
Docs + Sheets + Drive scope set as specced (`gmail.compose`, `gmail.readonly`,
`gmail.modify`, `drive`, `calendar`, `calendar.events`, etc.) puts the app
firmly in **restricted-scope** territory because of Gmail's
`readonly`/`compose`/`modify` and Drive's full `drive` scope. That means:
before public/production use, Google verification **and** an annual CASA
assessment are required if the data ever touches a server you control (which
is exactly the hosted shape). Swapping `drive` for `drive.file` removes Drive
from the restricted bucket entirely (non-sensitive, no verification) at the
cost of losing "see all my files" — the tool would only see files the user
explicitly opens or picks with it. There's no equivalent narrow-scope escape
hatch for Gmail read/compose access; any meaningful Gmail read or draft
capability is restricted-tier by design.

### Limits while unverified (Testing publishing status)

This is the number that determines whether a hackathon demo works for judges
without going through verification:

- A project in **Testing** publishing status is capped at **100 test users**,
  explicitly added by email in the OAuth consent screen's Audience/Test
  users section.
  - [Manage App Audience](https://support.google.com/cloud/answer/15549945?hl=en)
- **Refresh tokens issued to test users expire after 7 days** from the time
  of consent (not 6 months/indefinite as in production). If your OAuth
  client requested offline access and got a refresh token, that token also
  dies after 7 days — users must re-consent weekly.
  - [Manage App Audience](https://support.google.com/cloud/answer/15549945?hl=en)
- Testers also see an interstitial "Google hasn't verified this app"
  warning screen with a click-through to proceed, which is often what
  hackathon judges will encounter and need to click past.
- **Exceptions that avoid needing verification at all:** personal use,
  dev/test/staging environments, service-owned data only, internal
  organizational use, and domain-wide installs (restricted scopes still
  need *some* app verification even for domain-wide install, per Google's
  restricted-scope doc) — see the exceptions list on the restricted-scope
  page.
  - [Restricted scope verification — exceptions](https://developers.google.com/identity/protocols/oauth2/production-readiness/restricted-scope-verification)

**For a hackathon demo specifically:** add every judge's Google account as a
test user (up to 100), keep the project in Testing status, and warn them
they'll see the unverified-app tester warning and that their session/refresh
token is only good for 7 days. Also warn them that **judges using a
corporate/managed Google Workspace account may be blocked outright**, even
after being added as a test user: Workspace admins can restrict which
third-party or unverified apps are allowed to access org data at all, via
Admin console → Security → API controls / app access control — a setting
entirely outside your project's control. **Personal `@gmail.com` accounts
are the safe path for a demo**; ask judges on a managed work account to test
with a personal account instead if they hit an access-blocked error.
- [OAuth App Verification Help Center — admin app access controls](https://support.google.com/cloud/answer/13463073?hl=en)

If the org is Google Workspace and both you and the judges are in the
*same* Workspace domain, setting the consent screen's **user type to
Internal** instead removes the external test-user cap and the unverified-app
warning — but Internal apps are only grantable by accounts inside that one
Workspace domain, so this only helps if judges share your org's Workspace
domain, not for a general public hackathon audience.

---

## 3. Quota and billing attribution

### It's free, but quota'd per Cloud project

Every Workspace API (Gmail, Calendar, Docs, Sheets, Drive) is currently
**free for standard use**, gated by per-minute and per-day quotas tied to a
Google Cloud project — not to the end user's Google account.

- Calendar API: 10,000 requests/min per project; 600 requests/min per
  user per project.
  - [Calendar API usage limits](https://developers.google.com/workspace/calendar/api/guides/quota)
- Gmail API: 1,200,000 quota units/min per project; 6,000 quota units/min
  per user per project; 80,000,000 quota units/day per project before
  charges would apply. (`send`/`draft.send` = 100 units; simple `get` calls
  = 1 unit; batch delete/modify = 50 units; hard cap of 500 recipients per
  message.)
  - [Gmail API usage limits](https://developers.google.com/workspace/gmail/api/reference/quota)
- Docs API: also free for standard use, quota'd similarly per project.
  - [Docs API usage limits](https://developers.google.com/workspace/docs/api/limits)

**Google has announced that exceeding these free quota thresholds will
start incurring charges to the Cloud project's billing account later in
2026**, with at least 90 days' advance notice before that takes effect, and
projects created before May 1, 2026 keep grandfathered limits for a
transition window. This is a real cost-model consideration for whoever's
project absorbs the quota — see below.
- (Stated identically across the Calendar/Gmail/Docs quota pages linked above.)

### Which project absorbs the quota — this is the crux of "who pays"

Every Google API call needs a **quota project**: the Cloud project whose
quota bucket gets decremented and, per the 2026 billing change, whose
billing account eventually gets charged. How the quota project is
determined depends on the credential type:

- **API keys / service accounts**: the quota project is implicit — it's the
  project that owns the key or service account.
- **A user's OAuth access token**, called against a Google API library or
  REST endpoint **without an explicit quota project**, generally falls back
  to attribution rules that can fail closed: "If none of the previous checks
  yield a quota project, the request fails."
  - [Set the quota project — Google Cloud docs](https://docs.cloud.google.com/docs/quotas/set-quota-project)

This matters directly for our two shapes:

- **Local shape**: the tool runs the OAuth flow itself, using an OAuth
  client ID that belongs to *some* GCP project — either ours (bundled with
  the tool) or the user's own (bring-your-own-client, section 4). If we ship
  our own OAuth client ID hardcoded into the tool, **every user's API calls
  by default draw down our project's shared quota pool**, and once free-tier
  overage billing lands in 2026, they'd draw down *our* billing account too
  — the opposite of "the person installing it should pay for their own
  usage." This is the reason to push users toward bringing their own OAuth
  client (section 4): the OAuth client's owning project becomes the natural
  quota project, so their usage is billed/quota'd against their own project,
  not ours.

- **Hosted shape**: the server receives a bearer access token per request.
  If that token was minted from a *user-supplied* OAuth client (their own
  GCP project), the natural quota project is theirs; but a bearer token by
  itself doesn't automatically tell a REST call which project to bill —
  Google's REST/RPC calling convention lets *any* caller in possession of a
  valid access token attach the **`x-goog-user-project`** HTTP header to a
  request to explicitly designate which Cloud project should absorb
  quota/billing for that call, decoupling "whose access token this is" from
  "whose project pays."
  - [Set the quota project / `x-goog-user-project` header — Google Cloud docs](https://docs.cloud.google.com/docs/quotas/set-quota-project)

### The `x-goog-user-project` header and the IAM permission it requires

- Set the header to a project ID: `x-goog-user-project: <PROJECT_ID>`.
- The **caller's identity** (the OAuth principal — i.e., the end user whose
  access token is being used, or a service account, depending on the auth
  flow) must hold the **`serviceusage.services.use`** IAM permission on that
  target project. That permission comes bundled in the predefined
  **Service Usage Consumer** role (`roles/serviceusage.serviceUsageConsumer`).
  - [Set the quota project — Google Cloud docs](https://docs.cloud.google.com/docs/quotas/set-quota-project)
- If the header is present but the caller lacks that permission on the named
  project, the request is rejected. If the header is omitted entirely,
  Google falls through a chain of implicit signals (API key's project,
  ADC's associated project, etc.); if none resolve, **the request fails
  outright** rather than silently picking an arbitrary project.
  - [Set the quota project — Google Cloud docs](https://docs.cloud.google.com/docs/quotas/set-quota-project)

**Design implication:** for the hosted shape to correctly bill the calling
user's own GCP project rather than ours, we'd need the user to (a) have a
GCP project, (b) grant `serviceusage.services.use` on it to whatever
identity is making the call (their own OAuth-authenticated identity
typically already has this on projects they own), and (c) have our server
attach `x-goog-user-project: <their-project-id>` on every Workspace API
call. That in turn means we need to *collect* their project ID as part of
onboarding, alongside their OAuth client credentials — see section 4.

### If a business brings their own OAuth client from their own GCP project

If the OAuth client ID/secret used to obtain the token belongs to the
customer's own GCP project (rather than ours), things get simpler:

- The OAuth token is now inherently associated with *their* project as far
  as Google's default/fallback quota-project resolution is concerned in many
  flows, and their org's Workspace admin — not us — controls whether that
  project's OAuth client is allowed to touch Workspace data at all (via
  domain-wide app allow/block lists in the Admin console, a Workspace-edition/
  admin-policy-dependent control we don't have visibility into or control
  over from outside their org).
- Their existing GCP billing account is what would eventually be charged
  under the 2026 overage-billing change — cleanly satisfying "they pay for
  their own usage."
- It also sidesteps the verification bottleneck for **internal-only**
  Workspace deployments: if the consent screen's user type is set to
  **Internal**, only accounts inside that one Workspace org can authorize
  it, and sensitive/restricted-scope verification is not required for
  internal apps. The 100-user cap and 7-day refresh-token expiry are
  documented specifically as properties of *external* apps in Testing
  status; since Internal is a separate user-type track from
  Testing/External entirely, it's reasonable to infer — though Google
  doesn't state this as a single explicit sentence — that Internal apps
  aren't subject to that external-Testing cap and expiry. Confirm this
  against current console behavior before relying on it. Either way this
  only works for a business self-hosting the client for its own employees,
  not for redistributing to arbitrary external users.
  - [Restricted scope verification — exceptions (internal use)](https://developers.google.com/identity/protocols/oauth2/production-readiness/restricted-scope-verification)
  - [Configure the OAuth consent screen — user type](https://developers.google.com/workspace/guides/configure-oauth-consent)
  - [Manage App Audience — Testing status limits (100 users, 7-day expiry, framed for external apps)](https://support.google.com/cloud/answer/15549945?hl=en)

This is why "bring your own OAuth client" is the right default for both
individual users (local shape) and businesses (either shape): it aligns
scope-verification burden, quota, and eventual billing with whoever actually
owns the GCP project, instead of concentrating all of it — and the
verification/CASA liability — on us.

---

## 4. Bring-your-own OAuth client — README-ready setup steps

These steps assume a non-expert user with no existing GCP project, setting
up credentials for a **local, desktop-style OAuth flow** (loopback redirect,
`urn:ietf:wg:oauth:2.0:oob`-successor style — Google's current guidance is a
"Desktop app" OAuth client type using a loopback IP redirect). For a hosted
deployment, swap step 6 for a "Web application" client type with a real
HTTPS redirect URI instead.

1. **Create a Google Cloud project.** Go to
   [console.cloud.google.com](https://console.cloud.google.com/), click the
   project picker at the top, then **New Project**. Give it any name (e.g.
   "my-workspace-tool"), leave the organization/location defaults, and
   click **Create**. Wait for the notification that the project was
   created, then select it from the project picker.

2. **Enable the Workspace APIs you'll use.** In the left nav, go to
   **APIs & Services → Library**. Search for and click **Enable** on each
   API you need: *Google Calendar API*, *Gmail API*, *Google Docs API*,
   *Google Sheets API*, *Google Drive API*. (Only enable the ones your tool
   actually calls — this list should match the OAuth scopes you'll request
   in step 5.)

3. **Configure the OAuth consent screen.** Go to
   **APIs & Services → OAuth consent screen** (Google may label this
   **Google Auth Platform → Branding/Audience/Data Access** depending on
   console version). Choose **External** as the user type (unless every
   user is inside your own Google Workspace org, in which case choose
   **Internal**). Fill in:
   - App name (shown to users on the consent screen)
   - User support email
   - Developer contact email
   Click through the wizard and save.
   - [Configure the OAuth consent screen and choose scopes](https://developers.google.com/workspace/guides/configure-oauth-consent)

4. **Add test users (skip if Internal).** Still in the consent screen
   config, go to the **Audience** (or **Test users**) tab and add the
   Google account email(s) that will use the tool — yourself, teammates, or
   demo judges — up to 100 accounts. Anyone not on this list will be unable
   to authorize the app while it's in Testing status.
   - [Manage App Audience](https://support.google.com/cloud/answer/15549945?hl=en)

5. **Add the OAuth scopes.** In the consent screen's **Data Access** (or
   **Scopes**) section, click **Add or Remove Scopes** and check the
   specific scopes your tool needs (e.g. `.../auth/calendar`,
   `.../auth/gmail.modify`, `.../auth/documents`, `.../auth/spreadsheets`,
   `.../auth/drive`). Prefer the narrowest scope that does the job — e.g.
   `drive.file` instead of `drive` if you don't need to see the user's
   entire Drive — since narrower scopes may avoid the restricted-scope
   verification tier entirely (see section 2).

6. **Create the OAuth client ID.** Go to
   **APIs & Services → Credentials → Create Credentials → OAuth client ID**.
   - For a tool that runs locally on the user's machine: choose
     **Application type: Desktop app**, give it a name, click **Create**.
   - For a hosted deployment: choose **Application type: Web application**,
     add your server's callback URL under **Authorized redirect URIs**
     (e.g. `https://yourapp.example.com/oauth/callback`), click **Create**.
   - [Setting up OAuth 2.0](https://support.google.com/googleapi/answer/6158849?hl=en)
   - [Create credentials — Google Workspace guide](https://developers.google.com/workspace/guides/create-credentials)

7. **Save the client ID and secret.** After creation, Google shows the
   Client ID and Client Secret. Note the trust model differs by client
   type: a **Web application** client (used by the hosted server, with a
   confidential backend) genuinely relies on the secret being kept private
   server-side. A **Desktop app** (or other installed/native) client is a
   *public* client — Google issues a secret for it, but since it ships
   inside code that runs on the user's own machine, it can't actually be
   kept confidential and Google does not treat it as one; native-client
   flows should rely on PKCE rather than secret confidentiality for
   security. Either way, download the credentials JSON, or copy the values
   into the tool's configuration (e.g. environment variables
   `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET`). **Never commit these to a
   public repository** — Google's own policy: "Treat your OAuth client
   credentials with extreme care, as they allow anyone who has them to use
   your app's identity."
   - [OAuth 2.0 Policies](https://developers.google.com/identity/protocols/oauth2/policies)

8. **(Optional, for cost attribution) Grant yourself Service Usage Consumer
   on the project.** If the tool sends the `x-goog-user-project` header so
   API usage bills against this project, make sure the account
   authenticating has the `serviceusage.services.use` permission on it —
   project owners have this by default, so no action is usually needed if
   you're the project creator.
   - [Set the quota project](https://docs.cloud.google.com/docs/quotas/set-quota-project)

9. **Run the tool and authorize.** Start the tool; it opens a browser to
   Google's consent screen. Because your project is in Testing status and
   you added yourself as a test user, you'll see a tester warning
   ("Google hasn't verified this app... you've been given access as a
   tester") — click **Continue** to proceed (this is expected and safe for
   an app you configured yourself). This is a simpler screen than the
   "Advanced → Go to [app] (unsafe)" bypass shown to *non-test-user*
   visitors of an unverified app in production; test users of a
   Testing-status app don't need that bypass. Approve the scopes you want
   to grant.

10. **(When ready for wider use) Submit for verification.** If you plan to
    let more than 100 users, or users outside your own Workspace org, use
    the tool long-term, submit the OAuth consent screen for Google's
    verification (**OAuth consent screen → Publishing status → Publish
    app**, then follow the verification prompts). Expect 3–5 business days
    for sensitive scopes; budget for a CASA security assessment (recurring
    annually) if any restricted scope (e.g. `gmail.readonly`, `drive`) is
    requested and data touches a server.
    - [Sensitive scope verification](https://developers.google.com/identity/protocols/oauth2/production-readiness/sensitive-scope-verification)
    - [Restricted scope verification](https://developers.google.com/identity/protocols/oauth2/production-readiness/restricted-scope-verification)

---

## 5. Incremental authorization

Yes — Google's OAuth 2.0 implementation supports **incremental
authorization**: you can request a narrow scope set up front, and later
request additional scopes without discarding the user's existing grant,
as long as you pass **`include_granted_scopes=true`** on the new
authorization request.

- Mechanism: send a new `/o/oauth2/v2/auth` request with the *additional*
  scope(s) you now need, plus `include_granted_scopes=true`. If the user
  approves, the authorization code you get back — and the token you
  exchange it for — represents the **union** of the previously granted
  scopes and the newly granted ones, without the user having to
  re-approve everything from scratch.
  - [Using OAuth 2.0 for Web Server Applications — incremental authorization](https://developers.google.com/identity/protocols/oauth2/web-server)
  - [Using OAuth 2.0 to Access Google APIs](https://developers.google.com/identity/protocols/oauth2)
- Caveat/best practice from Google: request scopes contextually, at the
  point you actually need them, rather than front-loading every scope your
  app might ever use — this both improves consent-screen approval rates and
  keeps each incremental grant screen focused on the specific tool the user
  just tried to use.
- A practical wrinkle worth flagging (raised by third-party integrators,
  not disputed by Google's docs): **omitting `include_granted_scopes`** on a
  later request, or the underlying refresh-token/session-management
  behavior on some platforms, can silently narrow the token back down to
  only the newest request's scopes instead of merging — so always pass
  `include_granted_scopes=true` explicitly and verify the returned `scope`
  string is the union you expect rather than assuming it.
  - [Google OAuth's Incremental Authorization is Useless (practitioner critique, useful as a caution — not an official source)](https://www.gmass.co/blog/oauth-incremental-authorization-is-useless/)

For our MCP server: this is exactly the mechanism to use for "grant Calendar
now, add Gmail later without re-doing everything" — request each Workspace
API's scope only when the user first invokes a tool that needs it, always
with `include_granted_scopes=true`, and re-derive the MCP tool list from the
updated `scope` string (or a fresh tokeninfo call) after each incremental
grant.

---

## 6. Security note: the hosted shape receiving user access tokens

The hosted shape — a server that accepts a bearer access token per request
instead of running its own OAuth flow — has materially different risk than
the local shape, and Google's own developer policy speaks directly to it.

**Risks:**
- **The server becomes a high-value target.** Any bearer access token it
  handles is, for its lifetime, equivalent to the user's own Workspace
  credentials for whatever scopes it carries — read/send Gmail, read/write
  Calendar, full Drive access, etc. A breach of the hosted server leaks
  live capability over every connected user's Workspace data, not just our
  own data.
- **Tokens in transit and at rest.** If the server logs requests, error
  traces, or persists tokens for reuse across requests (e.g. to avoid
  re-authenticating on every call), those tokens are now data-at-rest that
  must be protected to the same standard as passwords.
- **Scope creep via caching.** If the server caches "what scopes does this
  bearer token have" from an earlier tokeninfo call and doesn't recheck, a
  user who revokes access (or whose org admin revokes the app) may still
  appear authorized to the cached tool list until the cache expires.
- **Third-party target for restricted-scope rules specifically**: Google's
  restricted-scope policy explicitly triggers the security-assessment
  requirement when restricted-scope data is "stored or transmitted on
  servers" — which the hosted shape does by definition, whereas a purely
  local tool that never sends tokens off the user's own machine can often
  avoid that trigger.
  - [Restricted scope verification](https://developers.google.com/identity/protocols/oauth2/production-readiness/restricted-scope-verification)

**What Google's policy requires:**
- **Never transmit tokens in plaintext**, and **always store tokens
  encrypted at rest** — direct quote from Google's OAuth 2.0 Policies: "Never
  transmit tokens in plaintext, and always store encrypted tokens at rest to
  provide an extra layer of protection in the event of a data breach."
  - [OAuth 2.0 Policies](https://developers.google.com/identity/protocols/oauth2/policies)
- **Revoke and delete tokens once no longer needed**: "Revoke tokens when
  you no longer need access to a user's account or when your app no longer
  needs access to permissions that a user previously granted. After the
  tokens are revoked, delete them permanently from your application or
  system."
  - [OAuth 2.0 Policies](https://developers.google.com/identity/protocols/oauth2/policies)
- **Limited Use**: under the Google API Services User Data Policy, any
  Google user data (including what's fetched using these tokens) may only
  be used "to provide or improve user-facing features that are prominent in
  the requesting application's user interface," must match what the app's
  published privacy policy discloses, and specific transfers (e.g. to
  advertising platforms, data brokers, for ad personalization) are flatly
  prohibited except under narrow consent/security/legal-compliance carve-outs.
  - [Google API Services User Data Policy](https://developers.google.com/terms/api-services-user-data-policy)
- **General security posture**: the policy requires "reasonable and
  appropriate steps to protect all applications or systems that make use of
  Google API Services... against unauthorized or unlawful access," and
  Google's guidance points to ISO/IEC 27001-style practices and OWASP Top 10
  hygiene as the reference bar — this is effectively what a CASA assessment
  checks for restricted scopes.
  - [Google API Services User Data Policy](https://developers.google.com/terms/api-services-user-data-policy)
  - [Restricted scope verification](https://developers.google.com/identity/protocols/oauth2/production-readiness/restricted-scope-verification)
- **Client credential hygiene**: separately from user tokens, the OAuth
  client secret itself must never be committed to a public repo and should
  be held in a secrets manager — relevant if the hosted server also holds
  the OAuth client secret to perform its own token exchanges/refreshes.
  - [OAuth 2.0 Policies](https://developers.google.com/identity/protocols/oauth2/policies)

**Practical recommendation:** for the hosted shape, treat every inbound
bearer token as short-lived and untrusted-until-checked: verify it against
`tokeninfo` (or equivalently, let API calls fail on 401/403 and treat that as
"re-authenticate") rather than trusting a client-asserted scope list; avoid
persisting tokens beyond the single request/session where possible, and if
you must persist them (e.g. long-lived MCP connections), encrypt at rest and
give the user an explicit, easy revoke/delete path consistent with the
"revoke and delete permanently" requirement above. Given the restricted-scope
CASA trigger is specifically "stored or transmitted on servers," minimizing
what the hosted server persists is both a security good idea and a
compliance-scope reducer.

---

## Summary table: which shape avoids which liability

| Concern | Local shape (own device, own client) | Local shape (our bundled client) | Hosted shape (BYO client) | Hosted shape (our client) |
|---|---|---|---|---|
| Who absorbs Workspace API quota/2026 billing | User's own GCP project | Our GCP project | User's GCP project (needs `x-goog-user-project`) | Our GCP project |
| Verification/CASA liability owner | User (only if they publish beyond Testing/Internal) | Us | User | Us |
| Token-at-rest exposure surface | User's own machine only | User's own machine only | Our server (must encrypt, must revoke) | Our server (must encrypt, must revoke) |
| 100-user / 7-day-refresh cap applies unless... | User verifies their own app, or uses Internal within their org | We verify our app for everyone | Their org verifies/sets Internal | We verify our app for everyone |

This strongly favors **bring-your-own-OAuth-client as the default for both
shapes**, with our own bundled client (if offered at all) reserved for a
time-boxed, clearly-labeled demo/trial path — consistent with "the person
installing it should pay for their own usage."
