"""Small, governed Google Workspace connection surface.

The pinned ADK Workspace toolsets cannot accept a per-user credential while
they are being constructed.  This module therefore uses the official Google
API Python client with credentials obtained from the existing authentication
boundary.  It intentionally exposes a finite set of typed, bounded reads;
host-only mutations are represented as refusals until the phase 5/6 host gate
is available.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, date, datetime
from types import MappingProxyType
from typing import Any

from adk_harness.auth import CredentialPurpose, GoogleAuthenticator

__all__ = [
    "APPLICATION_SCOPES",
    "CredentialReference",
    "WorkspaceConnection",
    "WorkspaceConnectionError",
    "WorkspaceConsent",
    "WorkspaceDenied",
    "WorkspaceStale",
    "WorkspaceUnknownOutcome",
    "WorkspaceUnsupported",
]

APPLICATION_SCOPES: dict[str, tuple[str, ...]] = {
    "calendar": ("https://www.googleapis.com/auth/calendar.events",),
    "gmail": ("https://www.googleapis.com/auth/gmail.compose",),
    "docs": ("https://www.googleapis.com/auth/documents",),
    "sheets": ("https://www.googleapis.com/auth/spreadsheets",),
}
CALENDAR_ACCESS_SCOPE = "https://www.googleapis.com/auth/calendar.calendarlist.readonly"
APPLICATIONS = frozenset(APPLICATION_SCOPES)
READ_OPERATIONS = frozenset(
    {
        "calendar_get_event",
        "calendar_list_events",
        "gmail_list_drafts",
        "gmail_get_draft",
        "docs_get",
        "sheets_get_values",
    }
)
READ_OPERATION_ORDER = (
    "calendar_get_event",
    "calendar_list_events",
    "gmail_list_drafts",
    "gmail_get_draft",
    "docs_get",
    "sheets_get_values",
)
MUTATING_OPERATIONS = frozenset(
    {"calendar_create_event", "calendar_update_event", "calendar_delete_event", "docs_insert_text"}
)
OPERATIONS = READ_OPERATIONS | MUTATING_OPERATIONS
_A1_RANGE = re.compile(r"^[A-Za-z]{1,3}[1-9][0-9]*(?::[A-Za-z]{1,3}[1-9][0-9]*)?$")
_EVENT_ID = re.compile(r"^[a-v0-9]{5,1024}$")
_EVENT_FIELDS = frozenset(
    {
        "id", "start", "end", "summary", "description", "location", "status",
        "visibility", "reminders",
    }
)
_SAFE_REMINDERS = {"useDefault": False, "overrides": []}


def _safe_response_reminders(value: Any) -> bool:
    return (
        isinstance(value, Mapping)
        and value.get("useDefault") is False
        and set(value).issubset({"useDefault", "overrides"})
        and value.get("overrides", []) == []
    )


def _parse_time(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        raise ValueError("consent time bounds must be ISO-8601 timestamps") from None
    if parsed.tzinfo is None:
        raise ValueError("consent time bounds require a timezone")
    return parsed


class WorkspaceConnectionError(RuntimeError):
    """Base class for safe Workspace refusals and SDK failures."""


class WorkspaceDenied(WorkspaceConnectionError):
    """The trusted consent or resource access gate refused an operation."""


class WorkspaceStale(WorkspaceConnectionError):
    """A conditional mutation was rejected because its approved version is stale."""


class WorkspaceUnknownOutcome(WorkspaceConnectionError):
    """A mutation may have reached Google but its result was not observed."""


class WorkspaceUnsupported(WorkspaceConnectionError):
    """An operation is outside this milestone's safe catalog."""


@dataclass(frozen=True, slots=True)
class CredentialReference:
    """Non-secret pointer to a verified Workspace grant."""

    subject: str
    reference: str = "local-keyring"
    purpose: CredentialPurpose = CredentialPurpose.WORKSPACE
    scopes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.subject or not self.reference:
            raise ValueError("credential reference requires subject and reference")
        if self.purpose is not CredentialPurpose.WORKSPACE:
            raise ValueError("Workspace connections require a workspace credential")
        object.__setattr__(self, "scopes", tuple(sorted(set(map(str, self.scopes)))))

    def to_config(self) -> dict[str, Any]:
        """Return serializable metadata; never return credential material."""
        return {
            "reference": self.reference,
            "subject": self.subject,
            "purpose": self.purpose.value,
            "scopes": self.scopes,
        }


