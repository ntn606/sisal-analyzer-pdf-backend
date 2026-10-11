"""Real MCP SDK over local stdio; saved proxy receipts only, no live sites."""

import asyncio
import json
import os
import subprocess
import sys
import unittest
from importlib.metadata import version

from jsonschema import Draft202012Validator, FormatChecker
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from support import ROOT


class MCPAndCLITests(unittest.TestCase):
    data_origin = "real_saved_reference_and_blocked_receipts_sdk_local_stdio"

    def test_exact_sdk_version(self):
        self.assertEqual(version("mcp"), "1.30.0")

    def test_real_stdio_initialize_list_call_and_invalid_identity(self):
        async def run():
            # Empty provider variables even if configured in the operator shell.
            env = {
                k: v
                for k, v in os.environ.items()
                if not any(
                    word in k.upper()
                    for word in (
                        "TOKEN",
                        "SECRET",
                        "PASSWORD",
                        "API_KEY",
                        "FOOTBALL_KEY",
                    )
                )
            }
            env["PYTHONPATH"] = os.environ.get("PYTHONPATH", "")
            params = StdioServerParameters(
                command=sys.executable,
                args=["-m", "web_research_scout", "mcp"],
                cwd=str(ROOT),
                env=env,
            )
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    listing = await session.list_tools()
                    self.assertEqual(
                        [t.name for t in listing.tools],
                        ["football_web_research_v1_probe"],
                    )
                    self.assertTrue(listing.tools[0].annotations.readOnlyHint)
                    self.assertFalse(listing.tools[0].annotations.openWorldHint)
                    self.assertFalse(
                        listing.tools[0].inputSchema["additionalProperties"]
                    )
                    self.assertFalse(
                        listing.tools[0].outputSchema["additionalProperties"]
                    )
                    result = await session.call_tool(
                        "football_web_research_v1_probe",
                        {
                            "palinsesto": "36411",
                            "avvenimento": "1885",
                            "match_date": "2026-10-12",
                        },
                    )
                    self.assertFalse(result.isError)
                    out = result.structuredContent
                    schema = json.loads(
                        (ROOT / "contracts/response.schema.json").read_text()
                    )
                    Draft202012Validator(
                        schema, format_checker=FormatChecker()
                    ).validate(out)
                    self.assertEqual(out["provenance"]["new_web_requests"], 0)
                    self.assertEqual(out["provenance"]["real_web_claims_verified"], 0)
                    self.assertFalse(out["ready_for_analysis"])
                    self.assertFalse(out["ready_for_quant"])
                    invalid = await session.call_tool(
                        "football_web_research_v1_probe",
                        {
                            "palinsesto": "36411",
                            "avvenimento": "unknown",
                            "match_date": "2026-10-12",
                        },
                    )
                    self.assertEqual(
                        invalid.structuredContent["status"], "identity_unverified"
                    )
                    self.assertIsNone(invalid.structuredContent["requested_event"])
                    malformed = await session.call_tool(
                        "football_web_research_v1_probe",
                        {
                            "palinsesto": {"private": "synthetic-hidden-input"},
                            "avvenimento": "1885",
                            "match_date": "2026-10-12",
                        },
                    )
                    self.assertTrue(malformed.isError)
                    self.assertNotIn(
                        "synthetic-hidden-input", malformed.model_dump_json()
                    )
                    unknown = await session.call_tool("synthetic-private-tool-name", {})
                    self.assertTrue(unknown.isError)
                    self.assertNotIn(
                        "synthetic-private-tool-name", unknown.model_dump_json()
                    )

        asyncio.run(run())

    def test_cli_probe_outputs_valid_json(self):
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "web_research_scout",
                "probe",
                "--palinsesto",
                "36411",
                "--avvenimento",
                "2282",
                "--match-date",
                "2026-10-12",
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=20,
            check=True,
        )
        self.assertEqual(completed.stderr, "")
        out = json.loads(completed.stdout)
        self.assertEqual(out["provenance"]["new_web_requests"], 0)
        self.assertFalse(out["ready_for_quant"])

    def test_cli_collection_disabled_without_opt_in(self):
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "web_research_scout",
                "collect",
                "--source",
                "newcastle",
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=20,
            check=True,
        )
        out = json.loads(completed.stdout)
        self.assertEqual(out["reason"], "live_disabled")
