"""Origin parsing diagnostics; no model or server startup."""
import importlib.util
from pathlib import Path
import pytest

spec = importlib.util.spec_from_file_location('harness_web_origin', Path(__file__).resolve().parents[1] / 'scripts/harness-web.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

def test_exact_https_authority_normalization():
    assert module.https_public_origin('https://Harless.example:443/') == 'https://harless.example'
    assert module.https_public_origin('https://harless.example:3443') == 'https://harless.example:3443'
    assert module.https_public_origin('https://[::1]:3443') == 'https://[::1]:3443'

@pytest.mark.parametrize('origin', [
    'http://harless.example', 'https://user:password@harless.example', 'https://harless.example/tasks',
    'https://harless.example/?token=secret', 'https://harless.example/#fragment',
    'https://harless.example\n', 'https://harless.example:0', 'https://harless.example:65536',
    'https://harless.example:abc', 'https://',
])
def test_invalid_public_origins_refused(origin):
    with pytest.raises(ValueError):
        module.https_public_origin(origin)
