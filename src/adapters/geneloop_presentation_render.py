"""Executed only inside a networkless Session sandbox by the TS intake adapter."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


def render(request):
    source = Path('/work/inputs') / request['file']
    if source.parent != Path('/work/inputs') or source.is_symlink() or not source.is_file():
        raise ValueError('invalid_presentation_source')
    data = source.read_bytes()
    if len(data) > 20 * 1024 * 1024 or hashlib.sha256(data).hexdigest() != request['sha256']:
        raise ValueError('presentation_version_changed')
    suffix = request['suffix']
    if suffix not in ('.pptx', '.ppt'):
        raise ValueError('invalid_presentation_type')
    output = Path('/work') / request['directory']
    if output.parent != Path('/work') or not output.name.startswith('input-visual-'):
        raise ValueError('invalid_presentation_output')
    output.mkdir(mode=0o700)  # Never overwrite another derivative.
    with tempfile.TemporaryDirectory(prefix='ppt-input-', dir='/tmp') as temp:
        temp = Path(temp)
        copied = temp / ('reference' + suffix)
        copied.write_bytes(data)
        profile = temp / 'profile'
        (profile / 'user').mkdir(parents=True)
        (profile / 'user/registrymodifications.xcu').write_text('''<?xml version="1.0" encoding="UTF-8"?>
<oor:items xmlns:oor="http://openoffice.org/2001/registry">
<item oor:path="/org.openoffice.Office.Common/Security/Scripting"><prop oor:name="MacroSecurityLevel" oor:op="fuse"><value>3</value></prop><prop oor:name="DisableMacrosExecution" oor:op="fuse"><value>true</value></prop></item>
<item oor:path="/org.openoffice.Office.Common/Security/Links"><prop oor:name="Update" oor:op="fuse"><value>0</value></prop></item>
</oor:items>''', encoding='utf-8')
        binary = '/opt/geneloop/libreoffice/program/soffice.bin'
        def convert(kind, directory):
            completed = subprocess.run([binary, '-env:UserInstallation=' + profile.as_uri(),
                '--headless', '--nologo', '--nodefault', '--norestore', '--nofirststartwizard',
                '--convert-to', kind, '--outdir', str(directory), str(copied)],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=180,
                env={**os.environ, 'SAL_DISABLE_OPENCL': '1', 'SAL_USE_VCLPLUGIN': 'svp'})
            if completed.returncode:
                raise ValueError('presentation_conversion_failed')
        convert('pdf:impress_pdf_Export', output)
        pdf = output / 'reference.pdf'
        if pdf.is_symlink() or not pdf.is_file() or not 0 < pdf.stat().st_size <= 20 * 1024 * 1024:
            raise ValueError('presentation_render_unavailable_or_too_large')
        normalized = None
        if suffix == '.ppt':
            convert('pptx:Impress MS PowerPoint 2007 XML', output)
            pptx = output / 'reference.pptx'
            if pptx.is_symlink() or not pptx.is_file() or not 0 < pptx.stat().st_size <= 20 * 1024 * 1024:
                raise ValueError('presentation_normalization_failed')
            normalized = {'path': str(pptx), 'sha256': hashlib.sha256(pptx.read_bytes()).hexdigest(),
                          'derived_from_sha256': request['sha256']}
        if source.read_bytes() != data:
            raise ValueError('presentation_version_changed')
        return {'pdf': str(pdf), 'pdf_sha256': hashlib.sha256(pdf.read_bytes()).hexdigest(),
                'source_sha256': request['sha256'], 'normalized_source': normalized}


if __name__ == '__main__':
    import base64
    try:
        print(json.dumps(render(json.loads(base64.b64decode(sys.argv[1])))))
    except Exception:
        # No host path, uploaded content or converter diagnostics in errors.
        print(json.dumps({'error': 'presentation_render_failed'}))
        sys.exit(1)
