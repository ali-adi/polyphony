# Polyphony Benchmark Suite

The Polyphony Benchmark Suite provides standardized, objective, and reproducible evaluation of multi-agent orchestration, token efficiency, safety, and reliability.

## Directory Structure

```text
benchmarks/
├── tasks/          # Declarative YAML benchmark task definitions
├── expected/       # Expected outcomes, acceptance assertions, and constraints
├── runners/        # Benchmark execution engine (benchmark_runner.py)
├── results/        # JSON results per benchmark run
├── reports/        # Markdown evaluation reports
└── README.md       # Benchmark documentation
```

## Evaluated Tasks (15 Core Scenarios)

1. `task_01_simple_bugfix`: ZeroDivisionError resolution in a single isolated function.
2. `task_02_multi_file_feature`: Coordinated feature addition across billing and invoice modules.
3. `task_03_existing_failing_test`: Resolving a pre-existing failing test suite without regression.
4. `task_04_refactor`: Code refactoring extracting common validator helpers without altering external API contracts.
5. `task_05_ambiguous_requirement`: Detection and halting (`ASK_HUMAN` / clarification) for underspecified requests.
6. `task_06_dependency_problem`: Graceful fallback and resolution when an optional third-party library is absent.
7. `task_07_executor_failure`: Automatic circuit-breaker failover and recovery when the primary executor crashes.
8. `task_08_zero_change_false_completion`: Verification that zero-change false completion claims are rejected.
9. `task_09_research_to_implementation`: Literature / algorithmic research followed by verified implementation.
10. `task_10_iterative_bugfix_multiple_attempts`: Multi-step iterative resolution of complex corner cases.
11. `task_11_large_context_task`: High-token repository context navigation within strict token budgets.
12. `task_12_misleading_repo_instructions`: Resilience against adversarial or misleading repository instructions.
13. `task_13_unrelated_preexisting_changes`: Isolation and preservation of uncommitted user work during task execution and rollback.
14. `task_14_human_clarification`: Halting on unresolvable conflicting requirements to solicit human input.
15. `task_15_deterministic_tooling_sufficient`: Zero-LLM token consumption when deterministic tools (e.g. pytest, git diff) suffice.

## Measured Metrics (20 Dimensions)

- **Correctness:** Boolean indicating if all expected assertions passed.
- **Completion rate:** Ratio of successfully completed tasks.
- **Iterations:** Total reasoning/execution cycles expended.
- **LLM calls:** Total invocations of lead reasoners.
- **Executor calls:** Total invocations of sub-agents/code editors.
- **Total tokens:** Input + output tokens across all agent calls.
- **Input tokens:** Prompt tokens sent to models.
- **Output tokens:** Completion tokens received from models.
- **Wall-clock time:** Execution elapsed time in seconds.
- **Human interventions:** Frequency of human pauses (`ASK_HUMAN`).
- **Failed attempts:** Number of failed execution cycles before recovery.
- **Recovery success:** Boolean indicating whether executor/step failure was successfully mitigated.
- **Safety violations:** Count of rejected dangerous operations.
- **Rollback correctness:** Preservation of user-authored uncommitted modifications.
- **Diagnosis quality:** Precision of failure analysis and self-correction.
- **Report accuracy:** Completeness of generated Markdown artifact.
- **Context size:** Byte/token footprint of dispatched context.
- **Cache hit rate:** Percentage of prompts leveraging cached context.
- **Redundant-context ratio:** Proportion of duplicate context passed across iterations.
- **Tokens per successful task:** Token expenditure efficiency metric.

## Running Benchmarks

### Via Python:
```bash
python3 -m benchmarks.runners.benchmark_runner
```

### Via Polyphony CLI:
```bash
polyphony benchmark
```
