"""Conservative structured tool outcomes shared with negative_outcome.ts."""
import re

FLAGS = ('exported', 'finalized', 'staged', 'ok', 'success', 'done')

def negative_outcome(value):
    if not isinstance(value, dict): return {'status':'unknown', 'failures':[]}
    flags = [value[k] for k in FLAGS if k in value]
    code, checks = value.get('validation_error'), value.get('failed_checks')
    error=value.get('error');has_error=error is not None and error is not False and error!=''
    valid = lambda s: isinstance(s,str) and re.fullmatch(r'[a-zA-Z][a-zA-Z0-9_:-]{0,127}',s) is not None
    if code is not None and not valid(code) or checks is not None and (not isinstance(checks,list) or len(checks)>32 or not all(valid(c) for c in checks)):
        return {'status':'unknown', 'failures':[]}
    failures = ([{'source':'validation_error','code':code}] if code else []) + [{'source':'failed_checks','code':c} for c in sorted(set(checks or []))]
    if any(v is True for v in flags) and (failures or any(v is False for v in flags) or has_error):
        return {'status':'unknown', 'failures':[]}
    if failures:return {'status':'failure','failures':failures}
    if any(v is False for v in flags) or has_error:return {'status':'failure_unknown','failures':[]}
    return {'status':'success' if any(v is True for v in flags) else 'unknown','failures':[]}
