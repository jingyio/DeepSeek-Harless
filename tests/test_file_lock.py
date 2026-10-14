"""Free process-exclusion diagnostics, run on POSIX and Windows CI."""
import errno
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
import runpy

import pytest

from src.adapters.file_lock import exclusive_lock
from src.adapters import file_lock


@pytest.mark.parametrize('script', [
    'paper-motif-experiment.py', 'paper-reference-experiment.py',
    'paper-citation-rsi.py', 'parameter-motif-proof.py',
    'paper-reference-continuation.py', 'paper-rsi-tool-learning.py',
    'paper-rsi-generated-task.py', 'paper-rsi-batch-shadow.py',
    'paper-rsi-state-shadow.py', 'paper-rsi-overnight.py',
    'paper-rsi-recovery.py', 'paper-rsi-trace.py',
    'paper-rsi-revision.py', 'paper-rsi-revision-task.py',
    'paper-rsi-patch.py', 'paper-rsi-patch-task.py',
    'paper-rsi-effect-task.py', 'paper-rsi-receipt-task.py',
])
def test_offline_controller_import_does_not_acquire_lock_or_call_model(script, monkeypatch):
    def forbidden(*args):
        pytest.fail('offline import must not acquire a lock')
    monkeypatch.setattr(file_lock, '_acquire', forbidden)
    namespace = runpy.run_path(str(Path(__file__).resolve().parents[1] / 'scripts' / script),
                              run_name='__offline_import_diagnostic__')
    assert namespace['ROOT'].is_dir()


def competitor(path):
    code = '''
import sys
from src.adapters.file_lock import exclusive_lock
try:
    with exclusive_lock(sys.argv[1]): pass
except BlockingIOError:
    raise SystemExit(73)
'''
    return subprocess.run([sys.executable, '-c', code, str(path)],
                          cwd=Path(__file__).resolve().parents[1], timeout=10,
                          capture_output=True, text=True)


def test_process_lock_excludes_competitors_and_releases_after_error(tmp_path):
    path = tmp_path / 'shared budget.lock'
    with pytest.raises(ValueError, match='task failed'):
        with exclusive_lock(path):
            result = competitor(path)
            assert result.returncode == 73, result.stderr
            raise ValueError('task failed')
    assert path.exists()  # Never unlink the shared lock inode after release.
    result = competitor(path)
    assert result.returncode == 0, result.stderr


def test_windows_backend_uses_same_byte_for_nonblocking_acquire_and_release(tmp_path, monkeypatch):
    calls = []
    fake = SimpleNamespace(LK_NBLCK=2, LK_UNLCK=0,
                           locking=lambda fd, mode, count: calls.append((mode, count)))
    monkeypatch.setitem(sys.modules, 'msvcrt', fake)
    monkeypatch.setattr(file_lock.sys, 'platform', 'win32')
    with exclusive_lock(tmp_path / 'lock'):
        assert calls == [(2, 1)]
    assert calls == [(2, 1), (0, 1)]


def test_windows_busy_lock_refuses_without_unlocking_or_running_body(tmp_path, monkeypatch):
    def busy(fd, mode, count):
        raise OSError(errno.EACCES, 'locked')
    fake = SimpleNamespace(LK_NBLCK=2, LK_UNLCK=0, locking=busy)
    monkeypatch.setitem(sys.modules, 'msvcrt', fake)
    monkeypatch.setattr(file_lock.sys, 'platform', 'win32')
    with pytest.raises(BlockingIOError):
        with exclusive_lock(tmp_path / 'lock'):
            pytest.fail('a busy budget must never enter the task')
