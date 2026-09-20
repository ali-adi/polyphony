"""Token budgets and adaptive token allocation subsystem.

Section 21: Token Budgets
Allow CLI:
    polyphony start --goal "implement X" --token-budget 50000
Or config:
    budget:
      total_tokens: 50000
      lead: 15000
      execution: 25000
      verification: 5000
      reserve: 5000

Dynamic remaining budget allocation:
Polyphony may compact context, switch executor, perform deterministic verification,
request human input, stop, or use a lower-cost strategy when remaining budget is tight.

Section 22: Adaptive Token Allocation
Do not divide the budget equally.
Allocate based on task complexity:
- Simple bugfix: small lead budget, larger implementation budget, deterministic verification
- Architecture redesign: larger lead budget, implementation, independent review, verification
- Reserve some budget for unexpected failures.
- Never spend the entire budget before verification.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Union

from orchestrator.task_types import TaskType

logger = logging.getLogger("polyphony.budgets")


class BudgetHealth(str, Enum):
    HEALTHY = "HEALTHY"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"
    EXHAUSTED = "EXHAUSTED"


@dataclass
class BudgetStatus:
    health: BudgetHealth
    total_tokens: int
    total_spent: int
    remaining_tokens: int
    recommendations: List[str]
    breakdown: Dict[str, int]


@dataclass
class TokenBudget:
    """Manages stage-specific token budgets, spends, and dynamic actions."""
    total_tokens: int = 50000
    lead: int = 15000
    execution: int = 25000
    verification: int = 5000
    reserve: int = 5000

    spent_lead: int = 0
    spent_execution: int = 0
    spent_verification: int = 0
    spent_reserve: int = 0

    def record_spend(self, stage: str, tokens: int) -> None:
        """Record tokens spent in a particular stage."""
        stage_clean = stage.lower()
        if "lead" in stage_clean or "plan" in stage_clean or "reason" in stage_clean:
            self.spent_lead += tokens
        elif "exec" in stage_clean or "code" in stage_clean or "implement" in stage_clean:
            self.spent_execution += tokens
        elif "verif" in stage_clean or "test" in stage_clean:
            self.spent_verification += tokens
        elif "reserve" in stage_clean:
            self.spent_reserve += tokens
        else:
            self.spent_execution += tokens

    @property
    def total_spent(self) -> int:
        return self.spent_lead + self.spent_execution + self.spent_verification + self.spent_reserve

    @property
    def remaining(self) -> int:
        return self.total_tokens - self.total_spent

    def remaining_breakdown(self) -> Dict[str, int]:
        return {
            "lead": max(0, self.lead - self.spent_lead),
            "execution": max(0, self.execution - self.spent_execution),
            "verification": max(0, self.verification - self.spent_verification),
            "reserve": max(0, self.reserve - self.spent_reserve),
            "total_remaining": self.remaining,
        }

    def evaluate_status(self) -> BudgetStatus:
        """Dynamically evaluates budget status and suggests actions.

        Section 21:
        In tight situations, Polyphony may:
        - compact context
        - switch executor
        - perform deterministic verification
        - request human input
        - stop
        - use a lower-cost strategy
        """
        rem = self.remaining
        breakdown = self.remaining_breakdown()

        if rem <= 0:
            return BudgetStatus(
                health=BudgetHealth.EXHAUSTED,
                total_tokens=self.total_tokens,
                total_spent=self.total_spent,
                remaining_tokens=rem,
                recommendations=["stop", "request_human_input"],
                breakdown=breakdown,
            )

        # Critical threshold: Remaining budget has dipped into reserve / minimum verification
        critical_threshold = self.reserve + self.verification
        if rem <= critical_threshold:
            return BudgetStatus(
                health=BudgetHealth.CRITICAL,
                total_tokens=self.total_tokens,
                total_spent=self.total_spent,
                remaining_tokens=rem,
                recommendations=[
                    "compact_context",
                    "switch_executor",
                    "perform_deterministic_verification",
                    "use_lower_cost_strategy",
                ],
                breakdown=breakdown,
            )

        # Warning threshold: 35% or less remaining
        if rem <= int(self.total_tokens * 0.35):
            return BudgetStatus(
                health=BudgetHealth.WARNING,
                total_tokens=self.total_tokens,
                total_spent=self.total_spent,
                remaining_tokens=rem,
                recommendations=[
                    "compact_context",
                    "use_lower_cost_strategy",
                ],
                breakdown=breakdown,
            )

        return BudgetStatus(
            health=BudgetHealth.HEALTHY,
            total_tokens=self.total_tokens,
            total_spent=self.total_spent,
            remaining_tokens=rem,
            recommendations=[],
            breakdown=breakdown,
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_tokens": self.total_tokens,
            "allocated": {
                "lead": self.lead,
                "execution": self.execution,
                "verification": self.verification,
                "reserve": self.reserve,
            },
            "spent": {
                "lead": self.spent_lead,
                "execution": self.spent_execution,
                "verification": self.spent_verification,
                "reserve": self.spent_reserve,
                "total": self.total_spent,
            },
            "remaining": self.remaining,
            "breakdown": self.remaining_breakdown(),
            "status": self.evaluate_status().health.value,
        }


class AdaptiveBudgetAllocator:
    """Adapts token budget allocations based on task complexity and type (Section 22)."""

    @staticmethod
    def allocate_by_task(
        task_type: Union[TaskType, str],
        total_tokens: int = 50000,
        complexity: str = "medium",
    ) -> TokenBudget:
        """Section 22:
        Simple bugfix:
        -> small lead budget
        -> larger implementation budget
        -> deterministic verification

        Architecture redesign:
        -> larger lead budget
        -> implementation
        -> independent review
        -> verification

        Reserve some budget for unexpected failures.
        Never spend the entire budget before verification.
        """
        t_type = (task_type.value if isinstance(task_type, TaskType) else str(task_type)).lower()
        comp = complexity.lower()

        # Minimum reserve for unexpected failures: at least 10%
        reserve_ratio = 0.15 if comp == "high" else 0.10
        reserve = int(total_tokens * reserve_ratio)
        allocable = total_tokens - reserve

        if t_type in ("bugfix", "bug", "fix", "maintenance"):
            # Simple bugfix: small lead budget, larger implementation budget
            lead_ratio = 0.15
            exec_ratio = 0.65
            verif_ratio = 0.20
        elif t_type in ("refactor", "architecture", "redesign", "feature"):
            # Architecture redesign / feature: larger lead budget
            lead_ratio = 0.40
            exec_ratio = 0.40
            verif_ratio = 0.20
        elif t_type in ("research", "experiment"):
            # Research: heavy reasoning, lighter implementation
            lead_ratio = 0.60
            exec_ratio = 0.25
            verif_ratio = 0.15
        elif t_type in ("verification", "audit"):
            # Verification heavy
            lead_ratio = 0.20
            exec_ratio = 0.20
            verif_ratio = 0.60
        else:
            # Default balanced
            lead_ratio = 0.30
            exec_ratio = 0.50
            verif_ratio = 0.20

        lead = int(allocable * lead_ratio)
        execution = int(allocable * exec_ratio)
        # Ensure verification gets at least 10% of total tokens so it is never starved
        verification = max(int(allocable * verif_ratio), int(total_tokens * 0.10))

        # Adjust execution to exact sum
        execution = total_tokens - (lead + verification + reserve)

        return TokenBudget(
            total_tokens=total_tokens,
            lead=lead,
            execution=execution,
            verification=verification,
            reserve=reserve,
        )

    @staticmethod
    def reallocate_remaining(budget: TokenBudget) -> TokenBudget:
        """Dynamically reallocates remaining unused tokens to future stages."""
        rem = budget.remaining
        if rem <= 0:
            return budget

        # Protect verification and reserve
        protected_verif = max(budget.verification - budget.spent_verification, int(budget.total_tokens * 0.10))
        protected_reserve = max(budget.reserve - budget.spent_reserve, int(budget.total_tokens * 0.05))

        unreserved = rem - (protected_verif + protected_reserve)
        if unreserved > 0:
            # Allocate remainder between lead and execution
            budget.lead = budget.spent_lead + int(unreserved * 0.3)
            budget.execution = budget.spent_execution + int(unreserved * 0.7)
            budget.verification = budget.spent_verification + protected_verif
            budget.reserve = budget.spent_reserve + protected_reserve

        return budget
