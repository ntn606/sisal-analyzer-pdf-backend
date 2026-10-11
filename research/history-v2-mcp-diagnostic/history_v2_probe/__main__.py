"""Offline JSON CLI or isolated stdio MCP. Live acquisition is not automatic."""
import argparse,json,sys
from datetime import datetime
from pathlib import Path
from .service import ProbeService

def main():
 parser=argparse.ArgumentParser()
 parser.add_argument('--mcp',action='store_true');parser.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1])
 parser.add_argument('--palinsesto');parser.add_argument('--avvenimento');parser.add_argument('--match-date')
 parser.add_argument('--replay-at',help='Operator-only offline replay timestamp, never an MCP argument')
 args=parser.parse_args()
 if args.mcp:
  if args.replay_at:parser.error('--replay-at is unavailable with MCP')
  from .mcp_server import create_server
  create_server(args.root).run(transport='stdio');return 0
 clock=None
 if args.replay_at:
  try:
   stamp=datetime.fromisoformat(args.replay_at.replace('Z','+00:00'))
   if stamp.tzinfo is None:raise ValueError
  except ValueError:print(json.dumps({'status':'temporal_unverified','diagnostic_only':True,'ready_for_analysis':False,'ready_for_quant':False,'blockers':['invalid_replay_timestamp']}));return 2
  clock=lambda:stamp
 output=ProbeService(args.root,clock).football_history_v2_probe(args.palinsesto,args.avvenimento,args.match_date)
 if args.replay_at:output['execution_mode']='offline_replay'
 print(json.dumps(output,ensure_ascii=False,indent=2));return 0
if __name__=='__main__':raise SystemExit(main())
