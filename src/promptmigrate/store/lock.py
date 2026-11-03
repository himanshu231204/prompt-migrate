"""Project-wide lock serializing manifest changes and initial environment database setup."""
from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
import hashlib
import os
from pathlib import Path

from .. import project


@contextmanager
def _project_lock(project_dir: Path) -> Iterator[None]:
    """Serialize project metadata changes and initial environment database setup."""
    root = project.require_init(project_dir)
    if os.name == "nt":
        import ctypes
        digest = hashlib.sha256(os.fsencode(root)).hexdigest()
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.CreateMutexW.argtypes = (ctypes.c_void_p, ctypes.c_int, ctypes.c_wchar_p)
        kernel.CreateMutexW.restype = ctypes.c_void_p
        kernel.WaitForSingleObject.argtypes = (ctypes.c_void_p, ctypes.c_uint32)
        kernel.WaitForSingleObject.restype = ctypes.c_uint32
        kernel.ReleaseMutex.argtypes = (ctypes.c_void_p,)
        kernel.CloseHandle.argtypes = (ctypes.c_void_p,)
        handle = kernel.CreateMutexW(None, False, f"Global\\PromptMigrate-{digest}")
        if not handle:
            raise OSError(ctypes.get_last_error(), "Could not create environment manifest mutex")
        result = kernel.WaitForSingleObject(handle, 0xFFFFFFFF)
        if result not in (0, 0x80):
            kernel.CloseHandle(handle)
            raise OSError(ctypes.get_last_error(), "Could not acquire environment manifest mutex")
        try:
            yield
        finally:
            kernel.ReleaseMutex(handle)
            kernel.CloseHandle(handle)
    else:
        import fcntl
        descriptor = os.open(root, os.O_RDONLY)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(descriptor)
