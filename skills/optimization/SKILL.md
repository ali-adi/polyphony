---
name: optimization
description: 10-step protocol for performance, latency, memory, and algorithmic optimization tasks without regressions.
---

# Optimization Protocol

A disciplined engineering procedure for optimizing retrieval, inference, execution latency, memory footprint, or algorithmic throughput.

## Core Tenets
1. **Never optimize without a baseline**: Guessing bottlenecks wastes tokens and causes code bloat.
2. **Never claim improvement without running benchmarks**: Benchmark candidate implementations under identical conditions.
3. **Reject regressions**: Any change that improves latency but breaks accuracy or test suites must be reverted immediately.

---

## The 10-Step Protocol

### Step 1: Establish Baseline
Run the target workload on the current unmodified code. Record:
- Latency (p50, p95, p99)
- Peak memory usage
- Resource consumption (CPU / GPU / Disk I/O)
- Accuracy or quality metric (precision, recall, output parity)

### Step 2: Define Success Criteria
Establish clear, quantitative goals:
- Target metric improvement (e.g. `latency_ms < 50ms`, `memory_reduction >= 30%`).
- Invariant tolerance (e.g. `0% accuracy regression`, `100% test pass rate`).

### Step 3: Profile & Identify the Real Bottleneck
Use deterministic profiling (`cProfile`, `py-spy`, `memory_profiler`, or time-traced logs):
- Is the bottleneck I/O, serialization, database queries, unvectorized loops, or redundant compute?
- Pinpoint the exact function or loop accounting for >= 60% of runtime.

### Step 4: Formulate a Single Hypothesis
State the proposed change clearly:
- *"Replacing dict scans with a hashed lookup table will reduce O(N) traversal in `resolve_code()` to O(1)."*

### Step 5: Implement Controlled Change
- Make the minimal required modification.
- Avoid unrelated refactoring or style cleanups that pollute the benchmark signal.
- Ensure all target files are explicitly defined in the task brief.

### Step 6: Run Regression & Unit Tests
Run `pytest` on the test suite. If tests fail, the change is invalid regardless of speedup.

### Step 7: Benchmark Candidate Implementation
Execute the benchmark harness multiple times under identical workload and hardware conditions to control for variance.

### Step 8: Compare Against Baseline
Compute relative delta:
- Speedup ratio: `Baseline / Candidate`
- Absolute difference: `Baseline_ms - Candidate_ms`

### Step 9: Revert If Regression Occurs
If latency increased, memory swelled, or precision dropped below threshold:
- Revert the change immediately.
- Formulate an alternative hypothesis.

### Step 10: Record Conclusion & Durable Learnings
Emit a structured summary of findings and save the conclusion in `projects/<project>/decisions.md`.
