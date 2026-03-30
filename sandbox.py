"""Cross-platform native Python sandbox for executing untrusted scripts."""

from __future__ import annotations

import argparse
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Sequence

import psutil

from native_python_sandbox.gpu_monitor import NvidiaGpuMonitor
from native_python_sandbox.models import ExecutionResult, TerminationReason
from native_python_sandbox.process_utils import (
    get_process_tree_memory_mb,
    terminate_process_tree,
)


class NativePythonSandbox:
    """Execute a Python script in a monitored child process."""

    _POLL_INTERVAL_SECONDS = 0.05

    def __init__(
        self,
        target_script_path: str | Path,
        max_cpu_timeout_seconds: float = 15,
        max_memory_mb: float = 256,
        max_gpu_memory_mb: float | None = None,
    ) -> None:
        self.target_script_path = Path(target_script_path).resolve()
        self.max_cpu_timeout_seconds = max_cpu_timeout_seconds
        self.max_memory_mb = max_memory_mb
        self.max_gpu_memory_mb = max_gpu_memory_mb

        self._termination_reason = TerminationReason.SUCCESS
        self._reason_lock = threading.Lock()

    def run(self) -> ExecutionResult:
        """Run the configured script and return a structured execution result."""

        script_validation_error = self._validate_target_script()
        if script_validation_error is not None:
            return script_validation_error

        command = [sys.executable, str(self.target_script_path)]
        creation_kwargs = self._build_process_creation_kwargs()
        stderr_notes: list[str] = []

        gpu_monitor = NvidiaGpuMonitor()
        gpu_monitor_active = False
        if self.max_gpu_memory_mb is not None:
            gpu_status = gpu_monitor.initialize()
            gpu_monitor_active = gpu_status.enabled
            if gpu_status.message:
                stderr_notes.append(gpu_status.message)

        try:
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                cwd=str(self.target_script_path.parent),
                **creation_kwargs,
            )
        except OSError as exc:
            gpu_monitor.shutdown()
            return ExecutionResult(
                exit_code=None,
                stdout="",
                stderr=f"Failed to launch sandboxed script: {exc}",
                termination_reason=TerminationReason.LAUNCH_ERROR,
            )

        stop_monitoring = threading.Event()
        monitor_thread = threading.Thread(
            target=self._monitor_process,
            args=(process.pid, stop_monitoring, gpu_monitor if gpu_monitor_active else None),
            name="sandbox-monitor",
            daemon=True,
        )
        monitor_thread.start()

        try:
            stdout, stderr = process.communicate()
        except Exception as exc:
            self._set_termination_reason(TerminationReason.RUNTIME_ERROR)
            terminate_process_tree(process.pid)
            stdout, stderr = process.communicate()
            stderr = self._append_stderr(stderr, f"Sandbox runtime failure: {exc}")
        finally:
            stop_monitoring.set()
            monitor_thread.join(timeout=1.0)
            gpu_monitor.shutdown()

        termination_reason = self._get_termination_reason()
        if termination_reason is TerminationReason.SUCCESS and process.returncode not in (0, None):
            termination_reason = TerminationReason.RUNTIME_ERROR

        if stderr_notes:
            stderr = self._append_stderr(stderr, "\n".join(stderr_notes))

        return ExecutionResult(
            exit_code=process.returncode,
            stdout=stdout,
            stderr=stderr,
            termination_reason=termination_reason,
        )

    def _validate_target_script(self) -> ExecutionResult | None:
        if not self.target_script_path.exists():
            return ExecutionResult(
                exit_code=None,
                stdout="",
                stderr=f"Target script does not exist: {self.target_script_path}",
                termination_reason=TerminationReason.LAUNCH_ERROR,
            )

        if not self.target_script_path.is_file():
            return ExecutionResult(
                exit_code=None,
                stdout="",
                stderr=f"Target script is not a file: {self.target_script_path}",
                termination_reason=TerminationReason.LAUNCH_ERROR,
            )

        if self.max_cpu_timeout_seconds <= 0:
            return ExecutionResult(
                exit_code=None,
                stdout="",
                stderr="max_cpu_timeout_seconds must be greater than zero.",
                termination_reason=TerminationReason.LAUNCH_ERROR,
            )

        if self.max_memory_mb <= 0:
            return ExecutionResult(
                exit_code=None,
                stdout="",
                stderr="max_memory_mb must be greater than zero.",
                termination_reason=TerminationReason.LAUNCH_ERROR,
            )

        if self.max_gpu_memory_mb is not None and self.max_gpu_memory_mb <= 0:
            return ExecutionResult(
                exit_code=None,
                stdout="",
                stderr="max_gpu_memory_mb must be greater than zero when provided.",
                termination_reason=TerminationReason.LAUNCH_ERROR,
            )

        return None

    def _build_process_creation_kwargs(self) -> dict[str, int | bool]:
        if sys.platform == "win32":
            return {
                "creationflags": subprocess.CREATE_NEW_PROCESS_GROUP,
            }

        return {
            "start_new_session": True,
        }

    def _monitor_process(
        self,
        root_pid: int,
        stop_event: threading.Event,
        gpu_monitor: NvidiaGpuMonitor | None = None,
    ) -> None:
        start_time = time.monotonic()

        try:
            root_process = psutil.Process(root_pid)
        except psutil.Error:
            return

        while not stop_event.is_set():
            if not root_process.is_running():
                return

            elapsed_seconds = time.monotonic() - start_time
            if elapsed_seconds > self.max_cpu_timeout_seconds:
                self._set_termination_reason(TerminationReason.TIMEOUT_EXCEEDED)
                terminate_process_tree(root_pid)
                return

            memory_mb = get_process_tree_memory_mb(root_process)
            if memory_mb > self.max_memory_mb:
                self._set_termination_reason(TerminationReason.MEMORY_VIOLATION)
                terminate_process_tree(root_pid)
                return

            if gpu_monitor is not None and self.max_gpu_memory_mb is not None:
                gpu_memory_mb = gpu_monitor.get_process_memory_mb(root_pid)
                if gpu_memory_mb > self.max_gpu_memory_mb:
                    self._set_termination_reason(TerminationReason.GPU_MEMORY_VIOLATION)
                    terminate_process_tree(root_pid)
                    return

            stop_event.wait(self._POLL_INTERVAL_SECONDS)

    def _set_termination_reason(self, reason: TerminationReason) -> None:
        with self._reason_lock:
            if self._termination_reason is TerminationReason.SUCCESS:
                self._termination_reason = reason

    def _get_termination_reason(self) -> TerminationReason:
        with self._reason_lock:
            return self._termination_reason

    @staticmethod
    def _append_stderr(existing_stderr: str, extra_message: str) -> str:
        if not existing_stderr:
            return extra_message
        return f"{existing_stderr.rstrip()}\n{extra_message}"


