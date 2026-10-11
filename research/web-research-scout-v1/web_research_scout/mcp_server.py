"""One cache-only stdio diagnostic tool. No live collection tool or HTTP service."""

import json
from pathlib import Path
from typing import Any

import anyio
from mcp.server.fastmcp import FastMCP
from mcp.types import CallToolResult, TextContent, ToolAnnotations

from .probe import DiagnosticProbe


class SafeMCP(FastMCP):
    async def list_tools(self):
        tools = await super().list_tools()
        contracts = Path(__file__).resolve().parents[1] / "contracts"
        for tool in tools:
            tool.inputSchema = json.loads(
                (contracts / "request.schema.json").read_text()
            )
            tool.outputSchema = json.loads(
                (contracts / "response.schema.json").read_text()
            )
        return tools

    async def call_tool(self, name, arguments):
        try:
            if (
                name != "football_web_research_v1_probe"
                or not isinstance(arguments, dict)
                or set(arguments) != set(("palinsesto", "avvenimento", "match_date"))
                or any(type(v) is not str for v in arguments.values())
            ):
                raise ValueError
            return await super().call_tool(name, arguments)
        except Exception:
            return CallToolResult(
                isError=True,
                content=[TextContent(type="text", text="invalid_tool_request")],
            )


def create_server(probe=None):
    probe = probe or DiagnosticProbe(Path(__file__).resolve().parents[1] / "cache")
    server = SafeMCP(
        "Web Research Scout V1 — isolated diagnostics", log_level="CRITICAL"
    )

    @server.tool(
        name="football_web_research_v1_probe",
        structured_output=True,
        annotations=ToolAnnotations(
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=False,
            openWorldHint=False,
        ),
    )
    async def football_web_research_v1_probe(
        palinsesto: str, avvenimento: str, match_date: str
    ) -> dict[str, Any]:
        """Read reviewed cached evidence. Unknown and unconfirmed information remains explicit."""
        return await anyio.to_thread.run_sync(
            probe.football_web_research_v1_probe, palinsesto, avvenimento, match_date
        )

    return server


def main():
    create_server().run(transport="stdio")


if __name__ == "__main__":
    main()
