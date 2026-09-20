"""Tests for Orchestration DAG (Section 32: Orchestration DAG)."""

import time
import pytest
from orchestrator.dag import DAG, NodeStatus


def test_section_32_diagram_dag_execution():
    """Verify Section 32 workflow:
                     Research
                        │
              ┌─────────┴─────────┐
              ↓                   ↓
        Implementation        Alternative
              │                   │
              └─────────┬─────────┘
                        ↓
                      Review
                        ↓
                    Verification
    """
    dag = DAG()

    # 1. Research
    dag.add_node(
        "research",
        name="Research Stage",
        stage_type="research",
        fn=lambda ctx: {"findings": "Option A is faster, Option B has better cache hit rate"},
    )

    # 2. Fan-out: Implementation and Alternative
    dag.add_node(
        "implementation",
        name="Primary Implementation",
        stage_type="implementation",
        dependencies=["research"],
        fn=lambda ctx: {"code": "Implementation A"},
    )
    dag.add_node(
        "alternative",
        name="Alternative Implementation",
        stage_type="implementation",
        dependencies=["research"],
        fn=lambda ctx: {"code": "Implementation B (Alternative)"},
    )

    # 3. Fan-in: Review
    dag.add_node(
        "review",
        name="Review Stage",
        stage_type="review",
        dependencies=["implementation", "alternative"],
        fn=lambda ctx: {"selected": "Implementation A", "approved": True},
    )

    # 4. Verification
    dag.add_node(
        "verification",
        name="Verification Stage",
        stage_type="verification",
        dependencies=["review"],
        fn=lambda ctx: {"tests_passed": True, "status": "VERIFIED"},
    )

    result = dag.execute(concurrency=2)

    assert result["success"] is True
    assert set(result["completed"]) == {"research", "implementation", "alternative", "review", "verification"}
    assert result["context"]["review_result"]["selected"] == "Implementation A"
    assert result["context"]["verification_result"]["status"] == "VERIFIED"


def test_dag_cycle_detection():
    dag = DAG()
    dag.add_node("A", name="Node A", dependencies=["B"])
    dag.add_node("B", name="Node B", dependencies=["A"])

    with pytest.raises(ValueError, match="Cycle detected"):
        dag.validate()


def test_dag_retry_mechanism():
    dag = DAG()
    attempt = 0

    def flaky_fn(ctx):
        nonlocal attempt
        attempt += 1
        if attempt < 2:
            raise RuntimeError("Transient network error")
        return "success_on_attempt_2"

    dag.add_node("flaky", name="Flaky Node", max_retries=2, fn=flaky_fn)
    result = dag.execute()

    assert result["success"] is True
    assert dag.nodes["flaky"].retries_attempted == 1
    assert dag.nodes["flaky"].result == "success_on_attempt_2"


def test_dag_failure_propagation():
    """Verify Section 32: failure propagation downstream."""
    dag = DAG()

    def bad_fn(ctx):
        raise ValueError("Fatal syntax error")

    dag.add_node("root", name="Root", max_retries=0, fn=bad_fn)
    dag.add_node("child", name="Child", dependencies=["root"], fn=lambda ctx: "never_runs")

    result = dag.execute()
    assert result["success"] is False
    assert dag.nodes["root"].status == NodeStatus.FAILED
    assert dag.nodes["child"].status == NodeStatus.FAILED
    assert "Upstream dependency failed" in dag.nodes["child"].error


def test_dag_conditional_branching():
    """Verify Section 32: conditional branches."""
    dag = DAG()
    dag.add_node("start", name="Start", fn=lambda ctx: "started")

    # True condition runs
    dag.add_node(
        "branch_a",
        name="Branch A",
        dependencies=["start"],
        condition=lambda ctx: True,
        fn=lambda ctx: "ran_branch_a",
    )

    # False condition is skipped
    dag.add_node(
        "branch_b",
        name="Branch B",
        dependencies=["start"],
        condition=lambda ctx: False,
        fn=lambda ctx: "ran_branch_b",
    )

    result = dag.execute(initial_context={})
    assert result["success"] is True
    assert dag.nodes["branch_a"].status == NodeStatus.COMPLETED
    assert dag.nodes["branch_b"].status == NodeStatus.SKIPPED


def test_dag_cancellation():
    """Verify Section 32: cancellation."""
    dag = DAG()
    dag.add_node("node1", name="Node 1", fn=lambda ctx: time.sleep(0.01))
    dag.add_node("node2", name="Node 2", dependencies=["node1"], fn=lambda ctx: "done")

    dag.cancel()
    assert dag.nodes["node1"].status == NodeStatus.CANCELLED
    assert dag.nodes["node2"].status == NodeStatus.CANCELLED
