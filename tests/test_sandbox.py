"""Tests for the Native Python Sandbox engine."""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

import psutil
import pytest

import sandbox as sandbox_module
from sandbox import NativePythonSandbox
from native_python_sandbox.models import TerminationReason


FIXTURES_DIR = Path(__file__).parent / "fixtures"


def test_successful_submission_completes_normally() -> None:
    result = NativePythonSandbox(
        FIXTURES_DIR / "good_submission.py",
        max_cpu_timeout_seconds=2,
        max_memory_mb=128,
    ).run()

    assert result.termination_reason is TerminationReason.SUCCESS
    assert result.exit_code == 0
    assert result.stdout.strip() == "analysis complete"
    assert result.stderr == ""


def test_missing_script_returns_launch_error() -> None:
    result = NativePythonSandbox(
        FIXTURES_DIR / "does_not_exist.py",
        max_cpu_timeout_seconds=2,
        max_memory_mb=128,
    ).run()

    assert result.termination_reason is TerminationReason.LAUNCH_ERROR
    assert result.exit_code is None
    assert "does not exist" in result.stderr


def test_invalid_timeout_returns_launch_error() -> None:
    result = NativePythonSandbox(
        FIXTURES_DIR / "good_submission.py",
        max_cpu_timeout_seconds=0,
        max_memory_mb=128,
    ).run()

    assert result.termination_reason is TerminationReason.LAUNCH_ERROR
    assert "max_cpu_timeout_seconds" in result.stderr


def test_invalid_memory_limit_returns_launch_error() -> None:
    result = NativePythonSandbox(
        FIXTURES_DIR / "good_submission.py",
        max_cpu_timeout_seconds=2,
        max_memory_mb=0,
    ).run()

    assert result.termination_reason is TerminationReason.LAUNCH_ERROR
    assert "max_memory_mb" in result.stderr


def test_cpu_bound_submission_is_killed_on_timeout() -> None:
    result = NativePythonSandbox(
        FIXTURES_DIR / "bad_submission_cpu.py",
        max_cpu_timeout_seconds=1,
        max_memory_mb=128,
    ).run()

    assert result.termination_reason is TerminationReason.TIMEOUT_EXCEEDED
    assert result.exit_code not in (0, None)


def test_sleep_loop_is_also_killed_by_elapsed_timeout() -> None:
    result = NativePythonSandbox(
        FIXTURES_DIR / "bad_submission_sleep.py",
        max_cpu_timeout_seconds=1,
        max_memory_mb=128,
    ).run()

    assert result.termination_reason is TerminationReason.TIMEOUT_EXCEEDED
    assert result.exit_code not in (0, None)


def test_memory_hog_submission_is_killed_on_memory_violation() -> None:
    result = NativePythonSandbox(
        FIXTURES_DIR / "bad_submission_memory.py",
        max_cpu_timeout_seconds=10,
        max_memory_mb=96,
    ).run()

    assert result.termination_reason is TerminationReason.MEMORY_VIOLATION
    assert result.exit_code not in (0, None)


def test_runtime_error_submission_is_reported_cleanly() -> None:
    result = NativePythonSandbox(
        FIXTURES_DIR / "runtime_error_submission.py",
        max_cpu_timeout_seconds=2,
        max_memory_mb=128,
    ).run()

    assert result.termination_reason is TerminationReason.RUNTIME_ERROR
    assert result.exit_code not in (0, None)
    assert "boom from contestant" in result.stderr


def test_gpu_limit_validation_rejects_non_positive_values() -> None:
    result = NativePythonSandbox(
        FIXTURES_DIR / "good_submission.py",
        max_cpu_timeout_seconds=2,
        max_memory_mb=128,
        max_gpu_memory_mb=0,
    ).run()

    assert result.termination_reason is TerminationReason.LAUNCH_ERROR
    assert "max_gpu_memory_mb" in result.stderr


