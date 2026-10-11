"""Actual MCP SDK stdio exchange against saved evidence, without provider calls."""
from pathlib import Path
from datetime import datetime,timedelta
import sys,unittest,json
from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client
ROOT=Path(__file__).resolve().parents[1]
class MCPStdioTests(unittest.IsolatedAsyncioTestCase):
 data_origin='real_saved_evidence_native_mcp_stdio_frozen_clock_replay_no_provider_calls'
 async def test_single_tool_three_arguments_and_real_structured_output(self):
  stamp=max(datetime.fromisoformat(json.loads(p.read_text())['verified_at']) for p in (ROOT/'cases').glob('*/request-asof-observation.json'))+timedelta(seconds=1)
  # The process launch is trusted test configuration, not an MCP argument.
  code='from datetime import datetime; from history_v2_probe import ProbeService; from history_v2_probe.mcp_server import create_server; stamp=datetime.fromisoformat('+repr(stamp.isoformat())+'); create_server(service=ProbeService('+repr(str(ROOT))+',clock=lambda:stamp)).run(transport="stdio")'
  params=StdioServerParameters(command=sys.executable,args=['-c',code],cwd=str(ROOT),env={'API_FOOTBALL_KEY':'','FOOTBALL_DATA_TOKEN':''})
  with (ROOT/'reports/mcp-stdio-server.log').open('w') as log:
   async with stdio_client(params,errlog=log) as (reader,writer):
    async with ClientSession(reader,writer) as session:
     await session.initialize();listed=await session.list_tools()
     self.assertEqual([t.name for t in listed.tools],['football_history_v2_probe'])
     self.assertEqual(set(listed.tools[0].inputSchema['properties']),{'palinsesto','avvenimento','match_date'})
     for avv in ('1885','2282'):
      result=await session.call_tool('football_history_v2_probe',{'palinsesto':'36411','avvenimento':avv,'match_date':'2026-10-12'},read_timeout_seconds=timedelta(seconds=15))
      self.assertFalse(result.isError);payload=result.structuredContent
      self.assertEqual(payload['status'],'diagnostic_available');self.assertTrue(payload['diagnostic_only']);self.assertFalse(payload['ready_for_analysis']);self.assertFalse(payload['ready_for_quant'])
      self.assertEqual([h['counts']['selected_results'] for h in payload['histories'].values()],[5,5]);self.assertEqual(payload['provenance']['new_api_requests'],0)
     missing=await session.call_tool('football_history_v2_probe',{'palinsesto':'36411','avvenimento':'1','match_date':'2026-10-12'},read_timeout_seconds=timedelta(seconds=15))
     self.assertEqual(missing.structuredContent['status'],'identity_unverified')
