"""OpenCode HTTP adapter.

Verified on 2026-08-25 against the installed ``opencode`` binary:

    $ /Users/datta/.opencode/bin/opencode --version
    1.17.9

    $ /Users/datta/.opencode/bin/opencode --help
    $ /Users/datta/.opencode/bin/opencode serve --help

``serve`` is the headless server command. Its help documents ``--hostname``
(default ``127.0.0.1``) and ``--port`` (default ``0``, an automatically chosen
port). The binary contains the OpenAPI routes ``/global/health``, ``/session``,
``/session/{sessionID}/message``, and the SSE ``/event`` endpoint. The installed
OpenAPI-generated SDK at ``~/.opencode/node_modules/@opencode-ai/sdk`` (package
version 1.15.0) describes ``/event`` as a JSON SSE stream whose records have a
``type`` and ``properties`` object; text, tool, usage, idle, and error records
are represented by the ``message.part.*``, ``session.next.*``,
``message.updated``, ``session.idle``, and ``session.error`` variants.

The adapter subscribes to that SSE stream before posting a prompt, so callers
see progress instead of waiting for the blocking prompt response. A supplied
``session_id`` is sent to the existing session; no history is replayed.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

from adk_harness.coding.protocol import HarnessSpec, HarnessTurn

__all__ = ["OpenCodeHarness"]


def _text(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _event_parts(event: dict[str, Any]) -> tuple[str | None, dict[str, Any]]:
    event_type = event.get("type")
    properties = event.get("properties")
    if isinstance(event_type, str) and isinstance(properties, dict):
        return event_type, properties

    # The generated OpenAPI types also expose the durable "sync" event shape.
    data = event.get("data")
    if event_type == "sync" and isinstance(data, dict):
        name = event.get("name")
        return (name.removesuffix(".1") if isinstance(name, str) else None), data

    return (event_type if isinstance(event_type, str) else None), {}


def _tool_content(properties: dict[str, Any]) -> str | None:
    content = properties.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = [item.get("text") for item in content if isinstance(item, dict)]
        text = "\n".join(part for part in parts if isinstance(part, str))
        return text or None
    return _text(properties.get("output")) or _text(properties.get("error"))


def _event_to_turn(  # noqa: PLR0915
    event: dict[str, Any],
    tool_names: dict[str, str],
) -> tuple[HarnessTurn | None, bool]:
    """Map one OpenCode event to a turn and report whether the run is terminal."""
    event_type, properties = _event_parts(event)
    if event_type is None:
        return None, False

    if event_type == "session.idle":
        return None, True
    if event_type == "session.error":
        error = properties.get("error")
        if isinstance(error, dict):
            message = _text(error.get("message")) or _text(error.get("name"))
        else:
            message = _text(error)
        return HarnessTurn(kind="error", text=message or "OpenCode session error", raw=event), True

    if event_type in {"session.next.text.delta", "session.next.reasoning.delta"}:
        return HarnessTurn(kind="text", text=_text(properties.get("delta")), raw=event), False
    if event_type in {"session.next.text.ended", "session.next.reasoning.ended"}:
        return HarnessTurn(kind="text", text=_text(properties.get("text")), raw=event), False

    if event_type == "message.part.delta":
        if properties.get("field") in {"text", "reasoning"}:
            return HarnessTurn(kind="text", text=_text(properties.get("delta")), raw=event), False
        return None, False

    if event_type == "message.part.updated":
        part = properties.get("part")
        if not isinstance(part, dict):
            return None, False
        part_type = part.get("type")
        if part_type in {"text", "reasoning"}:
            return HarnessTurn(kind="text", text=_text(part.get("text")), raw=event), False
        if part_type != "tool":
            return None, False
        call_id = _text(part.get("callID")) or ""
        name = _text(part.get("tool")) or tool_names.get(call_id) or "tool"
        tool_names[call_id] = name
        state = part.get("state")
        if not isinstance(state, dict):
            return None, False
        status = state.get("status")
        if status in {"pending", "running"}:
            input_args = state.get("input")
            return HarnessTurn(
                kind="tool_call",
                tool_name=name,
                tool_args=input_args if isinstance(input_args, dict) else {},
                raw=event,
            ), False
        if status in {"completed", "error"}:
            return HarnessTurn(
                kind="tool_result",
                tool_name=name,
                text=_text(state.get("output")) or _text(state.get("error")),
                raw=event,
            ), False
        return None, False

    if event_type == "session.next.tool.called":
        call_id = _text(properties.get("callID")) or ""
        name = _text(properties.get("tool")) or "tool"
        tool_names[call_id] = name
        args = properties.get("input")
        return HarnessTurn(
            kind="tool_call",
            tool_name=name,
            tool_args=args if isinstance(args, dict) else {},
            raw=event,
        ), False

    if event_type == "session.next.tool.input.ended":
        call_id = _text(properties.get("callID")) or ""
        name = tool_names.get(call_id, "tool")
        raw_args = properties.get("text")
        try:
            args = json.loads(raw_args) if isinstance(raw_args, str) else {}
        except json.JSONDecodeError:
            args = {}
        return HarnessTurn(
            kind="tool_call",
            tool_name=name,
            tool_args=args if isinstance(args, dict) else {},
            raw=event,
        ), False

    if event_type in {
        "session.next.tool.progress",
        "session.next.tool.success",
        "session.next.tool.failed",
        "session.next.shell.ended",
    }:
        call_id = _text(properties.get("callID")) or ""
        return HarnessTurn(
            kind="tool_result",
            tool_name=tool_names.get(call_id, "shell" if "shell" in event_type else "tool"),
            text=_tool_content(properties),
            raw=event,
        ), False

    if event_type == "session.next.shell.started":
        call_id = _text(properties.get("callID")) or ""
        tool_names[call_id] = "shell"
        return HarnessTurn(
            kind="tool_call",
            tool_name="shell",
            tool_args={"command": properties.get("command", "")},
            raw=event,
        ), False

    if event_type in {"message.updated", "session.next.step.ended"}:
        info = properties.get("info") if event_type == "message.updated" else properties
        if not isinstance(info, dict):
            return None, False
        tokens = info.get("tokens")
        cost = info.get("cost")
        if isinstance(tokens, dict) or isinstance(cost, (int, float)):
            usage: dict[str, Any] = {}
            if isinstance(tokens, dict):
                usage["tokens"] = tokens
            if isinstance(cost, (int, float)):
                usage["cost"] = cost
            return HarnessTurn(kind="usage", tool_args=usage, raw=event), False
        return None, False

    if event_type in {"session.next.step.failed", "session.next.retried"}:
        error = properties.get("error")
        message = _text(error.get("message")) if isinstance(error, dict) else _text(error)
        return HarnessTurn(kind="error", text=message or event_type, raw=event), False

    return None, False


class OpenCodeHarness:
    """Stream an already-running OpenCode server over its HTTP API."""

    def __init__(
        self,
        *,
        base_url: str = "http://127.0.0.1:4096",
        model: str | None = None,
        agent: str | None = None,
        timeout: float = 30.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._agent = agent
        self._timeout = timeout
        self._active_runs: list[dict[str, Any]] = []
        self.spec = HarnessSpec(id="opencode", version="unknown", available=False)

    async def discover(self) -> HarnessSpec:
        try:
            import httpx
        except ImportError as exc:
            self.spec = HarnessSpec(
                id="opencode",
                version="unknown",
                available=False,
                detail=f"httpx is required for the OpenCode adapter: {exc}",
            )
            return self.spec

        try:
            async with httpx.AsyncClient(base_url=self._base_url, timeout=self._timeout) as client:
                response = await client.get("/global/health")
                if response.status_code >= 400:
                    raise RuntimeError(f"HTTP {response.status_code}")
                data = response.json()
                if not isinstance(data, dict) or data.get("healthy") is not True:
                    raise RuntimeError(f"unhealthy response: {data!r}")
                version = data.get("version")
                self.spec = HarnessSpec(
                    id="opencode",
                    version=version if isinstance(version, str) else "unknown",
                    capabilities=("text", "tool_call", "tool_result", "usage", "session_resume"),
                    available=True,
                    detail=f"{self._base_url} reported healthy",
                )
        except Exception as exc:
            self.spec = HarnessSpec(
                id="opencode",
                version="unknown",
                available=False,
                detail=f"OpenCode server {self._base_url!r} could not be reached: {exc}",
            )
        return self.spec

    def run(
        self,
        prompt: str,
        *,
        cwd: str,
        session_id: str | None = None,
    ) -> AsyncIterator[HarnessTurn]:
        holder: dict[str, Any] = {}
        stream = self._run(prompt, cwd=cwd, session_id=session_id, holder=holder)
        holder["stream"] = stream
        return stream

    async def _run(  # noqa: PLR0915
        self,
        prompt: str,
        *,
        cwd: str,
        session_id: str | None,
        holder: dict[str, Any],
    ) -> AsyncIterator[HarnessTurn]:
        try:
            import httpx
        except ImportError as exc:
            yield HarnessTurn(kind="error", text=f"httpx is required: {exc}", raw=exc)
            return

        client = httpx.AsyncClient(base_url=self._base_url, timeout=self._timeout)
        holder["client"] = client
        self._active_runs.append(holder)
        tool_names: dict[str, str] = {}
        try:
            async with client:
                if session_id is None:
                    response = await client.post("/session", params={"directory": cwd})
                    if response.status_code >= 400:
                        yield HarnessTurn(
                            kind="error",
                            text=f"OpenCode session creation failed: HTTP {response.status_code}",
                            raw=response,
                        )
                        return
                    session = response.json()
                    session_id = session.get("id") if isinstance(session, dict) else None
                    if not isinstance(session_id, str) or not session_id:
                        yield HarnessTurn(
                            kind="error", text="OpenCode session response had no id", raw=session
                        )
                        return

                async with client.stream(
                    "GET", "/event", params={"directory": cwd}
                ) as response:
                    holder["response"] = response
                    holder["prompt_task"] = asyncio.create_task(
                        client.post(
                            f"/session/{session_id}/message",
                            params={"directory": cwd},
                            json=self._prompt_body(prompt),
                        )
                    )
                    data_lines: list[str] = []
                    async for raw_line in response.aiter_lines():
                        line = (
                            raw_line.decode(errors="replace")
                            if isinstance(raw_line, bytes)
                            else raw_line
                        )
                        if line.startswith("data:"):
                            data_lines.append(line[5:].lstrip())
                            continue
                        if line.strip() or not data_lines:
                            continue
                        turn, terminal = _decode_sse_event(data_lines, session_id, tool_names)
                        if turn is not None:
                            yield turn
                        if terminal:
                            data_lines = []
                            break
                        data_lines = []
                    if data_lines:
                        turn, _ = _decode_sse_event(data_lines, session_id, tool_names)
                        if turn is not None:
                            yield turn

                try:
                    prompt_response = await holder["prompt_task"]
                    if prompt_response.status_code >= 400:
                        yield HarnessTurn(
                            kind="error",
                            text=f"OpenCode prompt failed: HTTP {prompt_response.status_code}",
                            raw=prompt_response,
                        )
                except Exception as exc:
                    yield HarnessTurn(kind="error", text=str(exc), raw=exc)
        except Exception as exc:
            yield HarnessTurn(kind="error", text=str(exc), raw=exc)
        finally:
            task = holder.get("prompt_task")
            if task is not None and not task.done():
                task.cancel()
            if task is not None:
                try:
                    await task
                except asyncio.CancelledError:
                    pass
            if holder in self._active_runs:
                self._active_runs.remove(holder)

    def _prompt_body(self, prompt: str) -> dict[str, Any]:
        body: dict[str, Any] = {"parts": [{"type": "text", "text": prompt}]}
        if self._agent is not None:
            body["agent"] = self._agent
        if self._model is not None:
            provider, separator, model = self._model.partition("/")
            if separator:
                body["model"] = {"providerID": provider, "modelID": model}
        return body

    async def aclose(self) -> None:
        runs, self._active_runs = self._active_runs, []
        for holder in runs:
            task = holder.get("prompt_task")
            if task is not None and not task.done():
                task.cancel()
            for resource in (holder.get("response"), holder.get("client")):
                close = getattr(resource, "aclose", None)
                if close is not None:
                    await close()
            stream = holder.get("stream")
            if stream is not None:
                await stream.aclose()


def _decode_sse_event(
    data_lines: list[str],
    session_id: str,
    tool_names: dict[str, str],
) -> tuple[HarnessTurn | None, bool]:
    """Decode one SSE record; the caller keeps stream control around it."""
    try:
        event = json.loads("\n".join(data_lines))
    except json.JSONDecodeError:
        return None, False
    if not isinstance(event, dict):
        return None, False
    event_payload = event.get("payload")
    if isinstance(event_payload, dict) and "type" not in event:
        event = event_payload
    _, event_properties = _event_parts(event)
    event_session = event_properties.get("sessionID")
    if event_session is not None and event_session != session_id:
        return None, False
    turn, terminal = _event_to_turn(event, tool_names)
    return turn, terminal
