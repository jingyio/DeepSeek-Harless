"""Administrator-selected Poppler installation, never inherited credentials."""
import os
from pathlib import Path
import shutil


def configure_pdf_parser(scene):
    configured = os.environ.get('HARLESS_PDF_TOOLCHAIN_ROOT')
    if not configured:
        if not all(shutil.which(name) for name in ('pdfinfo', 'pdftotext')):
            raise ValueError('Poppler required')
        return
    root = Path(configured).resolve(strict=True)
    if root == Path('/') or not all((root / 'bin' / name).is_file() for name in ('pdfinfo', 'pdftotext')):
        raise ValueError('Invalid Poppler installation')
    libraries = root / 'lib/x86_64-linux-gnu'
    if not libraries.is_dir():
        raise ValueError('Poppler installation libraries required')
    scene['pdf_toolchain_root'] = str(root)
    for row in scene['mcp_rows']:
        row['config']['env'].update(PATH=str(root / 'bin') + ':/usr/bin:/bin', LD_LIBRARY_PATH=str(libraries))
