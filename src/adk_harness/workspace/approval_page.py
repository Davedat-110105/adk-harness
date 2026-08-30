"""A local page where a person approves one change, outside the model's reach.

The client hands the person a link and the answer travels from their browser
straight back to this process. The model sees a link and, later, an outcome; it
never sees the question and cannot answer it.

Each pending change gets one unguessable path, bound to the loopback address,
and that path stops working the moment it is answered.
"""

from __future__ import annotations

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

__all__ = ["ApprovalServer", "PendingApproval"]

# Rendered inline in the client's own chat. Tailwind is the one allowlisted
# stylesheet there, and the theme variables come from the host.
_WIDGET = """<!DOCTYPE html>
<html><head>
<script src="https://www.gstatic.com/antigravity/web/dev/tailwindcss.min.js"></script>
</head>
<body class="bg-transparent text-[var(--foreground)] antialiased p-4">
<div id="card" class="bg-[var(--card)] border border-[var(--border)] rounded-xl p-4">
  <h2 class="font-semibold">This change needs your approval</h2>
  <p class="text-[var(--muted-foreground)] text-sm mt-1">{operation}</p>
  <p class="text-[var(--muted-foreground)] text-xs mt-2 font-mono break-all">{arguments}</p>
  <p class="text-[var(--muted-foreground)] text-xs mt-1 font-mono break-all">{change_hash}</p>
  <div id="buttons" class="mt-4 flex gap-2">
    <button onclick="answer('yes')"
      class="px-3 py-1.5 rounded-md bg-[var(--primary)] text-[var(--primary-foreground)]">
      Approve</button>
    <button onclick="answer('no')"
      class="px-3 py-1.5 rounded-md bg-[var(--secondary)] text-[var(--secondary-foreground)]">
      Decline</button>
  </div>
  <p id="done" class="text-[var(--muted-foreground)] text-sm mt-3"></p>
</div>
<script>
function answer(choice) {{
  document.getElementById('buttons').remove();
  fetch('{base}/' + choice, {{method: 'POST'}})
    .then(() => {{
      document.getElementById('done').textContent =
        choice === 'yes' ? 'Approved. Tell the agent to continue.' : 'Declined. Nothing ran.';
    }})
    .catch(e => {{
      document.getElementById('done').textContent = 'Could not reach the harness: ' + e;
    }});
}}
</script>
</body></html>
"""

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

            class Handler(BaseHTTPRequestHandler):
                def log_message(self, format: str, *args: object) -> None:
                    """Keep the request line out of the server's output."""

                def _find(self) -> tuple[PendingApproval | None, str]:
                    parts = urlparse(self.path).path.strip("/").split("/")
                    if not parts or parts[0] != "approve":
                        return None, ""
                    token = parts[1] if len(parts) > 1 else ""
                    return pending.get(token), parts[2] if len(parts) > 2 else ""

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
                    item, _ = self._find()
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

    def widget(self, item: PendingApproval) -> str:
        """Write the inline card for one pending change and return its path."""
        base = f"http://127.0.0.1:{self.port}/approve/{item.token}"
        html = _WIDGET.format(
            operation=escape(item.operation),
            arguments=escape(str(item.arguments)),
            change_hash=escape(item.change_hash),
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

    def answer_for(self, change_hash: str) -> bool | None:
        """Return a decision already given for this exact change, once.

        Consuming it means a second identical call needs its own approval.
        """
        item = self._granted.pop(change_hash, None)
        return None if item is None else item.approved
