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
    for case in root.iter('testcase'):
        for error in list(case.findall('error')) + list(case.findall('failure')):
            identity = case.get('classname', '') + '.' + case.get('name', '')
            text = identity + '\n' + (error.text or error.get('message', ''))
            if len(text) > 6000:
                text = text[:3000] + '\n[exception summary truncated]\n' + text[-3000:]
            print('::error title=Offline test failed::' + escape(text))


if __name__ == '__main__':
    for argument in sys.argv[1:]:
        annotate(argument)
