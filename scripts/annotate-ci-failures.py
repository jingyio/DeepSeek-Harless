"""Expose offline test errors through public check annotations, not secrets/logs."""
from pathlib import Path
import sys
import xml.etree.ElementTree as ET


def escape(value):
    return value.replace('%', '%25').replace('\r', '%0D').replace('\n', '%0A')


def annotate(path):
    path = Path(path)
    if not path.is_file():
        print('No Python result file; failure may be before pytest or in Node tests.')
        return
    if path.stat().st_size > 32_000_000:
        raise ValueError('CI result file exceeds diagnostic bound')
    root = ET.fromstring(path.read_bytes())
    entries = []
    for case in root.iter('testcase'):
        for error in list(case.findall('error')) + list(case.findall('failure')):
            identity = case.get('classname', '') + '.' + case.get('name', '')
            body = error.text or error.get('message', '')
            entries.append((identity, body))
    if entries:
        # A single index exposes all failures even when individual annotations
        # are capped by the provider. Detailed diagnostics remain in the log.
        index = '\n'.join(identity + ': ' + next((s.strip() for s in body.splitlines() if s.strip()), '')[:200]
                          for identity, body in entries)
        index = index.encode('utf-8')[:40000].decode('utf-8', errors='ignore')
        print('::error title=Offline failures index::' + escape(str(len(entries)) + ' failed tests\n' + index))
    for identity, body in entries[:9]:
            text = identity + '\n' + body
            if len(text) > 6000:
                text = text[:3000] + '\n[exception summary truncated]\n' + text[-3000:]
            print('::error title=Offline test failed::' + escape(text))


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='backslashreplace')
    for argument in sys.argv[1:]:
        annotate(argument)
