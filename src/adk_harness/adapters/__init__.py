"""Bundled adapters.

Importing this package is always safe, on any machine. Each adapter defers its
vendor import into `discover()` (contract rule 2), so a harness you have not
installed reports `available=False` rather than breaking the import.
"""

from adk_harness.adapters.claude_code import ClaudeCodeHarness
from adk_harness.adapters.codex import CodexHarness

__all__ = ["ClaudeCodeHarness", "CodexHarness"]
