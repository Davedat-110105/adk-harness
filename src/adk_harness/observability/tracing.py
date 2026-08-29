"""OpenTelemetry propagation for workflow metadata without content capture."""

from __future__ import annotations

import logging
from collections.abc import Iterator, Mapping, MutableMapping
from contextlib import contextmanager
from typing import Any

from opentelemetry import context as otel_context
from opentelemetry import trace
from opentelemetry.trace import Span, Tracer
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

__all__ = [
    "MetadataTracer",
    "configure_safe_adk_logging",
    "safe_adk_telemetry_config",
    "validate_safe_telemetry_environment",
]

SAFE_METADATA_KEYS = frozenset(
    {
        "actor_id",
        "approval_hash",
        "decision",
        "operation_id",
        "outcome",
        "policy_version",
        "project_id",
        "task_id",
        "trace_id",
        "workspace_id",
    }
)


class MetadataTracer:
    """Small wrapper around an official OTel tracer and W3C propagator.

    Span attributes are an explicit allowlist. Unknown keys, mappings, and
    content-like values are discarded before they reach the SDK/exporter.
    Durable policy evidence is separate and therefore unaffected by sampling.
    """

    def __init__(self, tracer: Tracer | None = None) -> None:
        self._tracer = tracer or trace.get_tracer("adk_harness.workflow")
        self._propagator = TraceContextTextMapPropagator()

    @staticmethod
    def metadata(values: Mapping[str, Any] | None) -> dict[str, str]:
        if not values:
            return {}
        result: dict[str, str] = {}
        for key, value in values.items():
            if key not in SAFE_METADATA_KEYS or not isinstance(value, (str, int, bool)):
                continue
            text = str(value)
            if len(text) <= 256:
                result[key] = text
        return result

    @contextmanager
    def span(
        self,
        name: str,
        metadata: Mapping[str, Any] | None = None,
        *,
        context: otel_context.Context | None = None,
    ) -> Iterator[Span]:
        with self._tracer.start_as_current_span(
            name,
            context=context,
            attributes=self.metadata(metadata),
        ) as span:
            yield span

    def inject(
        self,
        carrier: MutableMapping[str, str],
        *,
        context: otel_context.Context | None = None,
    ) -> None:
        self._propagator.inject(carrier, context=context or otel_context.get_current())

    def extract(self, carrier: Mapping[str, str]) -> otel_context.Context:
        return self._propagator.extract(carrier)


def safe_adk_telemetry_config() -> Any:
    """Return ADK's public per-run config with all content capture disabled."""
    from google.adk.telemetry import ContentCapturingMode, TelemetryConfig

    return TelemetryConfig(
        capture_message_content=ContentCapturingMode.NO_CONTENT,
        adk_experimental_telemetry_opt_in=False,
    )


def configure_safe_adk_logging() -> None:
    """Set installed ADK Gemini logger(s) to WARNING once at process startup."""
    # The first name is the installed package logger; the second supports older
    # ADK namespace layouts without changing any per-task logger state.
    for name in ("google_adk.google.adk.models.google_llm", "google.adk.models.google_llm"):
        logger = logging.getLogger(name)
        if logger.level == logging.NOTSET or logger.level < logging.WARNING:
            logger.setLevel(logging.WARNING)


def validate_safe_telemetry_environment(
    values: Mapping[str, str] | None = None, *, require_explicit: bool = False
) -> None:
    """Reject explicit process settings that could re-enable content capture."""
    import os

    env = os.environ if values is None else values
    truthy = {"1", "true", "yes", "on"}
    if str(env.get("ADK_TELEMETRY_IGNORE_RUN_CONFIG", "")).strip().casefold() in truthy:
        raise PermissionError("ADK telemetry admin lock would bypass no-content RunConfig")
    legacy = env.get("ADK_CAPTURE_MESSAGE_CONTENT_IN_SPANS")
    if require_explicit and legacy is None:
        raise PermissionError("ADK span content setting must be explicit")
    if legacy is not None and str(legacy).strip().casefold() not in {"0", "false", "no", "off"}:
        raise PermissionError("ADK span content capture must be disabled")
    genai = env.get("OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT")
    if require_explicit and genai is None:
        raise PermissionError("GenAI telemetry content setting must be explicit")
    if genai is not None and str(genai).strip().upper() not in {"", "NO_CONTENT"}:
        raise PermissionError("GenAI telemetry content capture must be NO_CONTENT")
