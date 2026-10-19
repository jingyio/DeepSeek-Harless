"""Verify and atomically refresh the gateway's private owner launch URL."""
import argparse
import json
import os
import re
import tempfile
import urllib.error
import urllib.request
from pathlib import Path


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args):
        return None


def verify_access(url, port):
    # Never send a launch credential to a host supplied by a log or redirect.
    if not isinstance(port, int) or isinstance(port, bool) or not 1 <= port <= 65535:
        raise ValueError('Invalid owner port')
    if not re.fullmatch(r'http://127\.0\.0\.1:' + str(port) + r'/\?token=[A-Za-z0-9_-]{40,100}', url):
        raise ValueError('Invalid owner launch URL')
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())

    def request(target, headers=None):
        try:
            return opener.open(urllib.request.Request(target, headers=headers or {}), timeout=10)
        except urllib.error.HTTPError as response:
            return response

    with request(url) as response:
        cookies = response.headers.get_all('Set-Cookie') or []
        cookie = next((v.split(';', 1)[0] for v in cookies if re.match(r'dsh-auth-[^=;]+=', v)), None)
        if response.code != 303 or not cookie:
            raise RuntimeError('Owner launch authentication failed')
    with request('http://127.0.0.1:%s/' % port, {'Cookie': cookie}) as response:
        if response.code != 200:
            raise RuntimeError('Authenticated owner page unavailable')


def sync_owner_access(config_path, startup_log, log_offset=0):
    config = json.loads(Path(config_path).read_text(encoding='utf-8'))
    if log_offset < 0:
        raise ValueError('Invalid startup log offset')
    with Path(startup_log).open('rb') as log:
        log.seek(log_offset)
        text = log.read().decode('utf-8', errors='replace')
    urls = re.findall(r'^dsh web: (\S+)\s*$', text, re.MULTILINE)
    if len(urls) != 1:
        raise RuntimeError('Expected one launch URL from the current startup log slice')
    verify_access(urls[0], config['ownerPort'])
    target = Path(config['ownerTokenFile'])
    descriptor, temporary = tempfile.mkstemp(prefix=target.name + '.', dir=str(target.parent))
    try:
        with os.fdopen(descriptor, 'w', encoding='utf-8', newline='\n') as output:
            os.chmod(temporary, 0o600)
            output.write(urls[0] + '\n')
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, target)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return {'owner_launch_authenticated': True, 'owner_page_status': 200, 'model_requests': 0}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', required=True)
    parser.add_argument('--startup-log')
    parser.add_argument('--log-offset', type=int, default=0)
    parser.add_argument('--check', action='store_true', help='verify the configured URL without writing')
    args = parser.parse_args()
    try:
        if args.check:
            config = json.loads(Path(args.config).read_text(encoding='utf-8'))
            verify_access(Path(config['ownerTokenFile']).read_text(encoding='utf-8').strip(), config['ownerPort'])
            result = {'owner_launch_authenticated': True, 'owner_page_status': 200, 'model_requests': 0}
        else:
            if not args.startup_log:
                parser.error('--startup-log is required when refreshing')
            result = sync_owner_access(args.config, args.startup_log, args.log_offset)
        print(json.dumps(result))
    except Exception as error:
        # HTTP exceptions can contain the credential URL. Keep it out of logs.
        parser.exit(1, 'Owner access check failed (%s)\n' % type(error).__name__)


if __name__ == '__main__':
    main()