@dataclass(frozen=True, slots=True)
class WorkspaceConsent:
    """Explicit, expiring human consent for reads and selected resources."""

    subject: str
    applications: tuple[str, ...]
    resources: Mapping[str, tuple[str, ...]]
    operations: tuple[str, ...] = READ_OPERATION_ORDER
    approved: bool = False
    expires_at: datetime | None = None
    calendar_windows: Mapping[str, tuple[str, str]] = MappingProxyType({})
    sheets_ranges: Mapping[str, tuple[str, ...]] = MappingProxyType({})
    calendar_event_ids: Mapping[str, tuple[str, ...]] = MappingProxyType({})
    gmail_draft_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        apps = tuple(dict.fromkeys(self.applications))
        if not self.subject or not apps or any(app not in APPLICATIONS for app in apps):
            raise ValueError("consent has an unsupported or missing application")
        if self.expires_at is None or self.expires_at.tzinfo is None:
            raise ValueError("Workspace consent requires a finite timezone-aware expiry")
        ops = tuple(dict.fromkeys(self.operations))
        if any(op not in OPERATIONS for op in ops):
            raise ValueError("consent has an unsupported operation")
        normalized = {
            str(app): tuple(dict.fromkeys(map(str, ids))) for app, ids in self.resources.items()
        }
        if any(app not in APPLICATIONS for app in normalized):
            raise ValueError("consent has an unsupported resource application")
        object.__setattr__(self, "applications", apps)
        object.__setattr__(self, "operations", ops)
        windows = {str(key): tuple(value) for key, value in self.calendar_windows.items()}
        if any(len(value) != 2 or not all(value) for value in windows.values()):
            raise ValueError("calendar consent windows must contain exact non-empty bounds")
        if any(_parse_time(value[0]) >= _parse_time(value[1]) for value in windows.values()):
            raise ValueError("calendar consent windows must have start before end")
        ranges = {
            str(key): tuple(dict.fromkeys(map(str, value)))
            for key, value in self.sheets_ranges.items()
        }
        if any(
            not values or any(not _A1_RANGE.fullmatch(item) for item in values)
            for values in ranges.values()
        ):
            raise ValueError("sheets consent ranges must contain bounded A1 ranges")
        event_ids = {
            str(calendar): tuple(dict.fromkeys(map(str, ids)))
            for calendar, ids in self.calendar_event_ids.items()
        }
        if any(calendar not in normalized.get("calendar", ()) for calendar in event_ids):
            raise ValueError("calendar event IDs must belong to an approved calendar")
        if any(
            not _EVENT_ID.fullmatch(event_id)
            for ids in event_ids.values()
            for event_id in ids
        ):
            raise ValueError("calendar event IDs must use the stable base32hex form")
        draft_ids = tuple(dict.fromkeys(map(str, self.gmail_draft_ids)))
        if any(not draft_id for draft_id in draft_ids):
            raise ValueError("Gmail draft IDs must be non-empty")
        object.__setattr__(self, "resources", MappingProxyType(normalized))
        object.__setattr__(self, "calendar_windows", MappingProxyType(windows))
        object.__setattr__(self, "sheets_ranges", MappingProxyType(ranges))
        object.__setattr__(self, "calendar_event_ids", MappingProxyType(event_ids))
        object.__setattr__(self, "gmail_draft_ids", draft_ids)

    def allows(self, *, subject: str, application: str, resource: str, operation: str) -> bool:
        if not self.approved or subject != self.subject or application not in self.applications:
            return False
        expires_at = self.expires_at
        if expires_at is None or datetime.now(UTC) >= expires_at:
            return False
        return operation in self.operations and resource in self.resources.get(application, ())

    def to_config(self) -> dict[str, Any]:
        return {
            "subject": self.subject,
            "applications": self.applications,
            "resources": dict(self.resources),
            "operations": self.operations,
            "approved": self.approved,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "calendar_windows": dict(self.calendar_windows),
            "sheets_ranges": dict(self.sheets_ranges),
            "calendar_event_ids": dict(self.calendar_event_ids),
            "gmail_draft_ids": self.gmail_draft_ids,
        }


