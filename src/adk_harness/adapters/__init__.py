"""Bundled adapters.

Importing this package is always safe, on any machine. Each adapter defers its
vendor import into `discover()` (contract rule 2), so a harness you have not
installed reports `available=False` rather than breaking the import.

Four shapes, one protocol: Codex is a CLI subprocess, Claude Code is a Python
SDK over a CLI, opencode is an HTTP server with an SSE event stream, and
Antigravity is a Python SDK over a bundled compiled runtime. Two adapters can
accidentally agree with each other; four that disagree structurally and still
satisfy the same contract is evidence that the contract is real.
"""

from adk_harness.adapters.antigravity import AntigravityHarness
from adk_harness.adapters.claude_code import ClaudeCodeHarness
from adk_harness.adapters.codex import CodexHarness
from adk_harness.adapters.opencode import OpenCodeHarness

__all__ = [
    "AntigravityHarness",
    "ClaudeCodeHarness",
    "CodexHarness",
    "OpenCodeHarness",
]
