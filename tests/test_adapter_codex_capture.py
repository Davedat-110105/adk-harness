"""Replay real Codex output, captured from the CLI, not invented.

Why this file exists
--------------------
`tests/test_adapter_codex.py` had eleven passing tests while the adapter
produced **zero turns** against the real `codex` binary. Every fixture in it was
hand-built as `{"id": ..., "msg": {...}}` — an envelope the vendor has never
emitted. The tests proved the parser accepted the schema the tests invented, and
nothing more.

The missing property was not more assertions. It was a fixture nobody wrote by
hand. `tests/fixtures/codex_exec_real.jsonl` is stdout captured verbatim from:

    echo "Run 'ls src/adk_harness' and tell me how many .py files there are." \\
        | codex exec --json -C . -

against codex-cli 0.149.1 on 2026-08-25. If the vendor changes its envelope, or
someone rewrites the mapping against a remembered shape, these tests fail —
which is the whole point.

Re-capture with the command above when the CLI's format changes. Do not edit the
fixture by hand; a hand-edited capture is just a fake with extra steps.
"""

from __future__ import annotations

import json
from pathlib import Path

from adk_harness.adapters.codex import _event_to_turn

FIXTURE = Path(__file__).parent / "fixtures" / "codex_exec_real.jsonl"


def _turns() -> list:
    return [
        turn
        for turn in (
            _event_to_turn(json.loads(line))
            for line in FIXTURE.read_text().splitlines()
            if line.strip()
        )
        if turn is not None
    ]


def test_real_output_produces_turns_at_all() -> None:
    """The assertion that would have caught the shipped bug.

    Zero turns from a successful run means the adapter is not speaking the
    vendor's language, however well its unit tests pass.
    """
    assert _turns(), "a successful codex run must yield at least one turn"


def test_the_assistant_text_survives() -> None:
    texts = [t.text for t in _turns() if t.kind == "text"]
    assert any("8" in (t or "") for t in texts), texts


def test_a_shell_command_becomes_a_call_and_a_result() -> None:
    turns = _turns()
    calls = [t for t in turns if t.kind == "tool_call"]
    results = [t for t in turns if t.kind == "tool_result"]

    assert calls and results
    assert "ls src/adk_harness" in (calls[0].tool_name or "")
    # The command's real output has to reach the caller, not just its name.
    assert "protocol.py" in (results[0].text or "")


def test_the_call_precedes_its_result() -> None:
    kinds = [t.kind for t in _turns()]
    assert kinds.index("tool_call") < kinds.index("tool_result")


def test_usage_is_reported_once_at_the_end() -> None:
    turns = _turns()
    usage = [t for t in turns if t.kind == "usage"]
    assert len(usage) == 1
    assert turns[-1].kind == "usage"
    assert "input_tokens" in (usage[0].text or "")


def test_startup_notices_are_not_reported_as_errors() -> None:
    """The capture contains four `error` items that are warnings about config.

    Surfacing them as `kind="error"` would make every healthy run look failed,
    and a caller that trusts the error channel would be wrong every time.
    """
    raw = [json.loads(line) for line in FIXTURE.read_text().splitlines() if line.strip()]
    benign = [
        e
        for e in raw
        if (e.get("item") or {}).get("type") == "error"
    ]
    assert len(benign) == 4, "fixture should still contain the startup notices"
    assert not [t for t in _turns() if t.kind == "error"]


def test_every_turn_keeps_the_vendor_payload() -> None:
    """Contract rule 4: `raw` carries the vendor event untouched."""
    for turn in _turns():
        assert isinstance(turn.raw, dict)
        assert "type" in turn.raw