ServiceFactory = Callable[[str, Any], Any]


class WorkspaceConnection:
    """Official discovery clients behind explicit consent and resource gates."""

    def __init__(
        self,
        *,
        authenticator: GoogleAuthenticator,
        credential_reference: CredentialReference,
        consent: WorkspaceConsent,
        resource_allowlist: Mapping[str, Sequence[str]] | None = None,
        service_factory: ServiceFactory | None = None,
    ) -> None:
        if credential_reference.subject != consent.subject:
            raise WorkspaceDenied("credential and consent subjects differ")
        self.authenticator = authenticator
        self.credential_reference = credential_reference
        self.consent = consent
        self.resource_allowlist = {
            app: frozenset(map(str, resources))
            for app, resources in (resource_allowlist or consent.resources).items()
        }
        if any(app not in APPLICATIONS for app in self.resource_allowlist):
            raise WorkspaceDenied("resource allowlist contains an unsupported application")
        self._service_factory = service_factory or _build_service

    def config(self) -> dict[str, Any]:
        return {
            "credential": self.credential_reference.to_config(),
            "consent": self.consent.to_config(),
            "resource_allowlist": {
                app: tuple(resources) for app, resources in self.resource_allowlist.items()
            },
        }

    def _authorize(self, application: str, resource: str, operation: str) -> Any:
        if application not in APPLICATIONS or operation not in OPERATIONS:
            raise WorkspaceUnsupported("unsupported Workspace application or operation")
        if resource not in self.resource_allowlist.get(application, ()):
            raise WorkspaceDenied("resource is not in the Workspace allowlist")
        if not self.consent.allows(
            subject=self.credential_reference.subject,
            application=application,
            resource=resource,
            operation=operation,
        ):
            raise WorkspaceDenied("explicit Workspace consent is missing or expired")
        required = set(APPLICATION_SCOPES[application])
        if application == "calendar":
            required.add(CALENDAR_ACCESS_SCOPE)
        try:
            credentials = self.authenticator.verified_credentials(
                CredentialPurpose.WORKSPACE,
                subject=self.credential_reference.subject,
                required_scopes=tuple(sorted(required)),
            )
            return self._service_factory(application, credentials)
        except WorkspaceConnectionError:
            raise
        except Exception:
            raise WorkspaceDenied("verified Workspace credentials are unavailable") from None

    def _calendar_access(self, service: Any, calendar_id: str) -> str:
        try:
            response = (
                service.calendarList()
                .get(calendarId=calendar_id, fields="id,accessRole")
                .execute()
            )
        except Exception:
            raise WorkspaceDenied("calendar access preflight failed") from None
        role = response.get("accessRole") if isinstance(response, Mapping) else None
        if role not in {"freeBusyReader", "reader", "writer", "owner"}:
            raise WorkspaceDenied("calendar access is unavailable")
        return str(role)

    @staticmethod
    def _calendar_writer(role: str) -> None:
        if role not in {"writer", "owner"}:
            raise WorkspaceDenied("calendar mutation requires writer or owner access")

    @staticmethod
    def _current_event(service: Any, calendar_id: str, event_id: str, etag: str) -> None:
        try:
            current = service.events().get(
                calendarId=calendar_id,
                eventId=event_id,
                fields=(
                    "id,etag,attendees,conferenceData,recurrence,recurringEventId,"
                    "originalStartTime,eventType,reminders"
                ),
            ).execute()
        except Exception:
            raise WorkspaceDenied("calendar mutation preflight failed") from None
        if (
            not isinstance(current, Mapping)
            or current.get("id") != event_id
            or current.get("etag") != etag
        ):
            raise WorkspaceDenied("calendar event version is stale")
        if any(
            current.get(key)
            for key in (
                "attendees", "conferenceData", "recurrence", "recurringEventId",
                "originalStartTime",
            )
        ):
            raise WorkspaceUnsupported("calendar event has unsupported existing side effects")
        if current.get("eventType") not in (None, "default"):
            raise WorkspaceUnsupported("calendar event type is unsupported")
        if not _safe_response_reminders(current.get("reminders")):
            raise WorkspaceUnsupported("calendar event has inherited or enabled reminders")

    def calendar_get_event(self, *, calendar_id: str, event_id: str) -> Mapping[str, Any]:
        if not event_id:
            raise ValueError("event_id is required")
        if event_id not in self.consent.calendar_event_ids.get(calendar_id, ()):
            raise WorkspaceDenied("calendar event is not in explicit consent")
        service = self._authorize("calendar", calendar_id, "calendar_get_event")
        try:
            self._calendar_access(service, calendar_id)
            return service.events().get(
                calendarId=calendar_id,
                eventId=event_id,
                fields="id,etag,updated,status,start,end,summary,description,location,visibility",
            ).execute()
        except Exception:
            raise WorkspaceDenied("calendar event read failed") from None
        finally:
            _close_service(service)

    def calendar_list_events(
        self,
        *,
        calendar_id: str,
        time_min: str,
        time_max: str,
        max_results: int = 25,
    ) -> Mapping[str, Any]:
        if not time_min or not time_max or not 1 <= max_results <= 100:
            raise ValueError("calendar reads require a bounded time window and max_results 1..100")
        if self.consent.calendar_windows.get(calendar_id) != (time_min, time_max):
            raise WorkspaceDenied("calendar read window is not in explicit consent")
        service = self._authorize("calendar", calendar_id, "calendar_list_events")
        try:
            self._calendar_access(service, calendar_id)
            return service.events().list(
                calendarId=calendar_id,
                timeMin=time_min,
                timeMax=time_max,
                maxResults=max_results,
                singleEvents=True,
                orderBy="startTime",
                fields="items(id,etag,updated,status,start,end,summary,description,location,visibility),nextPageToken",
            ).execute()
        except Exception:
            raise WorkspaceDenied("calendar event list failed") from None
        finally:
            _close_service(service)

    def gmail_list_drafts(
        self, *, max_results: int = 25, page_token: str | None = None
    ) -> Mapping[str, Any]:
        if not 1 <= max_results <= 100:
            raise ValueError("draft reads require max_results 1..100")
        service = self._authorize("gmail", "me", "gmail_list_drafts")
        kwargs: dict[str, Any] = {"userId": "me", "maxResults": max_results}
        if page_token:
            kwargs["pageToken"] = page_token
        try:
            return service.users().drafts().list(**kwargs).execute()
        except Exception:
            raise WorkspaceDenied("Gmail draft list failed") from None
        finally:
            _close_service(service)

    def gmail_get_draft(self, *, draft_id: str) -> Mapping[str, Any]:
        if not draft_id:
            raise ValueError("draft_id is required")
        if draft_id not in self.consent.gmail_draft_ids:
            raise WorkspaceDenied("Gmail draft is not in explicit consent")
        service = self._authorize("gmail", "me", "gmail_get_draft")
        try:
            return service.users().drafts().get(
                userId="me", id=draft_id, format="metadata"
            ).execute()
        except Exception:
            raise WorkspaceDenied("Gmail draft read failed") from None
        finally:
            _close_service(service)

    def docs_get(self, *, document_id: str) -> Mapping[str, Any]:
        if not document_id:
            raise ValueError("document_id is required")
        service = self._authorize("docs", document_id, "docs_get")
        try:
            return service.documents().get(
                documentId=document_id, fields="documentId,title,revisionId"
            ).execute()
        except Exception:
            raise WorkspaceDenied("Docs document read failed") from None
        finally:
            _close_service(service)

    def sheets_get_values(self, *, spreadsheet_id: str, range: str) -> Mapping[str, Any]:
        if not spreadsheet_id or not _A1_RANGE.fullmatch(range):
            raise ValueError("sheets reads require an exact bounded A1 range")
        if range not in self.consent.sheets_ranges.get(spreadsheet_id, ()):
            raise WorkspaceDenied("sheet range is not in explicit consent")
        service = self._authorize("sheets", spreadsheet_id, "sheets_get_values")
        try:
            return service.spreadsheets().values().get(
                spreadsheetId=spreadsheet_id,
                range=range,
                majorDimension="ROWS",
            ).execute()
        except Exception:
            raise WorkspaceDenied("Sheets values read failed") from None
        finally:
            _close_service(service)

    @staticmethod
    def _host_authorized(
        operation: str, payload: Mapping[str, Any], host_authorizer: Callable[..., bool] | None
    ) -> None:
        try:
            allowed = (
                host_authorizer is not None
                and host_authorizer(operation, deepcopy(dict(payload))) is True
            )
        except Exception:
            allowed = False
        if not allowed:
            raise WorkspaceDenied("Workspace mutations require trusted host authorization")

    def _recheck_mutation(
        self,
        operation: str,
        resource: str,
        payload: Mapping[str, Any],
        host_authorizer: Callable[..., bool] | None,
    ) -> None:
        if not self.consent.allows(
            subject=self.credential_reference.subject,
            application="calendar" if operation.startswith("calendar_") else "docs",
            resource=resource,
            operation=operation,
        ):
            raise WorkspaceDenied("Workspace consent expired during mutation preflight")
        self._host_authorized(operation, payload, host_authorizer)

    @staticmethod
    def _validate_event_body(
        body: Mapping[str, Any], *, require_id: bool = False
    ) -> dict[str, Any]:
        if not isinstance(body, Mapping) or not {"start", "end"}.issubset(body):
            raise ValueError("calendar event body requires start and end")
        if set(body) - _EVENT_FIELDS:
            raise WorkspaceUnsupported("calendar event contains unsupported side effects")
        if body.get("reminders") != _SAFE_REMINDERS:
            raise WorkspaceUnsupported("calendar event requires explicit disabled reminders")
        starts = body["start"]
        ends = body["end"]
        if not isinstance(starts, Mapping) or not isinstance(ends, Mapping):
            raise ValueError("calendar event start and end must be typed objects")
        if "dateTime" in starts and "dateTime" in ends:
            if set(starts) - {"dateTime", "timeZone"} or set(ends) - {"dateTime", "timeZone"}:
                raise WorkspaceUnsupported("calendar event time contains unsupported fields")
            if _parse_time(str(starts["dateTime"])) >= _parse_time(str(ends["dateTime"])):
                raise ValueError("calendar event start must precede end")
        elif "date" in starts and "date" in ends:
            if set(starts) != {"date"} or set(ends) != {"date"}:
                raise WorkspaceUnsupported("all-day event time contains unsupported fields")
            try:
                start_date = date.fromisoformat(str(starts["date"]))
                end_date = date.fromisoformat(str(ends["date"]))
            except (TypeError, ValueError):
                raise ValueError("calendar event date must use YYYY-MM-DD") from None
            if start_date >= end_date:
                raise ValueError("calendar event start must precede end")
        else:
            raise ValueError("calendar event start and end must use matching date or dateTime")
        if require_id and (
            not isinstance(body.get("id"), str) or not _EVENT_ID.fullmatch(body["id"])
        ):
            raise ValueError("calendar insert requires a stable base32hex event id")
        return dict(body)

    def calendar_create_event(
        self,
        *,
        calendar_id: str,
        body: Mapping[str, Any],
        host_authorizer: Callable[..., bool] | None = None,
    ) -> Mapping[str, Any]:
        event = deepcopy(self._validate_event_body(body, require_id=True))
        self._host_authorized(
            "calendar_create_event",
            {"calendar_id": calendar_id, "body": deepcopy(event)},
            host_authorizer,
        )
        service = self._authorize("calendar", calendar_id, "calendar_create_event")
        try:
            role = self._calendar_access(service, calendar_id)
            self._calendar_writer(role)
            self._recheck_mutation(
                "calendar_create_event",
                calendar_id,
                {"calendar_id": calendar_id, "body": deepcopy(event)},
                host_authorizer,
            )
        except WorkspaceConnectionError:
            _close_service(service)
            raise
        except Exception:
            _close_service(service)
            raise WorkspaceDenied("calendar mutation preflight failed") from None
        try:
            return _checked_response(service.events().insert(
                calendarId=calendar_id, body=event, sendUpdates="none"
            ).execute())
        except WorkspaceConnectionError:
            raise
        except Exception as exc:
            raise _mutation_failure(exc) from None
        finally:
            _close_service(service)

    def calendar_update_event(
        self,
        *,
        calendar_id: str,
        event_id: str,
        body: Mapping[str, Any],
        approved_etag: str,
        host_authorizer: Callable[..., bool] | None = None,
    ) -> Mapping[str, Any]:
        if not event_id or not approved_etag:
            raise ValueError("calendar update requires event_id and approved_etag")
        event = deepcopy(self._validate_event_body(body))
        if event.get("id", event_id) != event_id:
            raise ValueError("calendar event body id does not match event_id")
        self._host_authorized(
            "calendar_update_event",
            {
                "calendar_id": calendar_id,
                "event_id": event_id,
                "body": deepcopy(event),
                "etag": approved_etag,
            },
            host_authorizer,
        )
        service = self._authorize("calendar", calendar_id, "calendar_update_event")
        try:
            role = self._calendar_access(service, calendar_id)
            self._calendar_writer(role)
            self._current_event(service, calendar_id, event_id, approved_etag)
            self._recheck_mutation(
                "calendar_update_event",
                calendar_id,
                {
                    "calendar_id": calendar_id,
                    "event_id": event_id,
                    "body": deepcopy(event),
                    "etag": approved_etag,
                },
                host_authorizer,
            )
        except WorkspaceConnectionError:
            _close_service(service)
            raise
        except Exception:
            _close_service(service)
            raise WorkspaceDenied("calendar mutation preflight failed") from None
        try:
            request = service.events().update(
                calendarId=calendar_id, eventId=event_id, body=event, sendUpdates="none"
            )
            request.headers["If-Match"] = approved_etag
            return _checked_response(request.execute())
        except WorkspaceConnectionError:
            raise
        except Exception as exc:
            raise _mutation_failure(exc, calendar=True) from None
        finally:
            _close_service(service)

    def calendar_delete_event(
        self,
        *,
        calendar_id: str,
        event_id: str,
        approved_etag: str,
        host_authorizer: Callable[..., bool] | None = None,
    ) -> Mapping[str, Any]:
        if not event_id or not approved_etag:
            raise ValueError("calendar delete requires event_id and approved_etag")
        self._host_authorized(
            "calendar_delete_event",
            {"calendar_id": calendar_id, "event_id": event_id, "etag": approved_etag},
            host_authorizer,
        )
        service = self._authorize("calendar", calendar_id, "calendar_delete_event")
        try:
            role = self._calendar_access(service, calendar_id)
            self._calendar_writer(role)
            self._current_event(service, calendar_id, event_id, approved_etag)
            self._recheck_mutation(
                "calendar_delete_event",
                calendar_id,
                {"calendar_id": calendar_id, "event_id": event_id, "etag": approved_etag},
                host_authorizer,
            )
        except WorkspaceConnectionError:
            _close_service(service)
            raise
        except Exception:
            _close_service(service)
            raise WorkspaceDenied("calendar mutation preflight failed") from None
        try:
            request = service.events().delete(calendarId=calendar_id, eventId=event_id)
            request.headers["If-Match"] = approved_etag
            result = request.execute()
            if result == "":
                return {}
            return _checked_response(result)
        except WorkspaceConnectionError:
            raise
        except Exception as exc:
            raise _mutation_failure(exc, calendar=True) from None
        finally:
            _close_service(service)

    def docs_insert_text(
        self,
        *,
        document_id: str,
        index: int,
        text: str,
        required_revision_id: str,
        host_authorizer: Callable[..., bool] | None = None,
    ) -> Mapping[str, Any]:
        if not document_id or index < 1 or not text or not required_revision_id:
            raise ValueError("Docs insert requires document, positive index, text, and revision")
        payload = {
            "document_id": document_id,
            "index": index,
            "text": text,
            "revision": required_revision_id,
        }
        self._host_authorized("docs_insert_text", payload, host_authorizer)
        service = self._authorize("docs", document_id, "docs_insert_text")
        try:
            current = service.documents().get(
                documentId=document_id, fields="documentId,revisionId"
            ).execute()
            if (
                not isinstance(current, Mapping)
                or current.get("revisionId") != required_revision_id
            ):
                raise WorkspaceDenied("Docs edit access or required revision is unavailable")
            self._recheck_mutation(
                "docs_insert_text", document_id, deepcopy(payload), host_authorizer
            )
        except WorkspaceConnectionError:
            _close_service(service)
            raise
        except Exception:
            _close_service(service)
            raise WorkspaceDenied("Docs mutation preflight failed") from None
        try:
            request = {
                "requests": [{"insertText": {"location": {"index": index}, "text": text}}],
                "writeControl": {"requiredRevisionId": required_revision_id},
            }
            return _checked_response(
                service.documents().batchUpdate(documentId=document_id, body=request).execute()
            )
        except WorkspaceConnectionError:
            raise
        except Exception as exc:
            raise _mutation_failure(exc, docs=True) from None
        finally:
            _close_service(service)


