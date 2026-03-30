# Native Python Sandbox Implementation Plan

## Project goal

Build a lightweight, cross-platform Python sandbox that executes untrusted contestant scripts in a child process, monitors CPU time and memory usage with `psutil`, forcefully terminates policy violations, and proves the behavior with automated `pytest` coverage.

## Proposed phases

### Phase 1: Core project structure

- Add the main package layout and initial module files.
- Define shared enums and dataclasses for execution outcomes.
- Establish dependency and test conventions for the repository.

### Phase 2: Sandbox engine

- Implement `NativePythonSandbox` with configurable timeout and memory limits.
- Launch submissions with `subprocess`.
- Add a monitoring thread that watches the child PID and descendant processes.
- Terminate the full process tree for timeout or memory violations.
- Return a structured `ExecutionResult`.

### Phase 3: Malicious fixtures and tests

- Add intentionally unsafe sample submissions for CPU and memory abuse.
- Write `pytest` coverage that validates timeout handling, memory enforcement, and successful parent-process survival.
- Keep the tests deterministic and platform-aware where needed.

### Phase 4: Documentation and portfolio polish

- Write a strong `README.md` with architecture notes, usage instructions, and security caveats.
- Add a demo workflow for capturing a screenshot or GIF of the sandbox stopping bad code.
- Make the repository presentation-ready for a GitHub portfolio link.

## Deliverables by phase

1. Engine code and result models.
2. Test suite and malicious sample scripts.
3. Documentation and repo polish.

## Notes

- This project will focus on process isolation and resource enforcement, not full OS-level sandboxing.
- Cross-platform process-tree termination needs careful handling, especially on Windows.
- CPU timeout will be enforced by wall-clock runtime monitoring, which aligns with the mentor's lightweight requirement and is simpler to keep robust across platforms.