def _build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run a Python script inside the Native Python Sandbox.",
        epilog=(
            "Examples:\n"
            "  python sandbox.py bad_submission.py --timeout-seconds 5 --memory-mb 256\n"
            "  python sandbox.py memory_bomb_submission.py --timeout-seconds 15 --memory-mb 256\n"
            "  python sandbox.py /examples"
        ),
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument(
        "script",
        nargs="?",
        help="Path to the Python script to execute, or /examples for guided usage.",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=15,
        help="Maximum elapsed runtime before the child process is terminated.",
    )
    parser.add_argument(
        "--memory-mb",
        type=float,
        default=256,
        help="Maximum combined RSS memory allowed for the child process tree.",
    )
    parser.add_argument(
        "--gpu-memory-mb",
        type=float,
        default=None,
        help="Optional NVIDIA GPU memory limit for the root child process.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] in {"/help", "help", "/?"}:
        argv = ["--help"]
    if argv and argv[0] == "/examples":
        print("Native Python Sandbox examples")
        print("1. Timeout protection:")
        print("   python sandbox.py bad_submission.py --timeout-seconds 5 --memory-mb 256")
        print("2. Memory protection:")
        print("   python sandbox.py memory_bomb_submission.py --timeout-seconds 15 --memory-mb 256")
        print("3. Optional GPU protection:")
        print(
            "   python sandbox.py bad_submission.py --timeout-seconds 5 --memory-mb 256 --gpu-memory-mb 512"
        )
        print("4. Full CLI help:")
        print("   python sandbox.py /help")
        return 0

    parser = _build_argument_parser()
    args = parser.parse_args(argv)
    if not args.script:
        parser.print_help()
        return 1

    sandbox = NativePythonSandbox(
        target_script_path=args.script,
        max_cpu_timeout_seconds=args.timeout_seconds,
        max_memory_mb=args.memory_mb,
        max_gpu_memory_mb=args.gpu_memory_mb,
    )
    result = sandbox.run()

    print(f"termination_reason={result.termination_reason.value}")
    print(f"exit_code={result.exit_code}")
    if result.stdout:
        print("\n--- stdout ---")
        print(result.stdout)
    if result.stderr:
        print("\n--- stderr ---", file=sys.stderr)
        print(result.stderr, file=sys.stderr)

    return 0 if result.termination_reason is TerminationReason.SUCCESS else 1


if __name__ == "__main__":
    raise SystemExit(main())
