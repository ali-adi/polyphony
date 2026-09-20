"""Tests for Agent-Specific Context Builders, Context Hierarchy, and Structured Outputs (Sections 15, 16, & 17)."""

import yaml
import pytest

from executors.base import ExecutorResult, ExecutorStatus
from orchestrator.context_builders import (
    AgentContextBuilder,
    ContextHierarchyCompressor,
    format_structured_executor_output,
)
from orchestrator.state import IterationRecord, TaskState, TaskStatus


def test_format_structured_executor_output():
    res = ExecutorResult(
        executor_name="cursor",
        status=ExecutorStatus.SUCCESS,
        summary="Fixed ICD-10 cache normalization.",
        files_changed=["coder/cache.py", "tests/test_cache.py"],
        tests={"passed": 19, "failed": 0},
    )

    out_yaml = format_structured_executor_output(
        res,
        remaining_risks=["No performance benchmark performed"],
        recommended_next_action="VERIFY",
    )

    parsed = yaml.safe_load(out_yaml)
    assert parsed["status"] == "SUCCESS"
    assert parsed["summary"] == "Fixed ICD-10 cache normalization."
    assert "coder/cache.py" in parsed["files_changed"]
    assert parsed["tests"]["passed"] == 19
    assert parsed["recommended_next_action"] == "VERIFY"
    assert "No performance benchmark performed" in parsed["remaining_risks"]


def test_context_hierarchy_compressor():
    iterations = [
        IterationRecord(
            iteration_number=1,
            lead_decision={"action": "DELEGATE", "executor": "cursor", "analysis": "Refactor helper"},
            executor_used="cursor",
            execution_result=ExecutorResult(executor_name="cursor", success=True, summary="Refactored helper function"),
            tests_passed=True,
            files_changed=["util.py"],
        ),
        IterationRecord(
            iteration_number=2,
            lead_decision={"action": "VERIFY", "executor": "python", "analysis": "Run full test suite"},
            executor_used="python",
            execution_result=ExecutorResult(executor_name="python", success=True, summary="Tests 100% green"),
            tests_passed=True,
            files_changed=[],
        ),
    ]

    compressed = ContextHierarchyCompressor.compress_iteration_records(iterations)
    assert len(compressed) == 2
    assert compressed[0]["iteration"] == 1
    assert compressed[0]["summary"] == "Refactored helper function"
    assert compressed[1]["action"] == "VERIFY"


def test_agent_context_builders():
    st = TaskState(
        task_id="task-ctx-1",
        project_name="proj",
        project_path="/proj",
        goal="Fix payment timeout",
        status=TaskStatus.RUNNING,
        current_iteration=1,
        max_iterations=5,
    )

    # Lead context
    lead_ctx = AgentContextBuilder.build_lead_context(
        st,
        relevant_evidence=["Error occurs after 30s socket timeout"],
        failure_history=["Attempt 1 failed because config was not reloaded"],
    )
    assert "Lead Reasoner Decision Context" in lead_ctx
    assert "Error occurs after 30s socket timeout" in lead_ctx
    assert "Attempt 1 failed because config was not reloaded" in lead_ctx

    # Implementer context
    impl_ctx = AgentContextBuilder.build_implementer_context(
        task_brief="Update timeout in client.py",
        target_files=["client.py"],
        acceptance_criteria=["Timeout is set to 60s", "All client tests pass"],
        conventions="PEP 8",
        relevant_code_snippets={"client.py": "TIMEOUT = 30"},
    )
    assert "Implementation Brief" in impl_ctx
    assert "client.py" in impl_ctx
    assert "PEP 8" in impl_ctx
    assert "TIMEOUT = 30" in impl_ctx

    # Researcher context
    res_ctx = AgentContextBuilder.build_researcher_context(
        research_question="What causes socket timeouts in urllib3 under macOS?",
        known_evidence=["Issue occurs under high concurrent SSL handshakes"],
        source_requirements=["Official Python documentation", "urllib3 issues"],
        desired_format="Markdown summary with code references",
    )
    assert "Research Specification" in res_ctx
    assert "socket timeouts" in res_ctx

    # Verifier context
    ver_ctx = AgentContextBuilder.build_verifier_context(
        expected_behavior="All requests complete within 60s without timeout exception",
        changed_files=["client.py"],
        acceptance_criteria=["client.py has TIMEOUT = 60"],
        test_commands=["pytest tests/test_client.py"],
    )
    assert "Verification Plan" in ver_ctx
    assert "pytest tests/test_client.py" in ver_ctx
