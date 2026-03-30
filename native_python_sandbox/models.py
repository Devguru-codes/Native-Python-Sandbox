"""Shared models for sandbox execution results."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class TerminationReason(str, Enum):
    """High-level reason the sandboxed process stopped running."""

    SUCCESS = "SUCCESS"
    TIMEOUT_EXCEEDED = "TIMEOUT_EXCEEDED"
    MEMORY_VIOLATION = "MEMORY_VIOLATION"
    GPU_MEMORY_VIOLATION = "GPU_MEMORY_VIOLATION"
    LAUNCH_ERROR = "LAUNCH_ERROR"
    RUNTIME_ERROR = "RUNTIME_ERROR"


@dataclass(slots=True)
class ExecutionResult:
    """Structured result returned after a sandbox execution attempt."""

    exit_code: int | None
    stdout: str
    stderr: str
    termination_reason: TerminationReason
