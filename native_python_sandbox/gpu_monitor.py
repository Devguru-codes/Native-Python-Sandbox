"""Optional GPU telemetry helpers for NVIDIA-backed systems."""

from __future__ import annotations

from contextlib import suppress
from dataclasses import dataclass


try:
    import pynvml
except ImportError:  # pragma: no cover - exercised via tests with missing dependency.
    pynvml = None


@dataclass(slots=True)
class GpuMonitorStatus:
    """Describe whether GPU monitoring can be used for this run."""

    enabled: bool
    message: str = ""


class NvidiaGpuMonitor:
    """Read per-process NVIDIA GPU memory usage through NVML when available."""

    def __init__(self) -> None:
        self._initialized = False

    def initialize(self) -> GpuMonitorStatus:
        if pynvml is None:
            return GpuMonitorStatus(
                enabled=False,
                message="GPU monitoring unavailable: nvidia-ml-py is not installed.",
            )

        try:
            pynvml.nvmlInit()
        except pynvml.NVMLError as exc:
            return GpuMonitorStatus(
                enabled=False,
                message=f"GPU monitoring unavailable: {exc}",
            )

        device_count = pynvml.nvmlDeviceGetCount()
        if device_count == 0:
            pynvml.nvmlShutdown()
            return GpuMonitorStatus(
                enabled=False,
                message="GPU monitoring unavailable: no NVIDIA GPUs detected.",
            )

        self._initialized = True
        return GpuMonitorStatus(enabled=True)

    def get_process_memory_mb(self, pid: int) -> float:
        if not self._initialized or pynvml is None:
            return 0.0

        total_bytes = 0
        device_count = pynvml.nvmlDeviceGetCount()
        for index in range(device_count):
            handle = pynvml.nvmlDeviceGetHandleByIndex(index)

            for process_fetch in (
                getattr(pynvml, "nvmlDeviceGetComputeRunningProcesses", None),
                getattr(pynvml, "nvmlDeviceGetGraphicsRunningProcesses", None),
            ):
                if process_fetch is None:
                    continue

                with suppress(pynvml.NVMLError):
                    for process_info in process_fetch(handle):
                        if process_info.pid == pid:
                            used_gpu_memory = getattr(process_info, "usedGpuMemory", 0)
                            if used_gpu_memory and used_gpu_memory > 0:
                                total_bytes += used_gpu_memory

        return total_bytes / (1024 * 1024)

    def shutdown(self) -> None:
        if not self._initialized or pynvml is None:
            return

        with suppress(pynvml.NVMLError):
            pynvml.nvmlShutdown()
        self._initialized = False
