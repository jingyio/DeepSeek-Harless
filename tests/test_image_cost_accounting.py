"""Free provider file uploads cannot invalidate known model-usage accounting."""
import json
from src.adapters.continuous_rsi import ledger_accounting
def test_file_uploads_remain_recorded_without_becoming_model_requests(tmp_path):
    p=tmp_path/'ledger.jsonl';rows=[
        {'request_id':1,'reserved_upper_usd':.01,'observed_peak_usd':.002},
        {'kind':'files_api','method':'POST','path':'/v1/files','response_status':200},
        {'kind':'files_api','method':'DELETE','path':'/v1/files/test','response_status':503},
        {'request_id':2,'reserved_upper_usd':.02,'observed_peak_usd':.003},
        {'kind':'budget_denied'}]
    original=''.join(json.dumps(r)+'\n' for r in rows);p.write_text(original)
    v=ledger_accounting(p,{'upstream_requests':2,'budget_accounted_usd':.005})
    assert v['accounting_complete'] and v['observed_usage_complete']
    assert v['requests']==2 and v['free_files_api_requests']==2 and v['cost_upper_usd']==.005
    assert p.read_text()==original

def test_real_missing_model_usage_still_keeps_its_original_fee_reservation(tmp_path):
    p=tmp_path/'ledger.jsonl';p.write_text(json.dumps({'request_id':1,'reserved_upper_usd':.02})+'\n'+json.dumps({'kind':'files_api'})+'\n')
    v=ledger_accounting(p,{'upstream_requests':1,'budget_accounted_usd':.02})
    assert v['accounting_complete'] and not v['observed_usage_complete'] and v['missing_observed_usage_requests']==1
    assert v['cost_upper_usd']==.02
