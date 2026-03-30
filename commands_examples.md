# Command Examples

This file collects every practical command currently supported by the project, along with what each one does and when to use it.

## 1. Create the virtual environment

```powershell
python -m venv .venv
```

Use this first to create an isolated Python environment for the project.

## 2. Install dependencies

```powershell
.\.venv\Scripts\python -m pip install -r req.txt
```

Installs:

- `psutil` for process and memory monitoring
- `pytest` for automated tests
- `nvidia-ml-py` for optional NVIDIA GPU telemetry

## 3. Show CLI help

```powershell
.\.venv\Scripts\python sandbox.py /help
```

This is the most user-friendly command to start with. It prints the built-in CLI help and available flags.

You can also use the standard argparse form:

```powershell
.\.venv\Scripts\python sandbox.py --help
```

## 4. Show guided usage examples

```powershell
.\.venv\Scripts\python sandbox.py /examples
```

Prints example commands for timeout protection, memory protection, and optional GPU protection.

## 5. Run the sandbox on a normal script

```powershell
.\.venv\Scripts\python sandbox.py tests\fixtures\good_submission.py --timeout-seconds 2 --memory-mb 128
```

Use this to verify the happy path. Expected result:

```text
termination_reason=SUCCESS
exit_code=0
```

## 6. Run the CPU infinite-loop demo

```powershell
.\.venv\Scripts\python sandbox.py bad_submission.py --timeout-seconds 5 --memory-mb 256
```

This runs the top-level demo script that loops forever. The sandbox should terminate it after the configured elapsed timeout.

Expected result:

```text
termination_reason=TIMEOUT_EXCEEDED
exit_code=<platform dependent>
```

Note:

- `termination_reason` is the stable contract.
- `exit_code` may differ across Windows, Linux, and macOS for killed processes.

## 7. Run the sleep-loop demo

```powershell
.\.venv\Scripts\python sandbox.py tests\fixtures\bad_submission_sleep.py --timeout-seconds 1 --memory-mb 128
```

This proves the sandbox catches elapsed runtime abuse, not just CPU-burning loops. A `time.sleep()` loop should still hit `TIMEOUT_EXCEEDED`.

## 8. Run the memory bomb demo

```powershell
.\.venv\Scripts\python sandbox.py memory_bomb_submission.py --timeout-seconds 15 --memory-mb 256
```

This runs the demo script that keeps allocating memory until the sandbox kills it.

Expected result:

```text
termination_reason=MEMORY_VIOLATION
exit_code=<platform dependent>
```

## 9. Run with optional GPU memory enforcement

```powershell
.\.venv\Scripts\python sandbox.py bad_submission.py --timeout-seconds 5 --memory-mb 256 --gpu-memory-mb 512
```

Use this when you want the sandbox to also watch NVIDIA GPU memory usage.

Behavior:

- If NVML is available and the machine has a supported NVIDIA GPU, GPU monitoring is enabled.
- If NVML is unavailable, the run still proceeds and the sandbox reports that GPU monitoring could not be enabled.

## 10. Run the automated tests

```powershell
.\.venv\Scripts\python -m pytest -q
```

Runs the full test suite for the project.

This currently covers:

- success cases
- bad path validation
- timeout enforcement
- memory enforcement
- runtime exception reporting
- optional GPU behavior
- process-tree cleanup
- CLI behavior

## 11. Run a single specific test

```powershell
.\.venv\Scripts\python -m pytest tests\test_sandbox.py -q
```

Use this if you want to run just the sandbox test module.

To run one named test:

```powershell
.\.venv\Scripts\python -m pytest tests\test_sandbox.py -k timeout -q
```

That example filters for tests whose names include `timeout`.

## 12. Common command patterns

### Use a custom timeout

```powershell
.\.venv\Scripts\python sandbox.py bad_submission.py --timeout-seconds 3 --memory-mb 256
```

Use a lower timeout when you want faster failure during demos or development.

### Use a custom memory limit

```powershell
.\.venv\Scripts\python sandbox.py memory_bomb_submission.py --timeout-seconds 15 --memory-mb 96
```

Use a lower memory limit when you want the memory-kill behavior to trigger faster.

### Run a script from another directory

```powershell
.\.venv\Scripts\python sandbox.py C:\path\to\submission.py --timeout-seconds 10 --memory-mb 256
```

The sandbox accepts either relative or absolute script paths.

## 13. Meaning of outputs

### `termination_reason=SUCCESS`

The script completed normally within the configured limits.

### `termination_reason=TIMEOUT_EXCEEDED`

The script exceeded the allowed elapsed runtime and was terminated.

### `termination_reason=MEMORY_VIOLATION`

The script exceeded the allowed RAM usage and was terminated.

### `termination_reason=GPU_MEMORY_VIOLATION`

The script exceeded the allowed NVIDIA GPU memory limit and was terminated.

### `termination_reason=LAUNCH_ERROR`

The sandbox could not start the script, usually because:

- the file path is wrong
- the path is not a file
- one of the limits is invalid

### `termination_reason=RUNTIME_ERROR`

The script launched but failed during execution, such as raising a Python exception.

## 14. Recommended first commands for a new user

If someone is opening the project for the first time, this is the shortest useful sequence:

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r req.txt
.\.venv\Scripts\python sandbox.py /help
.\.venv\Scripts\python sandbox.py bad_submission.py --timeout-seconds 5 --memory-mb 256
.\.venv\Scripts\python -m pytest -q
```

## 15. Current command surface

The project currently exposes these user-facing CLI entry patterns:

- `python sandbox.py /help`
- `python sandbox.py --help`
- `python sandbox.py /examples`
- `python sandbox.py <script_path> --timeout-seconds <seconds> --memory-mb <mb>`
- `python sandbox.py <script_path> --timeout-seconds <seconds> --memory-mb <mb> --gpu-memory-mb <mb>`

There are no other slash commands at the moment beyond `/help`, `/examples`, and the Windows-style help alias `/?`.
