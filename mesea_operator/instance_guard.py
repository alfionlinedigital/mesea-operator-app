"""Single-instance plumbing: a Windows mutex the installer can see, plus
cross-platform detection/termination of sibling instances for the portable app.

Two distinct mechanisms, one per update channel:

* **Installed (Windows)** — the app holds a named mutex (``acquire_singleton``)
  for its whole lifetime. The Inno Setup installer declares the *same* name via
  ``AppMutex`` (packaging/windows/installer.iss), so re-running the installer to
  upgrade detects the running app and asks the user to close it. The mutex name
  is shared through ``config.SINGLE_INSTANCE_MUTEX``.
* **Portable (any OS)** — there is no installer to gate the swap, so the app
  itself finds other running copies (``find_other_instances``) and offers to
  ``terminate`` them before continuing, freeing the on-disk binary for a
  self-update.

``psutil`` is imported lazily inside the functions that need real process
access, so this module imports cleanly (and unit tests run) without it, and the
``--version`` smoke path never pulls it in.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from typing import Callable, Iterable

from . import config

# Every shipped artifact is named "mesea-operator…" (installed exe, portable
# per-OS binaries). Treat any process whose image starts with this prefix as the
# same app family — and, crucially, refuse to target anything that does not, so
# a detection slip can never terminate an unrelated process.
APP_EXE_PREFIX = "mesea-operator"


@dataclass(frozen=True)
class ProcessInfo:
    pid: int
    name: str
    exe: str


def acquire_singleton(name: str | None = None) -> object | None:
    """Create a named Windows mutex and keep its handle alive for the process.

    No-op (returns None) off Windows. The returned handle is also stashed at
    module scope so it is never garbage-collected — the mutex must persist for
    the whole run for the installer's ``AppMutex`` check to see it.
    """
    if not sys.platform.startswith("win"):
        return None
    name = name or config.SINGLE_INSTANCE_MUTEX
    try:
        import ctypes

        handle = ctypes.windll.kernel32.CreateMutexW(None, False, name)
    except Exception:  # pragma: no cover - defensive; absent kernel32 etc.
        return None
    global _singleton_handle
    _singleton_handle = handle
    return handle


_singleton_handle: object | None = None


def find_other_instances(
    own_pid: int | None = None,
    iter_processes: Callable[[], Iterable[ProcessInfo]] | None = None,
) -> list[ProcessInfo]:
    """Return running ``mesea-operator*`` processes other than this one.

    ``iter_processes`` is injectable for tests; by default it enumerates real
    processes via ``psutil``.
    """
    own_pid = own_pid if own_pid is not None else os.getpid()
    iter_processes = iter_processes or _iter_processes
    others: list[ProcessInfo] = []
    for proc in iter_processes():
        if proc.pid == own_pid:
            continue
        image = (os.path.basename(proc.exe) or proc.name).lower()
        if image.startswith(APP_EXE_PREFIX):
            others.append(proc)
    return others


def terminate(pids: Iterable[int], timeout: float = 5.0, psutil_mod=None) -> dict[int, bool]:
    """Terminate ``pids`` (SIGTERM/terminate, then kill survivors).

    Returns ``{pid: closed?}``. ``psutil_mod`` is injectable for tests.
    """
    psutil = psutil_mod or _import_psutil()
    if psutil is None:
        return {pid: False for pid in pids}

    results: dict[int, bool] = {}
    procs = []
    for pid in pids:
        try:
            procs.append(psutil.Process(pid))
        except psutil.NoSuchProcess:
            results[pid] = True  # already gone is success

    for proc in procs:
        try:
            proc.terminate()
        except psutil.Error:  # pragma: no cover - races/permissions
            pass
    gone, alive = psutil.wait_procs(procs, timeout=timeout)

    for proc in alive:
        try:
            proc.kill()
        except psutil.Error:  # pragma: no cover
            pass
    gone2, still_alive = psutil.wait_procs(alive, timeout=timeout)

    closed = {p.pid for p in gone} | {p.pid for p in gone2}
    for proc in procs:
        results[proc.pid] = proc.pid in closed
    return results


def _iter_processes() -> Iterable[ProcessInfo]:
    psutil = _import_psutil()
    if psutil is None:
        return
    for proc in psutil.process_iter(["pid", "name", "exe"]):
        info = proc.info
        try:
            yield ProcessInfo(info["pid"], info.get("name") or "", info.get("exe") or "")
        except (KeyError, psutil.Error):  # pragma: no cover - vanished mid-iteration
            continue


def _import_psutil():
    try:
        import psutil

        return psutil
    except ImportError:  # pragma: no cover - psutil is a declared dependency
        return None
