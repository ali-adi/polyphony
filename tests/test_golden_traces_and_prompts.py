"""Tests for Golden Traces (Section 44) and Prompt Regression Testing (Section 45)."""

import pytest
from pathlib import Path

from orchestrator.golden_traces import (
    GoldenTrace,
    GoldenTraceStep,
    GoldenTraceSuite,
    TraceTolerance,
    compare_traces,
)
from orchestrator.prompt_testing import (
    PromptContextValidator,
    PromptTestSpec,
)


def test_golden_trace_serialization_and_fixtures(tmp_path: Path):
    suite = GoldenTraceSuite(root_dir=tmp_path)
    trace = suite.create_fixture("simple_bugfix")

    assert trace.scenario == "simple_bugfix"
    assert trace.final_status == "COMPLETED"
    assert len(trace.steps) == 1

    file_path = suite.record_trace(trace)
    assert file_path.exists()

    loaded = suite.load_scenario("simple_bugfix")
    assert len(loaded) == 1
    assert loaded[0].trace_id == trace.trace_id
    assert loaded[0].total_tokens == 3200


def test_golden_trace_comparison_regression_detection():
    suite = GoldenTraceSuite()
    golden = suite.create_fixture("simple_bugfix")

    # 1. Identical trace should have zero regressions
    current_ok = suite.create_fixture("simple_bugfix")
    res = compare_traces(golden, current_ok)
    assert not res.has_regression
    assert len(res.regressions) == 0

    # 2. Token regression: spent 5000 tokens instead of 3200 (> 20% increase)
    current_token_bloat = suite.create_fixture("simple_bugfix")
    current_token_bloat.total_tokens = 5000
    res = compare_traces(golden, current_token_bloat)
    assert res.has_regression
    assert any("Token regression" in r for r in res.regressions)

    # 3. Status regression
    current_failed = suite.create_fixture("simple_bugfix")
    current_failed.final_status = "FAILED"
    res = compare_traces(golden, current_failed)
    assert res.has_regression
    assert any("Completion regression" in r for r in res.regressions)

    # 4. Routing regression: routed to unexpected role or executor
    current_bad_routing = suite.create_fixture("simple_bugfix")
    current_bad_routing.steps[0].executor = "raw_bash"
    res = compare_traces(golden, current_bad_routing)
    assert res.has_regression
    assert any("Executor regression" in r for r in res.regressions)

    # 5. Safety regression
    current_unsafe = suite.create_fixture("simple_bugfix")
    current_unsafe.steps[0].safety_violations = ["Unauthorized file access"]
    res = compare_traces(golden, current_unsafe)
    assert res.has_regression
    assert any("Safety regression" in r for r in res.regressions)


def test_all_standard_fixtures():
    scenarios = [
        "simple_bugfix",
        "executor_timeout",
        "rollback",
        "human_question",
        "multi_iteration",
        "token_budget",
    ]
    for scenario in scenarios:
        trace = GoldenTraceSuite.create_fixture(scenario)
        assert trace.scenario == scenario
        assert trace.final_status == "COMPLETED"
        assert len(trace.steps) > 0


def test_prompt_regression_required_and_forbidden_content():
    spec = PromptTestSpec(
        name="test_lead_prompt",
        required_sections=["Task Objective", "Constraints"],
        required_substrings=["fix database connection", "strictly read-only"],
        forbidden_substrings=["drop database", "sudo rm -rf"],
    )

    good_prompt = (
        "# Lead Context\n\n"
        "## Task Objective:\nfix database connection\n\n"
        "## Constraints:\nstrictly read-only\n"
    )
    result = PromptContextValidator.validate(good_prompt, spec)
    assert result.passed
    assert len(result.violations) == 0

    bad_prompt = (
        "# Lead Context\n\n"
        "## Task Objective:\nfix database connection\n\n"
        "sudo rm -rf /var/lib\n"
    )
    result_bad = PromptContextValidator.validate(bad_prompt, spec)
    assert not result_bad.passed
    assert any("Missing required section: 'Constraints'" in v for v in result_bad.violations)
    assert any("Contains forbidden/irrelevant content" in v for v in result_bad.violations)


def test_prompt_regression_budgets_and_secrets():
    spec = PromptTestSpec(
        name="test_budget_and_secrets",
        max_characters=100,
        max_tokens=30,
        require_redacted_secrets=True,
    )

    clean_short_prompt = "Refactor database query to use parameterized queries."
    result = PromptContextValidator.validate(clean_short_prompt, spec)
    assert result.passed

    # Leaking OpenAI key
    leaky_prompt = "Refactor query with key sk-12345678901234567890123456"
    result_leaky = PromptContextValidator.validate(leaky_prompt, spec)
    assert not result_leaky.passed
    assert any("Unredacted sensitive credential detected" in v for v in result_leaky.violations)

    # Over budget
    huge_prompt = "Very long instruction " * 50
    result_huge = PromptContextValidator.validate(huge_prompt, spec)
    assert not result_huge.passed
    assert any("Character budget exceeded" in v for v in result_huge.violations)


def test_prompt_regression_structured_output_and_compression():
    spec = PromptTestSpec(
        name="test_structured_executor_output",
        structured_keys=["status", "summary", "files_changed", "tests"],
    )

    valid_yaml = (
        "status: SUCCESS\n"
        "summary: Fixed bug\n"
        "files_changed:\n  - file.py\n"
        "tests:\n  passed: 1\n  failed: 0\n"
    )
    result = PromptContextValidator.validate(valid_yaml, spec)
    assert result.passed

    invalid_yaml = "status: SUCCESS\nsummary: Missing other keys\n"
    result_invalid = PromptContextValidator.validate(invalid_yaml, spec)
    assert not result_invalid.passed
    assert any("Missing required key: 'files_changed'" in v for v in result_invalid.violations)

    # Test compression fidelity
    original = "The user wants to fix auth endpoint in auth.py, ensuring rate-limiting remains 100/min. Lots of irrelevant debug logs..."
    compressed = "Task: Fix auth in auth.py with rate-limiting 100/min preserved."
    fidelity = PromptContextValidator.test_compression_fidelity(
        original_context=original,
        compressed_context=compressed,
        key_facts=["auth.py", "100/min"],
        max_compressed_ratio=0.8,
    )
    assert fidelity.passed
    assert "auth.py" in fidelity.preserved_facts
    assert "100/min" in fidelity.preserved_facts
