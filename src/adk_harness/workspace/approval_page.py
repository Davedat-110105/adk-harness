"""A local page where a person approves one change, outside the model's reach.

The client hands the person a link and the answer travels from their browser
straight back to this process. The model sees a link and, later, an outcome; it
never sees the question and cannot answer it.

Each pending change gets one unguessable path, bound to the loopback address,
and that path stops working the moment it is answered.
"""

from __future__ import annotations

import contextlib
import json
import os
import secrets
import tempfile
import threading
from collections.abc import Mapping
from dataclasses import dataclass, field
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

# How long the Stop hook holds a turn open while somebody decides.
HOOK_WAIT_SECONDS = float(os.environ.get("ADK_HARNESS_HOOK_WAIT", "120"))

__all__ = ["ENDPOINT_FILE", "ApprovalServer", "PendingApproval"]

# Where the Stop hook looks for the running harness.
ENDPOINT_FILE = Path(tempfile.gettempdir()) / "adk-harness-approval-endpoint.json"

# Rendered inline in the client's own chat. Tailwind is the one allowlisted
# stylesheet there, and the theme variables come from the host.
_WIDGET = """<!DOCTYPE html>
<html><head>
<script src="https://www.gstatic.com/antigravity/web/dev/tailwindcss.min.js"></script>
</head>
<body class="bg-transparent text-[var(--foreground)] antialiased p-3">
<div class="bg-[var(--card)] border border-[var(--border)] rounded-lg px-4 py-3.5">
  <div class="flex items-baseline justify-between gap-3">
    <h2 class="text-[14px] font-semibold">Approve this change?</h2>
    <span id="state" class="text-[12px] text-[var(--muted-foreground)]">nothing has run</span>
  </div>

  <p class="text-[12px] font-mono text-[var(--muted-foreground)] mt-0.5">{operation}</p>

  <dl class="mt-2.5 text-[12px] grid grid-cols-[auto_1fr] gap-x-3 gap-y-1">
    {rows}
  </dl>

  <div class="mt-3.5 flex items-center gap-2">
    <div id="buttons" class="flex gap-2">
      <button onclick="answer('yes')"
        class="text-[12px] font-medium px-3 py-1.5 rounded-md
        bg-[var(--primary)] text-[var(--primary-foreground)]">Approve</button>
      <button onclick="answer('no')"
        class="text-[12px] font-medium px-3 py-1.5 rounded-md
        bg-[var(--secondary)] text-[var(--secondary-foreground)]">Decline</button>
    </div>
    <span class="ml-auto text-[12px] font-mono text-[var(--muted-foreground)]"
      title="{change_hash}">{short_hash}</span>
  </div>
</div>
<script>
var base = '{base}';

function settle(approved) {{
  var buttons = document.getElementById('buttons');
  if (buttons) {{ buttons.remove(); }}
  document.getElementById('state').textContent = approved ? 'approved' : 'declined, nothing ran';
}}

function answer(choice) {{
  document.getElementById('state').textContent = 'sending...';
  fetch(base + '/' + choice, {{method: 'POST'}})
    .then(function () {{ settle(choice === 'yes'); }})
    .catch(function (error) {{
      document.getElementById('state').textContent = 'could not reach the harness';
    }});
}}

// The frame reloads whenever the conversation updates, so read the decision
// back rather than trusting anything this page remembers.
fetch(base + '/status')
  .then(function (r) {{ return r.json(); }})
  .then(function (d) {{ if (d.answered) {{ settle(d.approved); }} }})
  .catch(function () {{}});
</script>
</body></html>
"""

_ROW = ('<dt class="text-[var(--muted-foreground)]">{key}</dt>'
        '<dd class="font-mono break-all">{value}</dd>')

