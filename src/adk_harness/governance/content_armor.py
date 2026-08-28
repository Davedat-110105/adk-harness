"""Local screening of untrusted content and tool arguments.

This is defense in depth, not a prompt-injection guarantee or managed Model Armor.
External content remains untrusted.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from typing import Any

from google.adk.plugins.base_plugin import BasePlugin

__all__ = ["ArmorFinding", "ContentArmor"]

_DEFAULT_URL_FORBIDDEN_FIELDS = frozenset(
    {"cc", "bcc", "email", "name", "recipient", "subject", "to"}
)
_EMAIL_RE = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.IGNORECASE)
_URL_RE = re.compile(r"https?://[^\s<>'\"]+", re.IGNORECASE)
_INSTRUCTION_PATTERNS = (
    ("ignore_previous_instructions", re.compile(r"ignore\s+previous\s+instructions", re.I)),
    ("you_are_now", re.compile(r"you\s+are\s+now", re.I)),
    ("disregard_the_above", re.compile(r"disregard\s+the\s+above", re.I)),
    ("system_prompt", re.compile(r"system\s+prompt", re.I)),
    ("new_instructions", re.compile(r"new\s+instructions\s*:", re.I)),
    ("assistant_role_marker", re.compile(r"\bassistant\s*:", re.I)),
    ("system_role_marker", re.compile(r"<system\s*>", re.I)),
)


class ArmorFinding(dict[str, str]):
    """A traceable screening finding."""

    def __init__(self, tool_name: str, pattern: str, excerpt: str) -> None:
        super().__init__(tool_name=tool_name, pattern=pattern, excerpt=excerpt)


class ContentArmor(BasePlugin):
    """Quarantine suspicious tool results and block suspicious tool inputs."""

    def __init__(
        self,
        *,
        allowed_email_domains: Iterable[str] = (),
        url_forbidden_fields: Iterable[str] = _DEFAULT_URL_FORBIDDEN_FIELDS,
        base64_threshold: int = 120,
        name: str = "content-armor",
    ) -> None:
        super().__init__(name=name)
        self.allowed_email_domains = frozenset(
            domain.lower().lstrip("@").rstrip(".") for domain in allowed_email_domains
        )
        self.url_forbidden_fields = frozenset(field.lower() for field in url_forbidden_fields)
        self.base64_threshold = base64_threshold
        self._instruction_patterns = (*_INSTRUCTION_PATTERNS, (
            # Exclude ordinary API IDs and etags; inspect only longer encoded payloads.
            "base64_blob",
            re.compile(
                rf"(?<![A-Za-z0-9+/])[A-Za-z0-9+/]{{{base64_threshold},}}={{0,2}}(?![A-Za-z0-9+/])"
            ),
        ))
        self.findings: list[ArmorFinding] = []

    async def before_tool_callback(
        self,
        *,
        tool: Any,
        tool_args: dict[str, Any],
        tool_context: Any,
    ) -> dict[str, Any] | None:
        tool_name = getattr(tool, "name", type(tool).__name__)
        for field, value in _string_fields(tool_args):
            if field.lower() in {"to", "cc", "bcc", "email", "recipient"}:
                for recipient in _EMAIL_RE.findall(value):
                    domain = recipient.rsplit("@", 1)[1].lower().rstrip(".")
                    if not _domain_allowed(domain, self.allowed_email_domains):
                        pattern = "external_email_recipient"
                        self._find(tool_name, pattern, recipient)
                        return {
                            "status": "blocked",
                            "reason": f"{pattern}: recipient outside allowed domains",
                            "tool": tool_name,
                        }
            if field.lower() in self.url_forbidden_fields:
                match = _URL_RE.search(value)
                if match:
                    pattern = "url_in_forbidden_field"
                    self._find(tool_name, pattern, match.group(0))
                    return {
                        "status": "blocked",
                        "reason": f"{pattern}: URL in {field}",
                        "tool": tool_name,
                    }
        return None

    async def after_tool_callback(
        self,
        *,
        tool: Any,
        tool_args: dict[str, Any],
        tool_context: Any,
        result: Any = None,
    ) -> Any:
        tool_name = getattr(tool, "name", type(tool).__name__)
        matches: list[tuple[str, str]] = []
        for value in _text_values(result):
            for pattern, expression in self._instruction_patterns:
                match = expression.search(value)
                if match:
                    excerpt = _excerpt(value, match.start(), match.end())
                    self._find(tool_name, pattern, excerpt)
                    matches.append((pattern, excerpt))
        if not matches:
            return result
        findings = ", ".join(pattern for pattern, _ in matches)
        return {
            "status": "quarantined",
            "reason": f"untrusted tool result; findings: {findings}",
            "tool": tool_name,
            "untrusted_data": result,
        }

    def _find(self, tool_name: str, pattern: str, excerpt: str) -> None:
        self.findings.append(ArmorFinding(tool_name, pattern, _truncate(excerpt)))


def _domain_allowed(domain: str, allowed: Iterable[str]) -> bool:
    return any(domain == item or domain.endswith(f".{item}") for item in allowed)


def _string_fields(value: Any, field: str = "") -> Iterable[tuple[str, str]]:
    if isinstance(value, Mapping):
        for key, nested in value.items():
            yield from _string_fields(nested, str(key))
    elif isinstance(value, list | tuple | set):
        for nested in value:
            yield from _string_fields(nested, field)
    elif isinstance(value, str):
        yield field, value


def _text_values(value: Any) -> Iterable[str]:
    if isinstance(value, Mapping):
        for nested in value.values():
            yield from _text_values(nested)
    elif isinstance(value, list | tuple | set):
        for nested in value:
            yield from _text_values(nested)
    elif isinstance(value, str):
        yield value
    else:
        yield str(value)


def _excerpt(value: str, start: int, end: int, radius: int = 60) -> str:
    return value[max(0, start - radius) : min(len(value), end + radius)]


def _truncate(value: str, limit: int = 160) -> str:
    return value if len(value) <= limit else f"{value[:limit - 1]}…"
