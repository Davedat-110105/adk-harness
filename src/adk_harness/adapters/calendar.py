"""Google Calendar REST API adapter."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Sequence
from typing import Any

from adk_harness.protocol import HarnessSpec, HarnessTurn

__all__ = ["CalendarHarness"]

_CALENDAR_SCOPE = "https://www.googleapis.com/auth/calendar.events"


def _event_body(prompt: str) -> dict[str, Any]:
    """Recover an event body from whatever the caller actually sent.

    A caller may pass clean JSON. An orchestrating model usually does not — it
    wraps the same JSON in a sentence. Parsing only a whole-string JSON document
    therefore worked in tests, where the prompt is written by hand, and failed
    against a real fleet, where the prompt is written by Gemini.

    So: try the whole string, then the first balanced object inside it, and only
    then fall back to treating the text as a summary.
    """
    try:
        parsed = json.loads(prompt)
    except json.JSONDecodeError:
        parsed = None
    if isinstance(parsed, dict):
        return parsed

    start = prompt.find("{")
    while start != -1:
        depth = 0
        for index in range(start, len(prompt)):
            if prompt[index] == "{":
                depth += 1
            elif prompt[index] == "}":
                depth -= 1
                if depth == 0:
                    try:
                        candidate = json.loads(prompt[start : index + 1])
                    except json.JSONDecodeError:
                        break
                    if isinstance(candidate, dict):
                        return candidate
                    break
        start = prompt.find("{", start + 1)

    return {"summary": prompt}


def _http_status(error: Exception) -> int | None:
    response = getattr(error, "resp", None)
    status = getattr(response, "status", None)
    if status is None:
        status = getattr(error, "status", None)
    return status if isinstance(status, int) else None


def _http_message(error: Exception) -> str:
    content = getattr(error, "content", None)
    if isinstance(content, bytes):
        content = content.decode(errors="replace")
    if isinstance(content, str):
        try:
            payload = json.loads(content)
        except json.JSONDecodeError:
            pass
        else:
            if isinstance(payload, dict):
                nested = payload.get("error")
                if isinstance(nested, dict) and nested.get("message"):
                    return str(nested["message"])
                if payload.get("message"):
                    return str(payload["message"])
    return str(error) or type(error).__name__


class CalendarHarness:
    """Create Google Calendar events through the REST API.

    `cwd` and `session_id` are ignored: the Calendar API has no working
    directory or resumable harness session. `dry_run` defaults to True because
    inserting an event is an externally visible mutation.
    """

    def __init__(self, *, calendar_id: str = "primary", dry_run: bool = True) -> None:
        self.calendar_id = calendar_id
        self.dry_run = dry_run
        self._service: Any = None
        # Ids of events this harness actually created. A caller that made a
        # visible change to someone's calendar should be able to find it again
        # without scraping the turn stream — to show it, or to undo it.
        self.created_event_ids: list[str] = []
        self.spec = HarnessSpec(id="google_calendar", version="v3", available=False)

    async def discover(self) -> HarnessSpec:
        self._service = None
        try:
            import google.auth
            from googleapiclient.discovery import build
        except (ImportError, FileNotFoundError) as exc:
            self.spec = HarnessSpec(
                id="google_calendar",
                version="v3",
                available=False,
                detail=(
                    "Google Calendar requires google-auth and "
                    f"google-api-python-client ({exc})."
                ),
            )
            return self.spec
        except Exception as exc:
            self.spec = HarnessSpec(
                id="google_calendar",
                version="v3",
                available=False,
                detail=f"Google Calendar imports failed: {type(exc).__name__}: {exc}",
            )
            return self.spec

        try:
            credentials, _project = google.auth.default(scopes=[_CALENDAR_SCOPE])
        except Exception as exc:
            self.spec = HarnessSpec(
                id="google_calendar",
                version="v3",
                available=False,
                detail=(
                    "Google Calendar Application Default Credentials are unavailable: "
                    f"{type(exc).__name__}: {exc}"
                ),
            )
            return self.spec

        try:
            service = build("calendar", "v3", credentials=credentials)
            service.events().list(calendarId=self.calendar_id, maxResults=1).execute()
        except Exception as exc:
            status = _http_status(exc)
            message = _http_message(exc)
            if status == 403:
                detail = (
                    f"Google Calendar returned HTTP 403 ({message}); credentials need "
                    f"scope {_CALENDAR_SCOPE}."
                )
            else:
                prefix = f"HTTP {status}" if status is not None else "Google Calendar error"
                detail = f"{prefix}: {message}"
            self.spec = HarnessSpec(
                id="google_calendar",
                version="v3",
                available=False,
                detail=detail,
            )
            return self.spec

        self._service = service
        self.spec = HarnessSpec(
            id="google_calendar",
            version="v3",
            capabilities=("tool_call", "tool_result", "usage"),
            available=True,
            detail=f"Google Calendar API v3, calendar {self.calendar_id!r}",
        )
        return self.spec

    def run(
        self,
        prompt: str,
        *,
        cwd: str,
        session_id: str | None = None,
    ) -> AsyncIterator[HarnessTurn]:
        return self._run(prompt)

    async def _run(self, prompt: str) -> AsyncIterator[HarnessTurn]:
        event = _event_body(prompt)

        yield HarnessTurn(
            kind="tool_call",
            tool_name="calendar.events.insert",
            tool_args=event,
            raw=event,
        )

        # Refuse locally rather than letting Google refuse for us. An
        # orchestrating model paraphrases; when it drops the times, the API
        # answers "Missing end time", which reads like our bug and costs a
        # round trip to learn nothing. Say what is missing instead.
        missing = [field for field in ("start", "end") if field not in event]
        if missing:
            yield HarnessTurn(
                kind="error",
                tool_name="calendar.events.insert",
                text=(
                    f"Cannot create an event without {' and '.join(missing)}. "
                    "Pass a JSON event body with RFC3339 start and end times; "
                    "prose alone does not carry them."
                ),
                raw={"missing": missing, "event": event},
            )
            yield HarnessTurn(
                kind="usage",
                text="0 calendar API requests",
                tool_args={"api_calls": 0},
                raw={"api_calls": 0},
            )
            return

        if self.dry_run:
            yield HarnessTurn(
                kind="tool_result",
                tool_name="calendar.events.insert",
                text="dry run: nothing was created",
                raw={"created": False, "dry_run": True},
            )
            yield HarnessTurn(
                kind="usage",
                text="0 calendar API requests",
                tool_args={"api_calls": 0},
                raw={"api_calls": 0},
            )
            return

        if self._service is None:
            yield HarnessTurn(
                kind="error",
                tool_name="calendar.events.insert",
                text="Google Calendar has not been discovered successfully",
            )
            return

        try:
            created = self._service.events().insert(
                calendarId=self.calendar_id,
                body=event,
            ).execute()
        except Exception as exc:
            status = _http_status(exc)
            message = _http_message(exc)
            prefix = f"HTTP {status}" if status is not None else "Google Calendar error"
            yield HarnessTurn(
                kind="error",
                tool_name="calendar.events.insert",
                text=f"{prefix}: {message}",
                raw=exc,
            )
            yield HarnessTurn(
                kind="usage",
                text="1 calendar API request",
                tool_args={"api_calls": 1},
                raw={"api_calls": 1},
            )
            return

        result = {
            "id": created.get("id") if isinstance(created, dict) else None,
            "htmlLink": created.get("htmlLink") if isinstance(created, dict) else None,
        }
        if result["id"]:
            self.created_event_ids.append(str(result["id"]))
        yield HarnessTurn(
            kind="tool_result",
            tool_name="calendar.events.insert",
            text=json.dumps(result),
            raw=created,
        )
        yield HarnessTurn(
            kind="usage",
            text="1 calendar API request",
            tool_args={"api_calls": 1},
            raw={"api_calls": 1},
        )

    async def delete_events(self, event_ids: Sequence[str]) -> int:
        """Remove events this harness created, returning how many were removed.

        A demo that creates a real event on a real calendar should be able to
        clean up after itself. Deletion is deliberately explicit rather than
        automatic on close: an event nobody asked to remove is not litter, and
        silently undoing a change a human approved would be its own kind of
        governance failure.
        """
        if self._service is None:
            await self.discover()
        if self._service is None:
            return 0
        removed = 0
        for event_id in event_ids:
            try:
                await asyncio.to_thread(
                    self._service.events()
                    .delete(calendarId=self.calendar_id, eventId=event_id)
                    .execute
                )
            except Exception:  # cleanup must not mask the result it is cleaning up
                continue
            removed += 1
            if event_id in self.created_event_ids:
                self.created_event_ids.remove(event_id)
        return removed

    async def aclose(self) -> None:
        self._service = None
