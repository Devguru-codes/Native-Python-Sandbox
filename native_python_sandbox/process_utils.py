"""Internal helpers for inspecting and terminating process trees."""

from __future__ import annotations

from contextlib import suppress

import psutil


def get_process_tree_memory_mb(root_process: psutil.Process) -> float:
    """Return the combined RSS memory usage for the root process and children."""

    processes = [root_process]
    with suppress(psutil.Error):
        processes.extend(root_process.children(recursive=True))

    total_bytes = 0
    for process in processes:
        with suppress(psutil.Error):
            total_bytes += process.memory_info().rss

    return total_bytes / (1024 * 1024)


def terminate_process_tree(root_pid: int, wait_timeout_seconds: float = 3.0) -> None:
    """Terminate a process and all descendants, escalating to kill if needed."""

    try:
        root_process = psutil.Process(root_pid)
    except psutil.Error:
        return

    processes = []
    with suppress(psutil.Error):
        processes = root_process.children(recursive=True)
    processes.append(root_process)

    for process in reversed(processes):
        with suppress(psutil.Error):
            process.terminate()

    _, alive = psutil.wait_procs(processes, timeout=wait_timeout_seconds)
    for process in alive:
        with suppress(psutil.Error):
            process.kill()

    if alive:
        psutil.wait_procs(alive, timeout=wait_timeout_seconds)
