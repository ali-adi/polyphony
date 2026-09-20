"""Review and verification subsystem with specialized reviewer modes (Section 34).

Section 34: Review and Verification Agents
Workflow:
Planner -> Implementer -> Reviewer -> Verifier

Reviewer modes:
- correctness reviewer
- security reviewer
- architecture reviewer
- test reviewer
- performance reviewer

Reviewers receive evidence and diffs rather than the entire raw history.
"""

from __future__ import annotations

import logging
import re
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger("polyphony.reviewers")


class ReviewerMode(str, Enum):
    CORRECTNESS = "correctness"
    SECURITY = "security"
    ARCHITECTURE = "architecture"
    TEST = "test"
    PERFORMANCE = "performance"


@dataclass
class ReviewReport:
    """Structured evaluation returned by a reviewer."""
    mode: ReviewerMode
    approved: bool
    score: float  # 0.0 to 1.0
    findings: List[str] = field(default_factory=list)
    risks: List[str] = field(default_factory=list)
    suggested_fixes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["mode"] = self.mode.value
        return d


class ReviewerContextBuilder:
    """Builds lightweight context for reviewers focusing on diffs and evidence rather than transcripts."""

    @staticmethod
    def build_context(
        mode: ReviewerMode,
        goal: str,
        diff: str,
        test_evidence: Optional[Dict[str, Any]] = None,
        static_evidence: Optional[Dict[str, Any]] = None,
        conventions: Optional[str] = None,
    ) -> str:
        parts = [
            f"# Specialized Review: {mode.value.upper()}",
            f"## Objective: {goal}",
            "",
            "## Changes Under Review (Diff):",
            f"```diff\n{diff.strip() if diff.strip() else '(No diff)'}\n```",
        ]

        if test_evidence:
            parts.extend([
                "",
                "## Test Evidence:",
                f"- Passed: {test_evidence.get('passed', 0)}",
                f"- Failed: {test_evidence.get('failed', 0)}",
                f"- Output Summary: {test_evidence.get('summary', 'Tests executed successfully')}",
            ])

        if static_evidence:
            parts.extend([
                "",
                "## Static Analysis Evidence:",
                f"- Clean: {static_evidence.get('clean', True)}",
                f"- Findings: {len(static_evidence.get('findings', []))}",
            ])

        if conventions:
            parts.extend([
                "",
                f"## Relevant Conventions:\n{conventions.strip()}",
            ])

        return "\n".join(parts)


class ReviewEngine:
    """Executes rule-based and static verification for reviewer modes."""

    def review(
        self,
        mode: ReviewerMode,
        goal: str,
        diff: str,
        test_evidence: Optional[Dict[str, Any]] = None,
        static_evidence: Optional[Dict[str, Any]] = None,
    ) -> ReviewReport:
        """Evaluate diff and evidence under the requested reviewer mode."""
        findings: List[str] = []
        risks: List[str] = []
        fixes: List[str] = []

        diff_clean = diff.strip()

        if mode == ReviewerMode.SECURITY:
            # Check for secrets, dangerous calls
            secret_patterns = [
                (r"(?i)(api[_-]?key|password|secret|token)\s*=\s*['\"][A-Za-z0-9_\-\.]{8,}['\"]", "Possible hardcoded credential or secret token"),
                (r"\bos\.system\(", "Dangerous call to os.system() (prefer subprocess.run with argument list)"),
                (r"\beval\(", "Dangerous call to eval()"),
                (r"\bexec\(", "Dangerous call to exec()"),
            ]
            for pat, desc in secret_patterns:
                if re.search(pat, diff_clean):
                    findings.append(f"Security Alert: {desc}")
                    risks.append("Potential security vulnerability or credential leak")
                    fixes.append("Refactor to safe parameterization or environment variable lookup")

            approved = len(findings) == 0
            score = 1.0 if approved else 0.4
            return ReviewReport(mode=mode, approved=approved, score=score, findings=findings, risks=risks, suggested_fixes=fixes)

        elif mode == ReviewerMode.TEST:
            # Check if tests were added/updated
            has_test_file = any(line.startswith("+++ b/tests/") or line.startswith("--- a/tests/") for line in diff_clean.splitlines())
            has_assert = "assert " in diff_clean
            tests_run = test_evidence and test_evidence.get("passed", 0) > 0
            tests_failed = test_evidence and test_evidence.get("failed", 0) > 0

            if tests_failed:
                findings.append(f"Test suite has {test_evidence['failed']} failing tests")
                risks.append("Regression introduced")
                fixes.append("Fix failing assertions before merging")
            elif not has_test_file and not has_assert:
                findings.append("No new test assertions or test files were included in the diff")
                risks.append("Unverified code changes")
                fixes.append("Add unit tests covering modified functions")

            approved = not tests_failed and (has_test_file or has_assert or tests_run)
            score = 1.0 if (not tests_failed and has_test_file) else (0.7 if approved else 0.3)
            return ReviewReport(mode=mode, approved=approved, score=score, findings=findings, risks=risks, suggested_fixes=fixes)

        elif mode == ReviewerMode.PERFORMANCE:
            # Check for nested loops or unindexed queries
            perf_patterns = [
                (r"for\s+\w+\s+in\s+.*:\s*\n[\s\+]*for\s+\w+\s+in", "Detected nested loop in diff (potential O(N^2) complexity)"),
                (r"time\.sleep\(", "Hardcoded sleep detected"),
            ]
            for pat, desc in perf_patterns:
                if re.search(pat, diff_clean):
                    findings.append(f"Performance Concern: {desc}")
                    risks.append("Latency degradation under large inputs")
                    fixes.append("Consider dictionary lookup or caching to reduce algorithmic complexity")

            approved = len(findings) == 0
            score = 1.0 if approved else 0.6
            return ReviewReport(mode=mode, approved=approved, score=score, findings=findings, risks=risks, suggested_fixes=fixes)

        elif mode == ReviewerMode.ARCHITECTURE:
            # Check for circular imports or monolithic functions
            if "import *" in diff_clean:
                findings.append("Wildcard import 'import *' detected")
                risks.append("Namespace pollution and implicit dependencies")
                fixes.append("Use explicit named imports")

            approved = len(findings) == 0
            score = 1.0 if approved else 0.7
            return ReviewReport(mode=mode, approved=approved, score=score, findings=findings, risks=risks, suggested_fixes=fixes)

        else:  # CORRECTNESS
            # General correctness check
            if not diff_clean:
                findings.append("Empty diff: no changes were implemented")
                risks.append("Goal incomplete")
                fixes.append("Implement required functionality")
                approved = False
                score = 0.0
            else:
                approved = True
                score = 0.95

            return ReviewReport(mode=mode, approved=approved, score=score, findings=findings, risks=risks, suggested_fixes=fixes)
