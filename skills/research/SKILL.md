---
name: research
description: Protocol for codebase exploration, architecture inspection, pattern discovery, and dependency mapping.
---

# Research & Architecture Exploration Protocol

A systematic procedure for mapping unfamiliar codebases, discovering architectural patterns, and inspecting dependencies before authoring changes.

## Core Tenets
1. **Read before writing**: Understand existing architectural conventions and design patterns before introducing new abstractions.
2. **Minimize token footprint**: Search specifically for definitions, call sites, and schema files rather than dumping massive file trees into context.
3. **Trace call graphs end-to-end**: Follow the execution path from user entry point to state persistence.
4. **Identify constraints**: Pinpoint existing test harnesses, type constraints, and configuration files.

---

## The 5-Step Exploration Procedure

### 1. High-Level Anatomy Inspection
- Inspect root configuration files:
  - Package descriptors (`pyproject.toml`, `package.json`, `Cargo.toml`, etc.)
  - Project configuration (`project.yaml`, `.env.example`, `Makefile`)
- Locate primary entry points (e.g. CLI definitions, API routers, main loop).
- Note durable documentation if available (`architecture.md`, `decisions.md`, `known_issues.md`).

### 2. Dependency & Module Boundaries
- Map internal package boundaries and layer hierarchies:
  - Interfaces / Abstract Base Classes
  - Data models & Schemas (e.g. Pydantic models, dataclasses)
  - Core business logic / Orchestration
  - External I/O adapters / Executors / Database clients
- Identify circular dependency risks or leaky abstractions.

### 3. Pattern Discovery
- Find idiomatic patterns already established in the codebase:
  - Error handling and custom exception hierarchies
  - Logging conventions and context propagation
  - Dependency injection or factory patterns
  - Testing conventions (fixtures, mocks, unit vs integration splits)
- Adhere strictly to existing conventions to maintain codebase coherence.

### 4. Call-Graph & Execution Tracing
- Trace the lifecycle of a single canonical operation:
  - Ingestion / Argument parsing
  - Validation & Pre-execution checks
  - State transformation & execution
  - Persistence & reporting
- Note any subtle side-effects, locks, or subprocess invocations.

### 5. Research Synthesis
- Formulate a succinct mental model and document:
  - Files requiring modification
  - Interfaces to preserve or extend
  - Edge cases and invariants to uphold
  - Required test coverage
