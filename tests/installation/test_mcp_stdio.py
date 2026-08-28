"""Exercise the installed CLI over the actual MCP transport, without live APIs."""

import asyncio
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def test_cli_serves_mcp_without_credentials(tmp_path: Path) -> None:
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "adk_harness", "serve"],
        cwd=str(tmp_path),
        env={
            "ADK_SERVICES": "",
            "ADK_HARNESSES": "0",
            "ADK_LEDGER": "0",
            # Never fall back to developer credentials, even if discovery changes.
            "GOOGLE_APPLICATION_CREDENTIALS": str(tmp_path / "absent-credentials.json"),
        },
    )
    async with asyncio.timeout(30), stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            names = {tool.name for tool in tools.tools}
            assert names == {"governance_audit", "armor_findings", "ledger_recent"}
            result = await session.call_tool("governance_audit", {})
            assert not result.isError
            assert result.content[0].text == "No decisions yet."