_PAGE = """<!doctype html>
<html><head><meta charset="utf-8"><title>Approve this change</title>
<style>
 body{{font:15px -apple-system,system-ui,sans-serif;margin:0;padding:2.5rem;
      background:#0f1115;color:#e6e8ee}}
 main{{max-width:34rem;margin:0 auto}}
 h1{{font-size:1.1rem;margin:0 0 1.25rem}}
 dl{{display:grid;grid-template-columns:9rem 1fr;gap:.5rem 1rem;margin:0 0 1.5rem}}
 dt{{color:#9aa3b2}} dd{{margin:0;word-break:break-word}}
 code{{font-size:.85em;color:#c9d1e4}}
 form{{display:inline}}
 button{{font:inherit;padding:.6rem 1.1rem;border-radius:.4rem;border:0;cursor:pointer}}
 .yes{{background:#2f6f4f;color:#fff;margin-right:.5rem}}
 .no{{background:#2a2e38;color:#e6e8ee}}
 p.done{{color:#9aa3b2}}
</style></head>
<body><main>
<h1>{heading}</h1>
<dl>
 <dt>Operation</dt><dd><code>{operation}</code></dd>
 <dt>Details</dt><dd><code>{arguments}</code></dd>
 <dt>Change hash</dt><dd><code>{change_hash}</code></dd>
</dl>
{body}
</main></body></html>
"""

_CHOICES = """<form method="post" action="{path}/yes"><button class="yes">Approve</button></form>
<form method="post" action="{path}/no"><button class="no">Decline</button></form>"""


def _rows(arguments: Mapping[str, Any], limit: int = 5) -> list[str]:
    """Flatten the payload into a few readable lines.

    An inline card must not scroll inside itself, so long payloads are
    summarised and the full text stays on the approval page.
    """
    flat: list[tuple[str, str]] = []

    def walk(value: Any, prefix: str) -> None:
        if isinstance(value, Mapping):
            for key, item in value.items():
                walk(item, f"{prefix}.{key}" if prefix else str(key))
        else:
            flat.append((prefix, str(value)))

    walk(dict(arguments), "")
    rows = [
        _ROW.format(key=escape(key), value=escape(value[:80]))
        for key, value in flat[:limit]
    ]
    if len(flat) > limit:
        rows.append(_ROW.format(key="", value=f"and {len(flat) - limit} more"))
    return rows


@dataclass
class PendingApproval:
    """One change waiting for a person."""

    token: str
    operation: str
    arguments: Mapping[str, Any]
    change_hash: str
    answered: threading.Event = field(default_factory=threading.Event)
    approved: bool = False

    def resolve(self, approved: bool) -> None:
        self.approved = approved
        self.answered.set()

    def wait(self, timeout: float) -> bool | None:
        """Return the answer, or None when nobody answered in time."""
        if not self.answered.wait(timeout):
            return None
        return self.approved


