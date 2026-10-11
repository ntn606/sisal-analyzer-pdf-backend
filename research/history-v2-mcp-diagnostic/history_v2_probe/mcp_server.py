"""Single read-only MCP tool, stdio only; no HTTP listener or production import."""
from pathlib import Path
import os
from typing import Any
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from .service import ProbeService

def create_server(root=None,service=None):
 service=service or ProbeService(root or os.environ.get('HISTORY_V2_DATA_ROOT') or Path(__file__).resolve().parents[1])
 server=FastMCP('History Provider V2 — isolated diagnostics',log_level='ERROR')
 @server.tool(name='football_history_v2_probe',structured_output=True,annotations=ToolAnnotations(readOnlyHint=True,destructiveHint=False,idempotentHint=False,openWorldHint=False))
 def football_history_v2_probe(palinsesto:str,avvenimento:str,match_date:str)->dict[str,Any]:
  """Validate a future Sisal event using reviewed real evidence. Diagnostic only."""
  return service.football_history_v2_probe(palinsesto,avvenimento,match_date)
 return server

def main():create_server().run(transport='stdio')
if __name__=='__main__':main()
