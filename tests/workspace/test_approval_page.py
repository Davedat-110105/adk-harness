from __future__ import annotations

import threading
import urllib.request
from typing import Any

from adk_harness.workspace.approval_page import ApprovalServer


def _get(url: str) -> tuple[int, str]:
    try:
        with urllib.request.urlopen(url, timeout=5) as response:
            return response.status, response.read().decode()
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode()


def _post(url: str) -> tuple[int, str]:
    request = urllib.request.Request(url, data=b"", method="POST")
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, response.read().decode()
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode()


def test_the_page_shows_the_change_and_takes_an_answer() -> None:
    server = ApprovalServer()
    pending, url = server.offer(
        operation="calendar.events.insert",
        arguments={"calendarId": "primary"},
        change_hash="abc123",
    )

    status, page = _get(url)
    assert status == 200
    assert "calendar.events.insert" in page
    assert "abc123" in page
    assert "Approve" in page and "Decline" in page

    answered: list[Any] = []
    waiter = threading.Thread(target=lambda: answered.append(pending.wait(5)))
    waiter.start()
    assert _post(f"{url}/yes")[0] == 200
    waiter.join(6)

    assert answered == [True]


def test_declining_answers_false() -> None:
    server = ApprovalServer()
    pending, url = server.offer(operation="calendar.events.delete", arguments={}, change_hash="d")

    assert _post(f"{url}/no")[0] == 200
    assert pending.wait(5) is False


def test_an_answered_link_stops_working() -> None:
    """One approval, one use. A stale tab cannot approve a later change."""
    server = ApprovalServer()
    _pending, url = server.offer(operation="calendar.events.patch", arguments={}, change_hash="p")

    assert _post(f"{url}/yes")[0] == 200
    assert _get(url)[0] == 404
    assert _post(f"{url}/yes")[0] == 404


def test_an_unknown_token_is_refused() -> None:
    server = ApprovalServer()
    server.offer(operation="calendar.events.get", arguments={}, change_hash="g")

    assert _get(f"http://127.0.0.1:{server.port}/approve/not-a-real-token")[0] == 404


def test_nobody_answering_returns_nothing() -> None:
    server = ApprovalServer()
    pending, _url = server.offer(operation="calendar.events.move", arguments={}, change_hash="m")

    assert pending.wait(0.2) is None


def test_the_page_listens_only_on_the_loopback_address() -> None:
    server = ApprovalServer()
    server.offer(operation="calendar.events.list", arguments={}, change_hash="l")

    assert server._httpd is not None
    assert server._httpd.server_address[0] == "127.0.0.1"


def test_the_inline_card_posts_back_to_this_server() -> None:
    """The card renders in the client's chat and answers over the loopback."""
    from pathlib import Path

    server = ApprovalServer()
    pending, url = server.offer(
        operation="calendar.events.insert",
        arguments={"calendarId": "primary"},
        change_hash="feedface",
    )

    html = Path(server.widget(pending)).read_text(encoding="utf-8")

    assert "calendar.events.insert" in html
    assert "feedface" in html
    assert f"{url}/' + choice" in html
    assert "Approve" in html and "Decline" in html
    assert "gstatic.com/antigravity" in html


def test_the_card_escapes_what_it_shows() -> None:
    """Arguments come from a model; they are shown, never executed."""
    from pathlib import Path

    server = ApprovalServer()
    pending, _url = server.offer(
        operation="calendar.events.insert",
        arguments={"summary": "<script>alert(1)</script>"},
        change_hash="h",
    )

    html = Path(server.widget(pending)).read_text(encoding="utf-8")

    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html
