---
name: benchmarking
description: Protocol for conducting variance-controlled, statistically sound benchmark runs and metric comparisons.
---

# Benchmarking Protocol

A reliable engineering procedure for evaluating system latency, throughput, memory, or quality metrics while isolating environmental noise.

## Core Tenets
1. **Warmup is mandatory**: Always discard initial run JIT / cache cold-start artifacts.
2. **Control variance**: Execute multiple iterations to observe distribution (p50, p95, p99, std dev), not just a single sample.
3. **Isolate external factors**: Benchmarks must run under fixed hardware, disabled background noise, and identical inputs.
4. **Reproducible harness**: Benchmarking harnesses must be scripted and checked into version control.

---

## The 6-Step Benchmarking Procedure

### 1. Harness Preparation
- Write a self-contained, reproducible benchmark script (e.g., `benchmark.py` or a dedicated pytest benchmark target).
- Define input datasets of deterministic size and complexity.
- Ensure the harness captures both wall-clock elapsed time and resource metrics (e.g. peak memory).

### 2. Warmup Execution
- Execute at least 1-3 warmup runs to prime:
  - Bytecode/JIT compilation
  - Memory caches and disk page caches
  - Connection or thread pools
- Discard metrics recorded during the warmup phase.

### 3. Measurement Runs
- Execute a minimum of $N \ge 5$ iterations (or $N \ge 10$ for high-variance tasks).
- For each run, record raw latency values in milliseconds.
- Avoid printing excessive log output or running CPU-heavy background tasks during collection.

### 4. Statistical Aggregation
Compute statistical summaries across the collected runs:
- **Mean & Standard Deviation**: Check if std dev is $< 5\%$ of the mean. If std dev is high, investigate environmental noise.
- **Percentiles**:
  - `p50` (Median latency)
  - `p95` (Near worst-case latency)
  - `p99` (Tail latency)
- **Peak Memory**: Maximum resident set size (RSS) during execution.

### 5. Metric Extraction & Emitting
Extract metrics into standard numerical key-value pairs suitable for `ExecutorResult.metrics` and `IterationRecord.metrics`:
```json
{
  "baseline_p50_ms": 124.5,
  "candidate_p50_ms": 78.2,
  "speedup_ratio": 1.59,
  "peak_memory_mb": 42.1
}
```

### 6. Archiving & Comparison
- When evaluating candidates against a baseline, ensure both were executed under identical conditions on the same commit baseline.
- Archive the benchmark command, input configuration, and results table in the task record.
