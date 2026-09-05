from __future__ import annotations

import os
from pathlib import Path

from .config import SetupError


class RunLock:
    """OS lock is released even after a crash; do not delete its file."""

    def __init__(self, path: Path):
        self.path = path
        self.file = None

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.file = self.path.open("a+b")
        try:
            # Reading a locked byte fails on Windows. Inspect size without reading it.
            if os.fstat(self.file.fileno()).st_size == 0:
                self.file.write(b"0")
                self.file.flush()
            self.file.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(self.file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.file.close()
            raise SetupError("KBC REBOT is already running. Stop its START window before another START or CHECK.") from None
        return self

    def __exit__(self, *args):
        self.file.close()
