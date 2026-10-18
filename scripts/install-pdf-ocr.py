"""Install pinned public OCR languages into a dedicated private toolchain."""
import argparse
import hashlib
import json
from pathlib import Path
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


def install(root):
    root = Path(root)
    if root.is_symlink(): raise ValueError('fixed_installation_required')
    target = root / 'tessdata'
    target.mkdir(parents=True, exist_ok=True, mode=0o700)
    if target.is_symlink(): raise ValueError('fixed_installation_required')
    manifest = json.loads((ROOT / 'config/pdf-ocr-assets.json').read_text())
    for name, digest in manifest['files'].items():
        path = target / name
        if path.is_symlink(): raise ValueError('fixed_language_file_required')
        if path.exists() and hashlib.sha256(path.read_bytes()).hexdigest() == digest: continue
        url = f"https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/{manifest['commit']}/{name}"
        with urllib.request.urlopen(url, timeout=90) as response: data = response.read(20*1024*1024)
        if hashlib.sha256(data).hexdigest() != digest: raise ValueError('ocr_language_hash_mismatch')
        temporary = target / (name + '.tmp')
        if temporary.exists(): raise ValueError('unfinished_ocr_installation')
        with temporary.open('xb') as output: output.write(data)
        temporary.chmod(0o600)
        temporary.replace(path)
    return {'languages': ['eng', 'chi_sim'], 'commit': manifest['commit'], 'verified': True}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    print(json.dumps(install(parser.parse_args().root)))
