"""Token optimization, context budgeting, and relevance filtering subsystem (Sections 13 & 14)."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple
from pydantic import BaseModel, Field


def calculate_reasoning_efficiency(useful_outcome_score: float, tokens_spent: int) -> float:
    """Calculates useful outcome / reasoning expenditure ratio (Section 13).

    useful_outcome_score: 0.0 to 1.0 (or normalized benchmark score)
    tokens_spent: total tokens expended
    """
    if tokens_spent <= 0:
        return float("inf") if useful_outcome_score > 0 else 0.0
    return round((useful_outcome_score * 10000.0) / float(tokens_spent), 4)


class ContextBudgetConfig(BaseModel):
    """Configurable context token budgets per role/stage (Section 14)."""
    lead: int = 30000
    implementation: int = 20000
    research: int = 16000
    verification: int = 8000


class RelevanceFilter:
    """Filters project rules, memories, and files based on relevance to the goal and target files."""

    @staticmethod
    def extract_keywords(text: str) -> Set[str]:
        words = re.findall(r"\b[a-zA-Z0-9_\-\.]{3,}\b", text.lower())
        stopwords = {
            "the", "and", "for", "with", "this", "that", "from", "have",
            "will", "when", "then", "into", "some", "more", "make", "over"
        }
        return {w for w in words if w not in stopwords}

    def filter_rules(self, rules: List[str], goal: str) -> List[str]:
        """Keep only rules relevant to goal keywords."""
        keywords = self.extract_keywords(goal)
        relevant = []
        for r in rules:
            r_lower = r.lower()
            if any(kw in r_lower for kw in keywords) or "always" in r_lower or "core" in r_lower:
                relevant.append(r)
        # If none matched, return top 3 rules as fallback
        return relevant if relevant else rules[:3]

    def filter_memories(self, memories: List[Dict[str, Any]], goal: str) -> List[Dict[str, Any]]:
        """Filter memory items based on keyword overlap with goal."""
        keywords = self.extract_keywords(goal)
        scored = []
        for m in memories:
            content = str(m.get("content", "")).lower()
            score = sum(1 for kw in keywords if kw in content)
            if score > 0:
                scored.append((score, m))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [m for _, m in scored[:5]]


class ContextDeduplicator:
    """Strips duplicate instructions, repeated decisions, and identical snippets."""

    def __init__(self):
        self._seen_hashes: Set[str] = set()

    def deduplicate_blocks(self, blocks: List[str]) -> List[str]:
        unique = []
        for b in blocks:
            clean = b.strip()
            if not clean:
                continue
            h = hashlib.sha256(clean.encode("utf-8")).hexdigest()
            if h not in self._seen_hashes:
                self._seen_hashes.add(h)
                unique.append(b)
        return unique


class DiffFirstContextBuilder:
    """Builds compact context after iteration 1 focusing on what changed, failed, and remains."""

    @staticmethod
    def build_iteration_diff_context(
        iteration: int,
        latest_diff: str,
        last_failure: Optional[str],
        remaining_criteria: List[str],
        budget_limit: int = 10000,
    ) -> str:
        """Constructs diff-first context strictly within budget."""
        parts = [
            f"=== ITERATION {iteration} DIFF-FIRST CONTEXT ===",
            "",
            "## 1. What Changed (Latest Diff):",
            latest_diff.strip() if latest_diff.strip() else "(No file changes in last step)",
            "",
            "## 2. What Failed / Current Diagnostics:",
            last_failure.strip() if last_failure else "(No failure reported)",
            "",
            "## 3. What Remains to Complete Goal:",
        ]
        if remaining_criteria:
            for c in remaining_criteria:
                parts.append(f"- [ ] {c}")
        else:
            parts.append("- [ ] Verify all tests pass and resolve pending items.")

        joined = "\n".join(parts)
        # Enforce budget truncation if needed (approx 4 chars per token)
        max_chars = budget_limit * 4
        if len(joined) > max_chars:
            joined = joined[:max_chars] + "\n\n... [Diff-first context truncated to budget limit]"
        return joined


class ContextBudgetManager:
    """Manages token budgets across orchestration roles."""

    def __init__(self, config: Optional[ContextBudgetConfig] = None):
        self.config = config or ContextBudgetConfig()
        self.usage: Dict[str, int] = {
            "lead": 0,
            "implementation": 0,
            "research": 0,
            "verification": 0,
        }

    def get_budget_for_role(self, role: str) -> int:
        role_lower = role.lower()
        if "lead" in role_lower or "reason" in role_lower:
            return self.config.lead
        elif "implement" in role_lower or "cursor" in role_lower or "code" in role_lower:
            return self.config.implementation
        elif "research" in role_lower:
            return self.config.research
        elif "verif" in role_lower or "test" in role_lower:
            return self.config.verification
        return 16000

    def record_usage(self, role: str, tokens: int) -> None:
        role_key = "lead"
        role_lower = role.lower()
        if "implement" in role_lower or "cursor" in role_lower:
            role_key = "implementation"
        elif "research" in role_lower:
            role_key = "research"
        elif "verif" in role_lower or "test" in role_lower:
            role_key = "verification"
        self.usage[role_key] = self.usage.get(role_key, 0) + tokens

    def is_within_budget(self, role: str) -> bool:
        budget = self.get_budget_for_role(role)
        role_key = "lead"
        role_lower = role.lower()
        if "implement" in role_lower:
            role_key = "implementation"
        elif "research" in role_lower:
            role_key = "research"
        elif "verif" in role_lower or "test" in role_lower:
            role_key = "verification"
        return self.usage.get(role_key, 0) <= budget


@dataclass
class TokenUsageRecord:
    """Individual token usage record complying with Section 20."""
    task_id: str
    iteration: int
    agent: str            # e.g., "lead", "implementer", "researcher", "verifier"
    executor: str         # e.g., "claude", "cursor", "agy", "python"
    model: str            # e.g., "claude-3-7-sonnet", "gpt-4o"
    decision: str         # e.g., "plan", "code", "review", "verify"
    prompt_tokens: int    # input tokens
    completion_tokens: int # output tokens
    prompt_snippet: Optional[str] = None
    result_snippet: Optional[str] = None
    is_reasoning_call: bool = False
    is_executor_call: bool = False
    context_size: int = 0
    cache_hit: bool = False
    redundant_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "iteration": self.iteration,
            "agent": self.agent,
            "executor": self.executor,
            "model": self.model,
            "decision": self.decision,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "prompt_snippet": self.prompt_snippet,
            "result_snippet": self.result_snippet,
            "is_reasoning_call": self.is_reasoning_call,
            "is_executor_call": self.is_executor_call,
            "context_size": self.context_size,
            "cache_hit": self.cache_hit,
            "redundant_tokens": self.redundant_tokens,
        }


class TokenUsageTracker:
    """Tracks and aggregates token usage per Section 20 requirements."""

    def __init__(self):
        self.records: List[TokenUsageRecord] = []
        self._successful_tasks: Set[str] = set()

    def record(
        self,
        task_id: str,
        iteration: int,
        agent: str,
        executor: str,
        model: str,
        decision: str,
        prompt_tokens: int,
        completion_tokens: int,
        prompt_snippet: Optional[str] = None,
        result_snippet: Optional[str] = None,
        is_reasoning_call: bool = False,
        is_executor_call: bool = False,
        context_size: Optional[int] = None,
        cache_hit: bool = False,
        redundant_tokens: int = 0,
    ) -> TokenUsageRecord:
        ctx_size = context_size if context_size is not None else prompt_tokens
        rec = TokenUsageRecord(
            task_id=task_id,
            iteration=iteration,
            agent=agent,
            executor=executor,
            model=model,
            decision=decision,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            prompt_snippet=prompt_snippet,
            result_snippet=result_snippet,
            is_reasoning_call=is_reasoning_call,
            is_executor_call=is_executor_call,
            context_size=ctx_size,
            cache_hit=cache_hit,
            redundant_tokens=redundant_tokens,
        )
        self.records.append(rec)
        return rec

    def mark_task_success(self, task_id: str) -> None:
        self._successful_tasks.add(task_id)

    def get_summary(self) -> Dict[str, Any]:
        """Generates usage summary matching Section 20 exact YAML specification."""
        lead_input = 0
        lead_output = 0
        executors_usage: Dict[str, Dict[str, int]] = {}

        total_input = 0
        total_output = 0

        llm_calls = 0
        executor_calls = 0
        reasoning_calls = 0

        iteration_tokens: Dict[int, int] = {}
        context_sizes: List[int] = []
        cache_hits = 0
        total_context_tokens = 0
        redundant_tokens_sum = 0

        for r in self.records:
            total_input += r.prompt_tokens
            total_output += r.completion_tokens

            if r.is_reasoning_call or "lead" in r.agent.lower():
                reasoning_calls += 1
                lead_input += r.prompt_tokens
                lead_output += r.completion_tokens
            else:
                llm_calls += 1

            if r.is_executor_call:
                executor_calls += 1

            exec_name = r.executor or "generic"
            if exec_name not in executors_usage:
                executors_usage[exec_name] = {"input_tokens": 0, "output_tokens": 0}
            executors_usage[exec_name]["input_tokens"] += r.prompt_tokens
            executors_usage[exec_name]["output_tokens"] += r.completion_tokens

            # Per iteration
            iteration_tokens[r.iteration] = iteration_tokens.get(r.iteration, 0) + r.total_tokens

            # Context metrics
            context_sizes.append(r.context_size)
            total_context_tokens += r.context_size
            redundant_tokens_sum += r.redundant_tokens
            if r.cache_hit:
                cache_hits += 1

        total_calls = len(self.records)
        avg_ctx_size = round(sum(context_sizes) / total_calls, 2) if total_calls > 0 else 0.0
        cache_hit_rate = round(cache_hits / total_calls, 4) if total_calls > 0 else 0.0
        redundant_ratio = round(redundant_tokens_sum / total_context_tokens, 4) if total_context_tokens > 0 else 0.0

        # Tokens per successful task
        successful_task_tokens = [
            sum(r.total_tokens for r in self.records if r.task_id == tid)
            for tid in self._successful_tasks
        ]
        avg_tokens_per_success = (
            round(sum(successful_task_tokens) / len(successful_task_tokens), 2)
            if successful_task_tokens
            else 0.0
        )

        return {
            "usage": {
                "lead": {
                    "input_tokens": lead_input,
                    "output_tokens": lead_output,
                },
                "executors": executors_usage,
                "total": {
                    "input": total_input,
                    "output": total_output,
                    "tokens": total_input + total_output,
                },
            },
            "metrics": {
                "llm_calls": total_calls,
                "executor_calls": executor_calls,
                "reasoning_calls": reasoning_calls,
                "tokens_per_iteration": iteration_tokens,
                "tokens_per_successful_task": avg_tokens_per_success,
                "average_context_size": avg_ctx_size,
                "cache_hit_rate": cache_hit_rate,
                "context_reuse": cache_hits,
                "redundant_context_ratio": redundant_ratio,
            },
        }

    def usage_by_task(self, task_id: str) -> Dict[str, int]:
        recs = [r for r in self.records if r.task_id == task_id]
        inp = sum(r.prompt_tokens for r in recs)
        out = sum(r.completion_tokens for r in recs)
        return {"input_tokens": inp, "output_tokens": out, "total": inp + out}

    def usage_by_agent(self, agent: str) -> Dict[str, int]:
        recs = [r for r in self.records if r.agent.lower() == agent.lower()]
        inp = sum(r.prompt_tokens for r in recs)
        out = sum(r.completion_tokens for r in recs)
        return {"input_tokens": inp, "output_tokens": out, "total": inp + out}

    def usage_by_model(self, model: str) -> Dict[str, int]:
        recs = [r for r in self.records if r.model == model]
        inp = sum(r.prompt_tokens for r in recs)
        out = sum(r.completion_tokens for r in recs)
        return {"input_tokens": inp, "output_tokens": out, "total": inp + out}

    def usage_by_decision(self, decision: str) -> Dict[str, int]:
        recs = [r for r in self.records if r.decision == decision]
        inp = sum(r.prompt_tokens for r in recs)
        out = sum(r.completion_tokens for r in recs)
        return {"input_tokens": inp, "output_tokens": out, "total": inp + out}
