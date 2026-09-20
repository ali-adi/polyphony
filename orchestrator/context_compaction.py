"""Deterministic and schema-driven context compaction (Section 24).

Section 24: Context Compaction
For long-running tasks:
Iteration 1, Iteration 2, Iteration 3, ...
eventually becomes:
```yaml
task_summary:
current_state:
successful_changes:
failed_attempts:
remaining_problem:
important_decisions:
known_risks:
verification_status:
```

Keep raw history locally.
Compaction is:
- deterministic where possible
- schema-driven
- versioned
- recoverable
Never destroy the original evidence.
"""

from __future__ import annotations

import datetime
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field
import yaml

logger = logging.getLogger("polyphony.context_compaction")


class CompactedContextSchema(BaseModel):
    """Schema-driven, versioned, recoverable compacted context."""
    version: int = 1
    task_id: str
    created_at: str = Field(default_factory=lambda: datetime.datetime.now().isoformat())
    compacted_iterations_count: int = 0
    raw_history_ref: Optional[str] = None

    task_summary: str = ""
    current_state: str = ""
    successful_changes: List[str] = Field(default_factory=list)
    failed_attempts: List[str] = Field(default_factory=list)
    remaining_problem: str = ""
    important_decisions: List[str] = Field(default_factory=list)
    known_risks: List[str] = Field(default_factory=list)
    verification_status: str = "PENDING"

    def to_compact_yaml(self) -> str:
        """Returns clean YAML format matching Section 24 specification."""
        data = {
            "task_summary": self.task_summary,
            "current_state": self.current_state,
            "successful_changes": self.successful_changes,
            "failed_attempts": self.failed_attempts,
            "remaining_problem": self.remaining_problem,
            "important_decisions": self.important_decisions,
            "known_risks": self.known_risks,
            "verification_status": self.verification_status,
        }
        return yaml.dump(data, sort_keys=False, default_flow_style=False).strip()

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump()


class ContextCompactor:
    """Manages deterministic compaction while strictly preserving raw history locally."""

    @staticmethod
    def compact(
        task_id: str,
        goal: str,
        iterations: List[Any],  # IterationRecord or dicts
        raw_storage_dir: Optional[Union[str, Path]] = None,
        version: int = 1,
        remaining_problem: Optional[str] = None,
    ) -> CompactedContextSchema:
        """Deterministically compresses past iterations into schema-driven summary.

        Preserves raw history locally for full recoverability.
        """
        successful_changes: List[str] = []
        failed_attempts: List[str] = []
        important_decisions: List[str] = []
        known_risks: List[str] = []
        last_verification = "PENDING"

        # 1. Deterministic extraction from iterations
        seen_files = set()
        for it in iterations:
            it_dict = it if isinstance(it, dict) else (it.model_dump() if hasattr(it, "model_dump") else it.__dict__)
            it_num = it_dict.get("iteration_number", 0)
            lead_decision = it_dict.get("lead_decision") or {}
            exec_res = it_dict.get("execution_result") or {}
            tests_passed = it_dict.get("tests_passed")

            # Extract decisions
            action = lead_decision.get("action")
            rationale = lead_decision.get("rationale") or lead_decision.get("plan")
            if action:
                decision_str = f"Iter {it_num}: {action}" + (f" - {rationale}" if rationale else "")
                if decision_str not in important_decisions:
                    important_decisions.append(decision_str)

            # Extract successes and changes
            files = it_dict.get("files_changed") or []
            if isinstance(exec_res, dict):
                files = files or exec_res.get("files_changed", [])
            for f in files:
                if f not in seen_files:
                    seen_files.add(f)
                    successful_changes.append(f"Modified/created `{f}` in iteration {it_num}")

            # Extract failures
            if tests_passed is False:
                t_out = it_dict.get("test_output") or "Test suite failure"
                t_first_line = t_out.strip().splitlines()[-1] if t_out.strip() else "Tests failed"
                failed_attempts.append(f"Iter {it_num} test failure: {t_first_line}")
            if isinstance(exec_res, dict) and not exec_res.get("success", True):
                err = exec_res.get("error") or "Executor failed"
                failed_attempts.append(f"Iter {it_num} execution failure: {err}")

            # Verification status
            if tests_passed is True:
                last_verification = "PASSED (all automated tests passed)"
            elif tests_passed is False:
                last_verification = "FAILED (tests failed in latest run)"

            # Risks / Warnings
            if isinstance(exec_res, dict):
                risks = exec_res.get("remaining_risks") or exec_res.get("warnings") or []
                for r in risks:
                    if r not in known_risks:
                        known_risks.append(r)

        # 2. Persist raw history for recoverability
        raw_ref = None
        if raw_storage_dir:
            store_dir = Path(raw_storage_dir).resolve()
            store_dir.mkdir(parents=True, exist_ok=True)
            raw_path = store_dir / f"raw_history_v{version}.json"
            raw_data = [
                it if isinstance(it, dict) else (it.model_dump() if hasattr(it, "model_dump") else it.__dict__)
                for it in iterations
            ]
            raw_path.write_text(json.dumps(raw_data, indent=2, default=str), encoding="utf-8")
            raw_ref = str(raw_path)

        task_summary = f"Goal: {goal} (processed {len(iterations)} iterations)"
        current_state = f"Iteration {len(iterations)} complete. {len(seen_files)} files modified across {len(iterations)} cycles."

        if not remaining_problem:
            remaining_problem = (
                "Resolve failures from previous attempts and verify criteria."
                if failed_attempts
                else "Finalize verification and verify all acceptance criteria."
            )

        return CompactedContextSchema(
            version=version,
            task_id=task_id,
            compacted_iterations_count=len(iterations),
            raw_history_ref=raw_ref,
            task_summary=task_summary,
            current_state=current_state,
            successful_changes=successful_changes,
            failed_attempts=failed_attempts,
            remaining_problem=remaining_problem,
            important_decisions=important_decisions,
            known_risks=known_risks,
            verification_status=last_verification,
        )

    @staticmethod
    def recover_raw_history(compacted: CompactedContextSchema) -> List[Dict[str, Any]]:
        """Recovers the full raw historical iterations from the preserved reference."""
        if not compacted.raw_history_ref:
            return []
        p = Path(compacted.raw_history_ref)
        if not p.exists():
            raise FileNotFoundError(f"Raw history file not found: {p}")
        return json.loads(p.read_text(encoding="utf-8"))