class ApprovalServer:
    """Serve one approval page per pending change, on the loopback address."""

    def __init__(self) -> None:
        self._pending: dict[str, PendingApproval] = {}
        self._granted: dict[str, PendingApproval] = {}
        self._answered: dict[str, bool] = {}
        self._httpd: ThreadingHTTPServer | None = None
        self._lock = threading.Lock()

    @property
    def port(self) -> int:
        self._start()
        assert self._httpd is not None
        return self._httpd.server_address[1]

    def _start(self) -> None:
        with self._lock:
            if self._httpd is not None:
                return
            pending = self._pending
            granted = self._granted
            answered = self._answered

            class Handler(BaseHTTPRequestHandler):
                def log_message(self, format: str, *args: object) -> None:
                    """Keep the request line out of the server's output."""

                def _find(self) -> tuple[PendingApproval | None, str]:
                    parts = urlparse(self.path).path.strip("/").split("/")
                    if not parts or parts[0] != "approve":
                        return None, ""
                    token = parts[1] if len(parts) > 1 else ""
                    return pending.get(token), parts[2] if len(parts) > 2 else ""

                def _json(self, payload: dict[str, Any]) -> None:
                    body = json.dumps(payload).encode("utf-8")
                    self.send_response(200)
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(body)))
                    self.send_header("Cache-Control", "no-store")
                    self.end_headers()
                    self.wfile.write(body)

                def _send(self, html: str, status: int = 200) -> None:
                    body = html.encode("utf-8")
                    self.send_response(status)
                    # The card is rendered in the client's own frame.
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Content-Length", str(len(body)))
                    self.send_header("Cache-Control", "no-store")
                    self.end_headers()
                    self.wfile.write(body)

                def do_GET(self) -> None:
                    path = urlparse(self.path).path.strip("/")
                    if path == "waiting":
                        # The Stop hook asks whether anybody is mid-decision, and
                        # waits for the answer rather than ending the turn.
                        item = next(iter(list(pending.values())), None)
                        if item is None:
                            self._json({"waiting": False})
                            return
                        decided = item.wait(HOOK_WAIT_SECONDS)
                        self._json(
                            {
                                "waiting": True,
                                "answered": decided is not None,
                                "approved": bool(decided),
                                "operation": item.operation,
                            }
                        )
                        return
                    item, action = self._find()
                    if action == "status":
                        token = urlparse(self.path).path.strip("/").split("/")[1]
                        decided = answered.get(token)
                        self._json(
                            {"answered": decided is not None, "approved": bool(decided)}
                        )
                        return
                    if item is None:
                        self._send("<p>This request is no longer waiting.</p>", 404)
                        return
                    self._send(
                        _PAGE.format(
                            heading="Approve this change?",
                            operation=item.operation,
                            arguments=item.arguments,
                            change_hash=item.change_hash,
                            body=_CHOICES.format(path=f"/approve/{item.token}"),
                        )
                    )

                def do_POST(self) -> None:
                    item, answer = self._find()
                    if item is None or answer not in ("yes", "no"):
                        self._send("<p>This request is no longer waiting.</p>", 404)
                        return
                    item.resolve(answer == "yes")
                    pending.pop(item.token, None)
                    granted[item.change_hash] = item
                    answered[item.token] = item.approved
                    self._send(
                        _PAGE.format(
                            heading="Approved" if item.approved else "Declined",
                            operation=item.operation,
                            arguments=item.arguments,
                            change_hash=item.change_hash,
                            body="<p class='done'>You can close this tab.</p>",
                        )
                    )

            self._httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
            thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
            thread.start()
            with contextlib.suppress(OSError):
                ENDPOINT_FILE.write_text(
                    json.dumps({"base": f"http://127.0.0.1:{self._httpd.server_address[1]}"}),
                    encoding="utf-8",
                )

    def widget(self, item: PendingApproval) -> str:
        """Write the inline card for one pending change and return its path."""
        base = f"http://127.0.0.1:{self.port}/approve/{item.token}"
        html = _WIDGET.format(
            operation=escape(item.operation),
            rows="".join(_rows(item.arguments)),
            change_hash=escape(item.change_hash),
            short_hash=escape(item.change_hash[:12]),
            base=base,
        )
        path = Path(tempfile.gettempdir()) / f"adk-harness-approve-{item.token}.html"
        path.write_text(html, encoding="utf-8")
        return str(path)

    def offer(
        self, *, operation: str, arguments: Mapping[str, Any], change_hash: str
    ) -> tuple[PendingApproval, str]:
        """Register a pending change and return it with the link to answer it."""
        self._start()
        item = PendingApproval(
            token=secrets.token_urlsafe(24),
            operation=operation,
            arguments=dict(arguments),
            change_hash=change_hash,
        )
        self._pending[item.token] = item
        return item, f"http://127.0.0.1:{self.port}/approve/{item.token}"

    def withdraw(self, item: PendingApproval) -> None:
        """Stop accepting an answer nobody gave in time."""
        self._pending.pop(item.token, None)

    def offer_for(
        self, *, operation: str, arguments: Mapping[str, Any], change_hash: str
    ) -> tuple[PendingApproval, str]:
        """Return the open link for this change, reusing one already waiting."""
        for item in self._pending.values():
            if item.change_hash == change_hash:
                return item, f"http://127.0.0.1:{self.port}/approve/{item.token}"
        return self.offer(operation=operation, arguments=arguments, change_hash=change_hash)

    def waiting_for(self, change_hash: str) -> PendingApproval | None:
        """Return the approval already on screen for this change, if any."""
        for item in self._pending.values():
            if item.change_hash == change_hash:
                return item
        return None

    def answer_for(self, change_hash: str) -> bool | None:
        """Return a decision already given for this exact change, once.

        Consuming it means a second identical call needs its own approval.
        """
        item = self._granted.pop(change_hash, None)
        return None if item is None else item.approved