def _build_service(application: str, credentials: Any) -> Any:
    from googleapiclient.discovery import build

    service_name = {
        "calendar": "calendar",
        "gmail": "gmail",
        "docs": "docs",
        "sheets": "sheets",
    }[application]
    version = {"calendar": "v3", "gmail": "v1", "docs": "v1", "sheets": "v4"}[application]
    return build(
        service_name,
        version,
        credentials=credentials,
        static_discovery=True,
        cache_discovery=False,
    )


def _close_service(service: Any) -> None:
    """Close only clients that expose the official public close hook."""
    close = getattr(service, "close", None)
    if callable(close):
        try:
            close()
        except Exception:
            # Cleanup must not disclose transport details or replace a read result.
            pass


def _mutation_failure(
    error: Exception | None, *, calendar: bool = False, docs: bool = False
) -> WorkspaceConnectionError:
    """Map only structured, post-dispatch failures to safe typed outcomes."""
    if isinstance(error, (TimeoutError, OSError, ConnectionError)):
        return WorkspaceUnknownOutcome(
            "mutation dispatch outcome is unknown; reconcile before retry"
        )
    status = getattr(getattr(error, "resp", None), "status", None)
    if status is None:
        status = getattr(error, "status", None)
    if calendar and status == 412:
        return WorkspaceStale("calendar event version is stale")
    if docs and status == 400:
        content = getattr(error, "content", b"")
        if isinstance(content, bytes):
            content = content.decode("utf-8", errors="ignore")
        try:
            details = json.loads(content) if content else {}
        except (TypeError, ValueError):
            details = {}
        text = json.dumps(details).lower()
        if "revision" in text or "writecontrol" in text:
            return WorkspaceStale("Docs required revision is stale")
    if status in {400, 401, 403, 404, 409, 422}:
        return WorkspaceDenied("Workspace mutation was rejected")
    return WorkspaceUnknownOutcome("mutation dispatch outcome is unknown; reconcile before retry")


def _checked_response(value: Any) -> Mapping[str, Any]:
    if isinstance(value, bytes):
        if not value:
            return {}
        try:
            value = json.loads(value)
        except (TypeError, ValueError):
            raise WorkspaceUnknownOutcome(
                "mutation response was malformed; reconcile before retry"
            ) from None
    if not isinstance(value, Mapping):
        raise WorkspaceUnknownOutcome("mutation response was malformed; reconcile before retry")
    return value
