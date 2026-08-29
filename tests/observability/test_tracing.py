from __future__ import annotations

import logging
from io import StringIO
from unittest.mock import AsyncMock, PropertyMock, patch

import pytest
from google.adk.models.google_llm import Gemini
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.genai import types
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from adk_harness.observability.tracing import (
    MetadataTracer,
    configure_safe_adk_logging,
    safe_adk_telemetry_config,
)


def test_metadata_tracer_propagates_context_and_drops_unallowlisted_content() -> None:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracer = MetadataTracer(provider.get_tracer("test"))
    carrier: dict[str, str] = {}

    with tracer.span("submission", {"task_id": "task-a", "prompt": "secret-content"}):
        tracer.inject(carrier)
        with tracer.span("worker", {"operation_id": "op-a"}, context=tracer.extract(carrier)):
            pass
    spans = exporter.get_finished_spans()
    assert {span.name for span in spans} == {"submission", "worker"}
    assert all("secret-content" not in repr(span) for span in spans)
    assert all("prompt" not in span.attributes for span in spans)
    assert spans[0].context.trace_id == spans[1].context.trace_id


def test_safe_telemetry_and_sdk_logging_disable_content_capture() -> None:
    config = safe_adk_telemetry_config()
    assert config.resolved_content_capturing_mode.value == "NO_CONTENT"
    logger_name = "google_adk.google.adk.models.google_llm"
    configure_safe_adk_logging()
    assert logging.getLogger(logger_name).level >= logging.WARNING


def test_installed_gemini_logger_does_not_emit_sensitive_marker_at_safe_level() -> None:
    marker = "SYNTHETIC_PRIVATE_GEMINI_LOG_SENTINEL_83"
    logger = logging.getLogger("google_adk.google.adk.models.google_llm")
    stream = StringIO()
    handler = logging.StreamHandler(stream)
    logger.addHandler(handler)
    try:
        configure_safe_adk_logging()
        logger.debug("request content: %s", marker)
        logger.info("response content: %s", marker)
    finally:
        logger.removeHandler(handler)
        handler.close()
    assert marker not in stream.getvalue()


@pytest.mark.asyncio
async def test_actual_gemini_public_generation_path_is_safe_at_startup_level() -> None:
    marker = "SYNTHETIC_PRIVATE_GEMINI_LOG_SENTINEL_84"
    logger = logging.getLogger("google_adk.google.adk.models.google_llm")
    stream = StringIO()
    handler = logging.StreamHandler(stream)
    logger.addHandler(handler)

    class Models:
        generate_content = AsyncMock(return_value=object())

    class Api:
        vertexai = True
        aio = type("Aio", (), {"models": Models()})()

    model = Gemini(
        model="gemini-test",
        client_kwargs={
            "vertexai": True,
            "project": "project-a",
            "location": "us-central1",
            "credentials": object(),
        },
    )
    request = LlmRequest(
        model="gemini-test",
        contents=[types.Content(role="user", parts=[types.Part(text=marker)])],
    )
    response = LlmResponse(content=types.Content(role="model", parts=[types.Part(text="ok")]))
    try:
        configure_safe_adk_logging()
        with (
            patch.object(Gemini, "api_client", new_callable=PropertyMock, return_value=Api()),
            patch("google.adk.models.google_llm.LlmResponse.create", return_value=response),
        ):
            results = [item async for item in model.generate_content_async(request)]
    finally:
        logger.removeHandler(handler)
        handler.close()
    assert results and results[0] is response
    assert marker not in stream.getvalue()
