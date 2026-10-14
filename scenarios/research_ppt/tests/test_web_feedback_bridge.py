"""反馈记账读取独立于交付成功；账本夹具仅作回归。"""
import json
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from scenarios.research_ppt.service import ROOT

class FeedbackBridgeTests(unittest.TestCase):
    def test_accounting_does_not_require_successful_delivery_or_live_deck(self):
        parent=ROOT/'.local/runs'
        parent.mkdir(parents=True,exist_ok=True)
        with TemporaryDirectory(dir=parent) as temp:
            directory=Path(temp)
            (directory/'metrics.json').write_text(json.dumps({'upstream_requests':1}))
            (directory/'cost-ledger.jsonl').write_text(json.dumps({'request_id':1,'response_status':200,'observed_peak_usd':.01,
                'response_usage':{'prompt_cache_miss_tokens':12,'prompt_cache_hit_tokens':8,'completion_tokens':5,'total_tokens':25}})+'\n')
            result=subprocess.run([sys.executable,'-m','scenarios.research_ppt.web_feedback_bridge'],cwd=ROOT,
                input=json.dumps({'action':'accounting','run_directory':temp}),text=True,capture_output=True)
            self.assertEqual(result.returncode,0,result.stderr)
            account=json.loads(result.stdout)['accounting']
            self.assertTrue(account['usage_complete'])
            self.assertEqual(account['upstream_requests'],1)
            self.assertEqual(account['observed_proxy_usd'],.01)
            self.assertIsNone(account['provider_bill_usd'])

    def test_accounting_rejects_directory_outside_harness_runs(self):
        with TemporaryDirectory(dir=ROOT/'.local') as temp:
            result=subprocess.run([sys.executable,'-m','scenarios.research_ppt.web_feedback_bridge'],cwd=ROOT,
                input=json.dumps({'action':'accounting','run_directory':temp}),text=True,capture_output=True)
            self.assertNotEqual(result.returncode,0)
