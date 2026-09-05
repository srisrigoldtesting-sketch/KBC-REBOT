from __future__ import annotations

import os


class KeepAwake:
    """Prevent automatic idle sleep only while the bot runs; restore on exit."""

    def __enter__(self):
        if os.name == "nt":
            import ctypes
            ctypes.windll.kernel32.SetThreadExecutionState(0x80000001)
        return self

    def __exit__(self, *args):
        if os.name == "nt":
            import ctypes
            ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)