def test_gpu_monitor_unavailable_falls_back_gracefully(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeGpuMonitor:
        def initialize(self):
            return type("Status", (), {"enabled": False, "message": "GPU monitoring unavailable for test."})()

        def shutdown(self) -> None:
            return None

    monkeypatch.setattr(sandbox_module, "NvidiaGpuMonitor", FakeGpuMonitor)

    result = NativePythonSandbox(
        FIXTURES_DIR / "good_submission.py",
        max_cpu_timeout_seconds=2,
        max_memory_mb=128,
        max_gpu_memory_mb=64,
    ).run()

    assert result.termination_reason is TerminationReason.SUCCESS
    assert "GPU monitoring unavailable for test." in result.stderr


def test_gpu_memory_violation_is_reported_when_monitor_supports_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeGpuMonitor:
        def initialize(self):
            return type("Status", (), {"enabled": True, "message": ""})()

        def get_process_memory_mb(self, pid: int) -> float:
            return 512.0

        def shutdown(self) -> None:
            return None

    monkeypatch.setattr(sandbox_module, "NvidiaGpuMonitor", FakeGpuMonitor)

    result = NativePythonSandbox(
        FIXTURES_DIR / "bad_submission_sleep.py",
        max_cpu_timeout_seconds=10,
        max_memory_mb=128,
        max_gpu_memory_mb=128,
    ).run()

    assert result.termination_reason is TerminationReason.GPU_MEMORY_VIOLATION
    assert result.exit_code not in (0, None)


def test_process_tree_termination_kills_spawned_children(tmp_path: Path) -> None:
    child_pid_file = tmp_path / "child_pid.txt"
    spawner_script = tmp_path / "spawn_child_and_wait.py"
    spawner_script.write_text(
        "\n".join(
            [
                "import subprocess",
                "import sys",
                "import time",
                f"pid_file = r'{child_pid_file}'",
                "child = subprocess.Popen([sys.executable, '-c', 'while True: pass'])",
                "with open(pid_file, 'w', encoding='utf-8') as handle:",
                "    handle.write(str(child.pid))",
                "while True:",
                "    time.sleep(1)",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    result = NativePythonSandbox(
        spawner_script,
        max_cpu_timeout_seconds=1,
        max_memory_mb=128,
    ).run()

    assert result.termination_reason is TerminationReason.TIMEOUT_EXCEEDED
    child_pid = int(child_pid_file.read_text(encoding="utf-8").strip())

    time.sleep(0.2)
    assert not psutil.pid_exists(child_pid)


def test_parent_process_survives_multiple_policy_violations() -> None:
    timeout_result = NativePythonSandbox(
        FIXTURES_DIR / "bad_submission_cpu.py",
        max_cpu_timeout_seconds=1,
        max_memory_mb=128,
    ).run()
    memory_result = NativePythonSandbox(
        FIXTURES_DIR / "bad_submission_memory.py",
        max_cpu_timeout_seconds=10,
        max_memory_mb=96,
    ).run()

    assert timeout_result.termination_reason is TerminationReason.TIMEOUT_EXCEEDED
    assert memory_result.termination_reason is TerminationReason.MEMORY_VIOLATION

    # Reaching this point means the pytest parent process stayed alive and responsive.
    assert True


def test_cli_reports_success_for_good_submission() -> None:
    command = [
        sys.executable,
        str(Path(__file__).resolve().parents[1] / "sandbox.py"),
        str(FIXTURES_DIR / "good_submission.py"),
        "--timeout-seconds",
        "2",
        "--memory-mb",
        "128",
    ]
    completed = subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0
    assert "termination_reason=SUCCESS" in completed.stdout


def test_cli_help_alias_succeeds() -> None:
    command = [
        sys.executable,
        str(Path(__file__).resolve().parents[1] / "sandbox.py"),
        "/help",
    ]
    completed = subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0
    assert "Run a Python script inside the Native Python Sandbox." in completed.stdout


def test_cli_examples_alias_succeeds() -> None:
    command = [
        sys.executable,
        str(Path(__file__).resolve().parents[1] / "sandbox.py"),
        "/examples",
    ]
    completed = subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0
    assert "Native Python Sandbox examples" in completed.stdout
