# Polyphony v0.1 Compatibility Contract

This document formalizes the compatibility guarantees provided by Polyphony at v0.1:

1. **Task Resumption Guarantee:**
   A task can be started, paused, interrupted, and resumed without loss of preceding iteration history or session context.

2. **Durable State Guarantee:**
   Task state and event telemetry survive unexpected process termination. State persistence occurs atomically prior to and immediately following each executor step.

3. **Normalized Executor Output Guarantee:**
   Every executor produces normalized output containing status, stdout/stderr, files changed, duration, and error categorization.

4. **Safety & Policy Precedence:**
   Dangerous commands, path traversal attempts, and modifications to protected files are blocked prior to executor dispatch regardless of model prompt or reasoning directive.

5. **Human Approval Precedence:**
   When human intervention is requested (`ASK_HUMAN`) or safety thresholds mandate confirmation, execution halts in a durable `PAUSED`/`BLOCKED` state until explicit human input is received.

6. **Repository Integrity Guarantee:**
   Pre-existing user work outside the scope of Polyphony's task execution must be preserved. Checkpoint baselines record pre-execution repository state.

7. **Auditability & Provenance Guarantee:**
   Every task execution can be reconstructed chronologically via structured JSONL event streams, execution histories, and generated summary reports.

8. **Verifiable Completion Guarantee:**
   A task is marked completed only when verifiable evidence (file modifications, test execution, or explicit deterministic assertions) confirms completion. Zero-change false completions are rejected.
