"""Nonblocking process lock for budget/learning stores; never unlink lock files.

POSIX uses the same flock as historical experiments. Windows locks byte zero
through msvcrt, so previews/imports do not depend on an unavailable Unix module.
"""
from contextlib import contextmanager
import errno
import os
from pathlib import Path
import sys


def _acquire(fd):
    if sys.platform == 'win32':
        import msvcrt
        os.lseek(fd, 0, os.SEEK_SET)
        try:
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        except OSError as exc:
            if exc.errno not in (errno.EACCES, errno.EAGAIN, errno.EDEADLK):
                raise
            raise BlockingIOError(errno.EWOULDBLOCK, 'store is locked by another process') from exc
    else:
        import fcntl
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)


def _release(fd):
    if sys.platform == 'win32':
        import msvcrt
        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
    else:
        import fcntl
        fcntl.flock(fd, fcntl.LOCK_UN)


@contextmanager
def exclusive_lock(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(path, os.O_RDWR | os.O_CREAT | getattr(os, 'O_NOFOLLOW', 0), 0o600)
    acquired = False
    try:
        # Both backends lock the existing inode/handle, not a deleteable marker.
        # Windows byte-range locks may extend past EOF; no content write needed.
        _acquire(fd)
        acquired = True
        yield fd
    finally:
        try:
            if acquired:
                _release(fd)
        finally:
            os.close(fd)
