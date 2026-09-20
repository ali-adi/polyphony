"""Tests for Review and Verification Agents (Section 34: Review and Verification Agents)."""

import pytest
from orchestrator.reviewers import (
    ReviewEngine,
    ReviewReport,
    ReviewerContextBuilder,
    ReviewerMode,
)


def test_reviewer_context_builder_uses_evidence_and_diff():
    """Verify Section 34:
    Reviewers should receive evidence and diffs rather than the entire history.
    """
    ctx = ReviewerContextBuilder.build_context(
        mode=ReviewerMode.SECURITY,
        goal="Add API key authentication",
        diff="""+++ b/src/auth.py\n@@ -1,2 +1,3 @@\n+def check_key(k):\n+    return k == 'secret'\n""",
        test_evidence={"passed": 5, "failed": 0, "summary": "All tests passed"},
        static_evidence={"clean": True, "findings": []},
    )
    assert "Specialized Review: SECURITY" in ctx
    assert "+++ b/src/auth.py" in ctx
    assert "Test Evidence:" in ctx
    # Ensure no raw historical transcripts are in the prompt
    assert "raw historical transcript" not in ctx


def test_security_reviewer_catches_vulnerability():
    engine = ReviewEngine()
    insecure_diff = """+++ b/src/run.py\n+import os\n+os.system("rm -rf " + user_input)\n"""
    rep = engine.review(
        mode=ReviewerMode.SECURITY,
        goal="Execute command",
        diff=insecure_diff,
    )
    assert rep.approved is False
    assert rep.score < 0.5
    assert any("os.system" in f for f in rep.findings)
    assert len(rep.risks) > 0


def test_test_reviewer_catches_failures_and_missing_tests():
    engine = ReviewEngine()

    # Failing test evidence
    failing_rep = engine.review(
        mode=ReviewerMode.TEST,
        goal="Fix math bug",
        diff="+++ b/src/math.py\n+def add(a, b): return a + b\n",
        test_evidence={"passed": 2, "failed": 1},
    )
    assert failing_rep.approved is False
    assert "failing tests" in failing_rep.findings[0]

    # Passing test with test additions
    passing_rep = engine.review(
        mode=ReviewerMode.TEST,
        goal="Fix math bug",
        diff="+++ b/tests/test_math.py\n+def test_add(): assert add(1, 2) == 3\n",
        test_evidence={"passed": 3, "failed": 0},
    )
    assert passing_rep.approved is True
    assert passing_rep.score == 1.0


def test_performance_and_architecture_reviewers():
    engine = ReviewEngine()

    # Performance
    slow_diff = """+++ b/algo.py\n+for i in range(100):\n+    for j in range(100):\n+        process(i, j)\n"""
    perf_rep = engine.review(
        mode=ReviewerMode.PERFORMANCE,
        goal="Search matrix",
        diff=slow_diff,
    )
    assert perf_rep.approved is False
    assert any("nested loop" in f for f in perf_rep.findings)

    # Architecture
    arch_diff = """+++ b/main.py\n+from module import *\n"""
    arch_rep = engine.review(
        mode=ReviewerMode.ARCHITECTURE,
        goal="Import helpers",
        diff=arch_diff,
    )
    assert arch_rep.approved is False
    assert any("Wildcard import" in f for f in arch_rep.findings)
