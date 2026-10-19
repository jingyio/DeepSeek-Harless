"""Preview or explicitly run one historical management graph re-certification."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.adapters.continuous_rsi import load_config, private
from src.adapters.management_recertification import recertify
from src.motif_core.offline.experience_registry import check_motif_certificate, read, sha


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=ROOT/'.local/rsi/daily-management-real-v3.json')
    for name in ('old-policy', 'old-certificate', 'template', 'job'):
        parser.add_argument('--'+name, type=Path, required=True)
    parser.add_argument('--call-model', action='store_true')
    args = parser.parse_args()
    cfg = load_config(args.config)
    old = read(private(args.old_policy))
    check_motif_certificate(old, private(args.old_certificate), sha(args.old_policy))
    if not args.call_model:
        print(json.dumps({'paid': False, 'old_policy_digest': old['policy_digest'],
                          'tools': [n['tool'] for n in old['artifact'].get('nodes', [])],
                          'adapter': cfg.get('adapter'), 'limits': cfg['limits'],
                          'series_cap_usd': cfg['series_cap_usd'],
                          'shared_learning_cap_usd': cfg['learning_cap_usd']}, ensure_ascii=False))
        return
    loader = importlib.util.spec_from_file_location('management_private_key', ROOT/'scenarios/literature-notes/run-live.py')
    module = importlib.util.module_from_spec(loader)
    loader.loader.exec_module(module)
    os.environ['DEEPSEEK_API_KEY'] = module.load_key(module.KEY_FILE, os.environ)
    result = recertify(args.config, args.old_policy, args.old_certificate, args.template, args.job)
    print(json.dumps(result, ensure_ascii=False))
    if result.get('status') != 'activated':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
