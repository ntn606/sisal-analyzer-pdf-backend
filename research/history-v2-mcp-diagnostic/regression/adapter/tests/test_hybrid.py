"""HYBRID: real FD snapshots plus synthetic Sisal/API-Football IDs and reviews."""
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import socket
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from scenarios import scenario
from identity_adapter import probe
from identity_adapter.cli import main


class HybridTests(unittest.TestCase):
    """No test here verifies a real Sisal/API-Football/FD identity bridge."""
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        guard=patch.object(socket.socket,'connect',side_effect=AssertionError('Network forbidden'))
        guard.start();self.addCleanup(guard.stop)

    def run_case(self,case):
        request,registry,dataset=scenario(self.root,case)
        return probe(request,registry,dataset,self.root)

    def test_hybrid_arsenal_real_history_pl_and_cl_synthetic_linkage(self):
        result=self.run_case('arsenal')
        self.assertEqual(result['status'],'diagnostic_available')
        history=result['histories']['away']
        self.assertEqual(history['team']['provider_id'],57)
        self.assertEqual([m['match_id'] for m in history['matches']],[560593,560586,560577,575333,560570])
        self.assertEqual({m['competition']['code'] for m in history['matches']},{'PL','CL'})
        self.assertEqual(history['statistics']['overall']['goals_for'],7)
        self.assertEqual(result['verification_scope'],'synthetic_only')

    def test_hybrid_psg_real_history_fl1_and_cl_synthetic_linkage(self):
        result=self.run_case('psg')
        self.assertEqual(result['status'],'diagnostic_available')
        history=result['histories']['home']
        self.assertEqual(history['team']['provider_id'],524)
        self.assertEqual([m['match_id'] for m in history['matches']],[559675,559691,575332,559697,559702])
        self.assertEqual(history['statistics']['overall']['goals_for'],12)
        self.assertFalse(result['statistics_usable_in_production'])

    def test_hybrid_roma_real_insufficient_history_preserved(self):
        result=self.run_case('roma')
        self.assertEqual(result['status'],'insufficient_history')
        self.assertEqual(result['histories']['home']['counts']['selected_results'],1)
        self.assertEqual(result['histories']['home']['history_status'],'insufficient_history')
        self.assertIsNone(result['histories']['home']['statistics'])

    def test_hybrid_leipzig_real_four_results_preserved(self):
        result=self.run_case('leipzig')
        self.assertEqual(result['status'],'insufficient_history')
        self.assertEqual(result['histories']['home']['counts']['selected_results'],4)

    def test_hybrid_real_only_cannot_certify_synthetic_bridge(self):
        request,registry,dataset=scenario(self.root,'arsenal')
        request['evidence_mode']='real_only'
        result=probe(request,registry,dataset,self.root)
        self.assertEqual(result['status'],'identity_unverified')
        self.assertEqual(result['histories'],{})
        self.assertFalse(result['diagnostic_statistics_allowed'])

    def test_hybrid_real_histories_do_not_certify_backtest_publication(self):
        request,registry,dataset=scenario(self.root,'psg')
        request.update(purpose='historical_backtest',analysis_at=request['verified_at'])
        result=probe(request,registry,dataset,self.root)
        self.assertEqual(result['status'],'temporal_unverified')
        self.assertFalse(result['temporal']['backtest_availability_verified'])
        self.assertTrue(result['temporal']['reasons'])
        self.assertIsNone(result['histories']['home']['statistics'])

    def test_hybrid_cli_emits_json_and_never_enables_quant(self):
        request,registry,_=scenario(self.root,'arsenal')
        req=self.root/'request.json';reg=self.root/'registry.json'
        req.write_text(json.dumps(request));reg.write_text(json.dumps(registry))
        output=io.StringIO()
        with redirect_stdout(output):
            code=main(['--request',str(req),'--registry',str(reg),'--evidence',str(self.root)])
        result=json.loads(output.getvalue())
        self.assertEqual(code,0)
        self.assertEqual(result['status'],'diagnostic_available')
        self.assertFalse(result['ready_for_quant'])
        self.assertEqual(result['verification_scope'],'synthetic_only')


if __name__=='__main__':unittest.main()
