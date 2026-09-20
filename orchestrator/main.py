"""Core decision loop and orchestrator engine for Polyphony."""

from __future__ import annotations

import datetime
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional
import click
import yaml

from executors.base import ExecutorResult
from executors.router import ExecutorRouter
from orchestrator.context import (
    build_delegation_context_header,
    build_reasoning_prompt,
    build_system_prompt,
    build_user_prompt,
    load_project_knowledge,
    parse_reasoner_decision,
)
from orchestrator.logging import TaskLogger
from orchestrator.report import generate_task_report
from orchestrator.safety import SafetyConfig, SafetyEngine
from orchestrator.state import IterationRecord, StateManager, TaskState, TaskStatus


DECISION_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "analysis": {"type": "string"},
        "action": {"type": "string", "enum": ["DELEGATE", "VERIFY", "USE_SKILL", "ASK_HUMAN", "COMPLETE", "ABORT", "EXTEND"]},
        "executor": {"type": "string", "enum": ["agy", "cursor", "python", "claude"]},
        "target_files": {"type": "array", "items": {"type": "string"}},
        "skill": {"type": "string"},
        "question": {"type": "string"},
        "instruction": {"type": "string"},
        "learnings": {"type": "string"},
        "allow_zero_changes": {"type": "boolean"},
        "agent": {"type": "string"},
        "model": {"type": "string"},
        "thinking_level": {"type": "string", "enum": ["low", "medium", "high"]},
        "success_criteria": {"type": "array", "items": {"type": "string"}},
        "verification_needed": {"type": "boolean"},
        "metrics": {"type": "object", "additionalProperties": {"type": "number"}},
    },
    "required": ["analysis", "action"],
}


def _is_underspecified_delegation(decision: Dict[str, Any], instruction: str, target_executor: str) -> Tuple[bool, str]:
    """Validate that instructions delegated to coding agents are tightly scoped with target files."""
    if target_executor not in ("cursor", "agy", "claude"):
        return False, ""
    target_files = decision.get("target_files") or []
    import re
    has_file_ref = bool(re.search(r'[\w\-./]+\.(py|ts|js|jsx|tsx|go|rs|cpp|c|h|yaml|yml|json|md|toml|sql|html|css)\b', instruction))
    if not target_files and not has_file_ref:
        return True, (
            "Delegation rejected: Underspecified instruction. When delegating to a coding agent, "
            "you must provide a tightly scoped task brief specifying 'target_files' or explicit file paths "
            "and concrete boundaries (e.g. 'Modify auth/jwt.py lines 45-80 to use RS256; do not touch middleware.py')."
        )
    return False, ""


class Orchestrator:
    """Coordinates lead reasoning agent, executor adapters, safety gates, and state persistence."""

    def __init__(
        self,
        project_name: str,
        root_dir: str | Path = ".",
        read_only: bool = False,
        max_iterations: int = 10,
        preferred_lead: Optional[str] = None,
        cli_overrides: Optional[Dict[str, Any]] = None,
        history_window: int = 3,
        dry_run: bool = False,
        token_budget: Optional[int] = None,
    ):
        self.root_dir = Path(root_dir).resolve()
        self.project_name = project_name
        self.read_only = read_only
        self.max_iterations = max_iterations
        self.preferred_lead = preferred_lead
        self.cli_overrides = cli_overrides or {}
        self.history_window = history_window
        self.dry_run = dry_run
        self.token_budget_override = token_budget

        # 1. Load project definition & global config
        self.knowledge = load_project_knowledge(project_name, self.root_dir)
        self.project_cfg = self.knowledge.get("config", {})
        self.project_path = Path(self.project_cfg.get("path", self.root_dir / project_name)).resolve()

        if not self.project_path.exists():
            raise FileNotFoundError(f"Target project directory does not exist: {self.project_path}")

        global_path = self.root_dir / "config" / "global.yaml"
        self.global_cfg = {}
        if global_path.exists():
            with open(global_path, "r", encoding="utf-8") as f:
                self.global_cfg = yaml.safe_load(f) or {}

        from orchestrator.models_config import resolve_models_config
        self.models_config = resolve_models_config(
            global_cfg=self.global_cfg,
            project_cfg=self.project_cfg,
            cli_overrides=self.cli_overrides,
        )

        # 2. State and Safety
        self.state_mgr = StateManager(self.root_dir)
        from orchestrator.safety import resolve_safety_config
        self.safety_config = resolve_safety_config(
            global_cfg=self.global_cfg,
            project_cfg=self.project_cfg,
            read_only=self.read_only,
        )
        self.safety_engine = SafetyEngine(
            config=self.safety_config,
            project_root=str(self.project_path),
        )

        # 3. Router
        test_cfg = self.project_cfg.get("testing", {})
        python_bin = test_cfg.get("interpreter", "python3")
        self.router = ExecutorRouter(python_bin=python_bin)

        # 4. Token Budget & Adaptive Allocation (Sections 21 & 22)
        from orchestrator.budgets import AdaptiveBudgetAllocator, TokenBudget
        from orchestrator.task_types import TaskType
        budget_cfg = self.project_cfg.get("budget", {})
        total_tokens = self.token_budget_override or budget_cfg.get("total_tokens", 50000)
        if budget_cfg and not self.token_budget_override and "lead" in budget_cfg:
            self.budget = TokenBudget(
                total_tokens=total_tokens,
                lead=budget_cfg.get("lead", 15000),
                execution=budget_cfg.get("execution", 25000),
                verification=budget_cfg.get("verification", 5000),
                reserve=budget_cfg.get("reserve", 5000),
            )
        else:
            self.budget = AdaptiveBudgetAllocator.allocate_by_task(
                task_type=TaskType.FEATURE,
                total_tokens=total_tokens,
            )

    def _select_lead_reasoner(self) -> str:
        """Select primary reasoning engine, falling back to agy if Claude is rate-limited."""
        lead_choice = self.preferred_lead or self.project_cfg.get("executors", {}).get("lead")
        if lead_choice:
            return lead_choice

        claude_ex = self.router.get_executor("claude")
        if claude_ex and claude_ex.is_available():
            available, msg = claude_ex.check_quota_status()
            if available:
                return "claude"

        # Fallback to agy
        agy_ex = self.router.get_executor("agy")
        if agy_ex and agy_ex.is_available():
            return "agy"

        return "python"

    def run_task(self, goal: str) -> TaskState:
        """Run an autonomous task loop against the goal."""
        task_state = self.state_mgr.create_task(
            project_name=self.project_name,
            project_path=str(self.project_path),
            goal=goal,
            read_only=self.read_only,
            max_iterations=self.max_iterations,
        )
        task_state.status = TaskStatus.RUNNING
        self.state_mgr.save_state(task_state)
        return self._execute_task_loop(task_state)

    def resume_task(self, task_id: str, extra_iterations: Optional[int] = None) -> TaskState:
        """Resume an existing task from its saved state, extending iteration budget if needed."""
        task_state = self.state_mgr.load_state(self.project_name, task_id)
        if not task_state:
            raise FileNotFoundError(f"Task '{task_id}' not found for project '{self.project_name}'.")
        task_state.status = TaskStatus.RUNNING
        if task_state.current_iteration >= self.max_iterations:
            ext = extra_iterations or 5
            self.max_iterations = task_state.current_iteration + ext
            task_state.max_iterations = self.max_iterations
        self.state_mgr.save_state(task_state)
        return self._execute_task_loop(task_state)

    def _update_cost_and_budget(self, task_state: TaskState, rec: IterationRecord, logger: TaskLogger) -> bool:
        from orchestrator.report import estimate_iteration_tokens, estimate_token_cost_usd
        it_tokens = estimate_iteration_tokens(rec)
        it_cost = estimate_token_cost_usd(it_tokens)
        task_state.total_tokens += it_tokens
        task_state.total_cost_usd = round(task_state.total_cost_usd + it_cost, 4)
        logger._write_log("INFO", f"Tokens this round: ~{it_tokens:,} | Total tokens: ~{task_state.total_tokens:,} (~${task_state.total_cost_usd:.4f} USD)")

        if self.safety_config.max_cost_usd and task_state.total_cost_usd > self.safety_config.max_cost_usd:
            msg = f"Task exceeded maximum budget limit of ${self.safety_config.max_cost_usd:.2f} (current cost: ${task_state.total_cost_usd:.2f})"
            logger._write_log("ERROR", msg)
            task_state.status = TaskStatus.ABORTED
            task_state.error = msg
            self.state_mgr.complete_task(task_state, TaskStatus.ABORTED, error=msg)
            return False
        return True

    def _execute_task_loop(self, task_state: TaskState) -> TaskState:
        task_dir = self.state_mgr._get_task_dir(self.project_name, task_state.task_id)
        log_cfg = self.global_cfg.get("logging", {})
        log_dir_name = log_cfg.get("log_dir", "logs")
        log_file = task_dir / log_dir_name / "execution.log"
        logger = TaskLogger(task_state.task_id, log_file=log_file, logging_config=log_cfg)

        logger.header(f"Starting Task {task_state.task_id} for '{self.project_name}'")
        logger._write_log("INFO", f"Goal: {task_state.goal} | Read-Only: {self.read_only} | Dry-Run: {self.dry_run}")

        # Clean up any orphaned temp checkpoint commits left by previous interrupted runs
        if (self.project_path / ".git").exists():
            from executors.router import release_workspace_checkpoint
            release_workspace_checkpoint(str(self.project_path))

        # Choose lead reasoner
        lead_reasoner = self._select_lead_reasoner()
        logger._write_log("INFO", f"Active Lead Reasoner: {lead_reasoner}")

        # Automatic Git Branch Isolation if configured
        if self.safety_config.isolate_git_branch and not self.read_only and not self.dry_run:
            git_dir = self.project_path / ".git"
            if git_dir.exists():
                import subprocess
                branch_name = f"polyphony/{task_state.task_id}"
                res = subprocess.run(
                    ["git", "checkout", "-b", branch_name],
                    cwd=str(self.project_path),
                    capture_output=True,
                    text=True,
                )
                if res.returncode == 0:
                    logger._write_log("INFO", f"Isolated workspace changes to Git branch: {branch_name}")
                else:
                    logger._write_log("WARN", f"Could not create branch {branch_name}: {res.stderr.strip()}")

        lead_session_id: Optional[str] = task_state.lead_session_id
        executor_sessions: Dict[str, str] = dict(task_state.executor_sessions)
        initialized_sessions: set[str] = {f"{k}:{v}" for k, v in executor_sessions.items()}

        available_executors = [name for name, ok in self.router.get_available_executors().items() if ok]
        test_cmd = self.project_cfg.get("testing", {}).get("command")

        # 1. Build static system prompt once outside the loop to enable true prompt caching
        system_prompt = build_system_prompt(
            knowledge=self.knowledge,
            available_executors=available_executors,
            models_config=self.models_config,
            project_path=str(self.project_path),
        )

        import signal
        original_sigint = None
        try:
            original_sigint = signal.getsignal(signal.SIGINT)

            def handle_sigint(signum, frame):
                logger._write_log("WARN", f"Caught SIGINT (Ctrl+C). Aborting task {task_state.task_id} and saving checkpoint.")
                task_state.status = TaskStatus.ABORTED
                task_state.error = "Interrupted by operator (SIGINT)"
                self.state_mgr.save_state(task_state)
                logger.error("Execution interrupted by user. Task marked as ABORTED.")
                if original_sigint and callable(original_sigint):
                    original_sigint(signum, frame)
                else:
                    import sys
                    sys.exit(130)

            signal.signal(signal.SIGINT, handle_sigint)
        except (ValueError, AttributeError):
            pass

        consecutive_failures: int = 0
        last_error_text: str = ""
        escalation_header: str = ""

        try:
            while task_state.current_iteration < self.max_iterations:
                iter_num = task_state.current_iteration + 1
                logger.iteration(iter_num, self.max_iterations)

                # 1. Build dynamic user prompt
                user_prompt = build_user_prompt(
                    task_state=task_state,
                    history_window=self.history_window,
                )
                if escalation_header:
                    user_prompt = f"{escalation_header}\n\n{user_prompt}"
                    escalation_header = ""

                reasoner_ex = self.router.get_executor(lead_reasoner)
                if not reasoner_ex:
                    reasoner_ex = self.router.get_executor("agy") or self.router.get_executor("python")

                lead_profile = self.models_config.lead.get(lead_reasoner)
                lead_model = lead_profile.model if lead_profile else None
                lead_thinking = lead_profile.thinking_level if lead_profile else None

                # Dynamic thinking effort downgrade for verification/inspection iterations
                if task_state.iterations:
                    last_act = task_state.iterations[-1].lead_decision.get("action")
                    if last_act in ("VERIFY", "USE_SKILL") and lead_thinking == "high":
                        lead_thinking = "low"

                # Split prompt: pass system_prompt to Claude or combine for others
                if lead_reasoner == "claude":
                    instruction_arg = user_prompt
                    sys_prompt_arg = system_prompt
                else:
                    instruction_arg = f"{system_prompt}\n\n---\n\n{user_prompt}"
                    sys_prompt_arg = None

                reason_kwargs = {
                    "instruction": instruction_arg,
                    "cwd": str(self.project_path),
                    "read_only": True,
                    "timeout_seconds": 180,
                    "model": lead_model,
                    "thinking_level": lead_thinking,
                    "system_prompt": sys_prompt_arg,
                    "session_id": lead_session_id,
                }
                if lead_reasoner == "claude":
                    reason_kwargs["output_format"] = "json"
                elif lead_reasoner == "agy":
                    reason_kwargs["output_format"] = "json"
                    reason_kwargs["json_schema"] = json.dumps(DECISION_JSON_SCHEMA)

                reason_res = reasoner_ex.execute(**reason_kwargs)

                # Track lead session ID if returned and persist to task_state
                if reason_res.metadata.get("session_id"):
                    lead_session_id = reason_res.metadata["session_id"]
                    task_state.lead_session_id = lead_session_id

                # Mid-task lead reasoner failover if primary fails with infrastructure/quota error
                if not reason_res.success and (
                    reason_res.metadata.get("quota_exceeded")
                    or "rate limit" in (reason_res.error or "").lower()
                    or reason_res.exit_code in (124, 127)
                ):
                    if lead_reasoner != "agy":
                        logger._write_log("WARN", f"Lead reasoner '{lead_reasoner}' failed ({reason_res.error}). Failing over to 'agy' mid-task.")
                        lead_reasoner = "agy"
                        reasoner_ex = self.router.get_executor("agy") or self.router.get_executor("python")
                        lead_profile = self.models_config.lead.get(lead_reasoner)
                        lead_model = lead_profile.model if lead_profile else None
                        lead_thinking = lead_profile.thinking_level if lead_profile else None
                        reason_res = reasoner_ex.execute(
                            instruction=f"{system_prompt}\n\n---\n\n{user_prompt}",
                            cwd=str(self.project_path),
                            read_only=True,
                            timeout_seconds=180,
                            model=lead_model,
                            thinking_level=lead_thinking,
                            output_format="json",
                            json_schema=json.dumps(DECISION_JSON_SCHEMA),
                        )

                decision = parse_reasoner_decision(reason_res.output)
                # Parse retry instead of immediate abort
                if decision.get("action") == "ABORT" and "raw_text" in decision:
                    logger._write_log("WARN", "Reasoner response could not be parsed as valid JSON. Retrying with format correction prompt...")
                    retry_prompt = (
                        f"Your previous response could not be parsed as valid JSON matching the required schema.\n"
                        f"Please re-emit ONLY the raw JSON object without markdown formatting, code fences, or extraneous text.\n\n"
                        f"Required schema:\n"
                        f'{{\n  "analysis": "...",\n  "action": "DELEGATE | VERIFY | COMPLETE | ABORT | USE_SKILL",\n  "executor": "agy | cursor | python | claude",\n  "instruction": "...",\n  "success_criteria": [],\n  "verification_needed": false\n}}\n\n'
                        f"Your previous output was:\n{decision['raw_text'][:500]}"
                    )
                    retry_kwargs = {
                        "instruction": retry_prompt,
                        "cwd": str(self.project_path),
                        "read_only": True,
                        "timeout_seconds": 90,
                        "model": lead_model,
                        "thinking_level": lead_thinking,
                    }
                    if lead_reasoner == "claude":
                        retry_kwargs["output_format"] = "json"
                    elif lead_reasoner == "agy":
                        retry_kwargs["output_format"] = "json"
                        retry_kwargs["json_schema"] = json.dumps(DECISION_JSON_SCHEMA)
                    retry_res = reasoner_ex.execute(**retry_kwargs)
                    retry_decision = parse_reasoner_decision(retry_res.output)
                    if not ("raw_text" in retry_decision and retry_decision.get("action") == "ABORT"):
                        decision = retry_decision

                action = decision.get("action", "COMPLETE").upper()
                target_executor = decision.get("executor", "python").lower()
                instruction = decision.get("instruction", "")
                analysis = decision.get("analysis", "")

                logger.reasoning(lead_reasoner, analysis, action, target_executor)

                # Check action outcomes
                if action == "COMPLETE":
                    # Lazy agent guardrail: check if task required file changes but none were made
                    action_verbs = {"fix", "implement", "add", "refactor", "update", "create", "build", "optimize", "delete", "remove", "patch"}
                    goal_words = set(re.findall(r"\b\w+\b", task_state.goal.lower()))
                    if (
                        not self.read_only
                        and (goal_words & action_verbs)
                        and len(task_state.all_files_changed) == 0
                        and not decision.get("allow_zero_changes", False)
                    ):
                        logger._write_log("WARN", "Completion intercepted: Task objective appears to require code changes, but no files were modified.")
                        rec = IterationRecord(
                            iteration_number=iter_num,
                            reasoner_used=lead_reasoner,
                            lead_decision=decision,
                            executor_used="none",
                            instruction="Complete Guardrail Interception",
                            safety_passed=False,
                            safety_message=(
                                "Completion rejected: The goal indicates code modifications (verbs: "
                                f"{', '.join(sorted(goal_words & action_verbs))}), but no files have been modified yet. "
                                "Please delegate the necessary file changes to an executor, or if you verified that no code changes "
                                "are strictly necessary, set 'allow_zero_changes': true with your rationale in 'analysis'."
                            ),
                        )
                        self.state_mgr.record_iteration(task_state, rec)
                        if not self._update_cost_and_budget(task_state, rec, logger):
                            break
                        continue

                    # Check verification before stop
                    tests_passed: Optional[bool] = None
                    test_output: Optional[str] = None
                    test_res: Optional[ExecutorResult] = None

                    last_iter = task_state.iterations[-1] if task_state.iterations else None
                    just_verified = (
                        last_iter is not None
                        and (
                            last_iter.tests_passed is True
                            or (
                                last_iter.execution_result is not None
                                and last_iter.execution_result.success
                                and (
                                    last_iter.instruction == test_cmd
                                    or (last_iter.lead_decision and last_iter.lead_decision.get("action") == "VERIFY")
                                )
                            )
                        )
                        and not last_iter.files_changed
                    )

                    if self.safety_config.require_tests_before_stop and test_cmd and not self.read_only:
                        if just_verified:
                            logger._write_log("INFO", "Verification test suite already passed in preceding iteration; skipping redundant re-test.")
                            tests_passed = True
                            test_output = last_iter.test_output or "Previously verified"
                            if last_iter.execution_result:
                                test_res = last_iter.execution_result
                        elif self.dry_run:
                            logger._write_log("INFO", f"[DRY-RUN] Would run quality verification test suite: {test_cmd}")
                            tests_passed = True
                            test_output = "[DRY-RUN] Verification test execution skipped"
                        else:
                            logger._write_log("INFO", f"Running quality verification test suite: {test_cmd}")
                            py_ex = self.router.get_executor("python")
                            test_res = py_ex.execute(test_cmd, cwd=str(self.project_path))
                            tests_passed = test_res.success
                            test_output = "\n".join(filter(None, [test_res.output, test_res.error]))
                            logger.test_result(tests_passed, test_output)

                        if not tests_passed:
                            consecutive_failures += 1
                            last_error_text = test_output or "Verification test suite failed"
                            rec_metrics = dict(test_res.metrics) if test_res and test_res.metrics else {}
                            if isinstance(decision.get("metrics"), dict):
                                for k, v in decision["metrics"].items():
                                    if isinstance(v, (int, float)):
                                        rec_metrics[k] = float(v)
                            # Feed back failure to next round
                            rec = IterationRecord(
                                iteration_number=iter_num,
                                reasoner_used=lead_reasoner,
                                lead_decision=decision,
                                executor_used="python",
                                instruction=test_cmd,
                                execution_result=test_res,
                                tests_passed=False,
                                test_output=test_output,
                                safety_passed=True,
                                metrics=rec_metrics,
                            )
                            self.state_mgr.record_iteration(task_state, rec)
                            if not self._update_cost_and_budget(task_state, rec, logger):
                                break
                            if consecutive_failures >= 3:
                                msg = f"Task aborted: Verification tests failed 3 consecutive times. Last error: {last_error_text[:200]}"
                                self.state_mgr.complete_task(task_state, TaskStatus.FAILED, error=msg)
                                logger.error(msg)
                                break
                            elif consecutive_failures == 2:
                                escalation_header = (
                                    f"🚨 CRITICAL ESCALATION: Verification tests have failed 2 consecutive times. Last error:\n{last_error_text[:300]}\n\n"
                                    f"MANDATORY ROOT CAUSE ANALYSIS:\n"
                                    f"1. Do NOT declare COMPLETE until tests pass.\n"
                                    f"2. Diagnose the root cause of test failures."
                                )
                            continue

                    # Everything verified, task complete!
                    learnings = decision.get("learnings") or decision.get("decision_record")
                    if learnings:
                        decisions_file = self.root_dir / "projects" / self.project_name / "decisions.md"
                        import datetime
                        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
                        entry = f"\n\n### Learning [{now_str}] — Goal: {task_state.goal}\n{learnings}\n"
                        try:
                            decisions_file.parent.mkdir(parents=True, exist_ok=True)
                            with open(decisions_file, "a", encoding="utf-8") as f:
                                f.write(entry)
                            logger._write_log("INFO", f"Saved institutional learning to {decisions_file.name}")
                        except Exception as e:
                            logger._write_log("WARN", f"Could not save learning to decisions.md: {e}")

                    rec_metrics = {}
                    if isinstance(decision.get("metrics"), dict):
                        for k, v in decision["metrics"].items():
                            if isinstance(v, (int, float)):
                                rec_metrics[k] = float(v)

                    rec = IterationRecord(
                        iteration_number=iter_num,
                        reasoner_used=lead_reasoner,
                        lead_decision=decision,
                        executor_used="none",
                        instruction="Complete",
                        tests_passed=tests_passed,
                        safety_passed=True,
                        metrics=rec_metrics,
                    )
                    self.state_mgr.record_iteration(task_state, rec)
                    self._update_cost_and_budget(task_state, rec, logger)
                    self.state_mgr.complete_task(task_state, TaskStatus.COMPLETED, summary=analysis)
                    logger.complete(analysis)
                    break

                elif action == "ABORT":
                    rec = IterationRecord(
                        iteration_number=iter_num,
                        reasoner_used=lead_reasoner,
                        lead_decision=decision,
                        executor_used="none",
                        instruction="Abort",
                        safety_passed=True,
                    )
                    self.state_mgr.record_iteration(task_state, rec)
                    self._update_cost_and_budget(task_state, rec, logger)
                    self.state_mgr.complete_task(task_state, TaskStatus.ABORTED, summary=analysis, error=analysis)
                    logger.error(analysis)
                    break

                elif action == "USE_SKILL":
                    from orchestrator.context import load_skill_content
                    skill_name = decision.get("skill") or instruction
                    skill_body = load_skill_content(skill_name, self.root_dir, self.project_name)
                    if skill_body:
                        logger._write_log("INFO", f"Loaded active skill documentation: {skill_name}")
                        result_msg = f"Skill '{skill_name}' documentation:\n\n{skill_body}"
                        rec = IterationRecord(
                            iteration_number=iter_num,
                            reasoner_used=lead_reasoner,
                            lead_decision=decision,
                            executor_used="orchestrator",
                            instruction=f"Use skill: {skill_name}",
                            execution_result=ExecutorResult(
                                executor_name="orchestrator",
                                success=True,
                                output=result_msg,
                                exit_code=0,
                            ),
                            safety_passed=True,
                        )
                    else:
                        logger._write_log("WARN", f"Skill '{skill_name}' not found.")
                        rec = IterationRecord(
                            iteration_number=iter_num,
                            reasoner_used=lead_reasoner,
                            lead_decision=decision,
                            executor_used="orchestrator",
                            instruction=f"Use skill: {skill_name}",
                            execution_result=ExecutorResult(
                                executor_name="orchestrator",
                                success=False,
                                output="",
                                error=f"Skill '{skill_name}' was not found in project or global skills directories.",
                                exit_code=1,
                            ),
                            safety_passed=True,
                        )
                    self.state_mgr.record_iteration(task_state, rec)
                    if not self._update_cost_and_budget(task_state, rec, logger):
                        break
                    continue

                elif action == "ASK_HUMAN":
                    question = decision.get("question") or instruction or analysis
                    logger._write_log("INFO", f"Lead reasoner requested human clarification: {question}")
                    user_answer = None
                    import sys
                    if sys.stdin.isatty():
                        try:
                            click.secho(f"\n❓ [POLYPHONY HUMAN INPUT REQUIRED]", fg="yellow", bold=True)
                            click.secho(f"   Question: {question}\n", fg="cyan")
                            user_answer = input("Your answer (or leave blank to pause): ").strip()
                        except (EOFError, KeyboardInterrupt):
                            user_answer = None

                    if user_answer:
                        rec = IterationRecord(
                            iteration_number=iter_num,
                            reasoner_used=lead_reasoner,
                            lead_decision=decision,
                            executor_used="human",
                            instruction=question,
                            execution_result=ExecutorResult(
                                executor_name="human",
                                success=True,
                                output=f"Human Answer: {user_answer}",
                                exit_code=0,
                            ),
                            safety_passed=True,
                        )
                        self.state_mgr.record_iteration(task_state, rec)
                        if not self._update_cost_and_budget(task_state, rec, logger):
                            break
                        continue
                    else:
                        msg = f"Task paused awaiting human decision: {question}"
                        self.state_mgr.complete_task(task_state, TaskStatus.NEEDS_HUMAN, summary=msg, error=msg)
                        logger.error(msg)
                        break

                # Action is DELEGATE or VERIFY
                # Pre-delegation guardrail: validate specificity of coding agent delegation
                if action == "DELEGATE":
                    is_underspec, underspec_reason = _is_underspecified_delegation(decision, instruction, target_executor)
                    if is_underspec:
                        logger._write_log("WARN", underspec_reason)
                        rec = IterationRecord(
                            iteration_number=iter_num,
                            reasoner_used=lead_reasoner,
                            lead_decision=decision,
                            executor_used=target_executor,
                            instruction=instruction,
                            safety_passed=False,
                            safety_message=underspec_reason,
                        )
                        self.state_mgr.record_iteration(task_state, rec)
                        if not self._update_cost_and_budget(task_state, rec, logger):
                            break
                        continue

                # 2. Safety policy check on instruction / command
                is_shell_cmd = (target_executor == "python")
                safe, safe_reason = self.safety_engine.validate_command(instruction, is_shell=is_shell_cmd)
                logger.safety_check(safe, safe_reason)

                if not safe:
                    rec = IterationRecord(
                        iteration_number=iter_num,
                        reasoner_used=lead_reasoner,
                        lead_decision=decision,
                        executor_used=target_executor,
                        instruction=instruction,
                        safety_passed=False,
                        safety_message=safe_reason,
                    )
                    self.state_mgr.record_iteration(task_state, rec)
                    if not self._update_cost_and_budget(task_state, rec, logger):
                        break
                    continue

                # 3. Execute instruction via router
                logger.execution(target_executor, instruction)
                step_model = decision.get("model")
                step_thinking = decision.get("thinking_level")
                subagents_arg = (
                    self.models_config.subagents
                    if (action == "DELEGATE" and hasattr(self.models_config, "subagents"))
                    else None
                )

                # Inject lightweight context header on first turn of an executor session
                exec_instruction = instruction
                if action == "DELEGATE" and target_executor in ("claude", "agy", "cursor"):
                    sess_key = f"{target_executor}:{executor_sessions.get(target_executor, 'default')}"
                    if sess_key not in initialized_sessions:
                        ctx_hdr = build_delegation_context_header(self.knowledge)
                        exec_instruction = ctx_hdr + instruction
                        initialized_sessions.add(sess_key)

                if self.dry_run:
                    logger._write_log("INFO", f"[DRY-RUN] Would execute instruction via '{target_executor}': {exec_instruction[:120]}...")
                    exec_res = ExecutorResult(
                        executor_name=target_executor,
                        success=True,
                        output=f"[DRY-RUN] Simulated execution on {target_executor}",
                        exit_code=0,
                    )
                    used_executor = target_executor
                else:
                    step_agent = decision.get("agent") or decision.get("subagent")
                    exec_res, used_executor = self.router.execute(
                        target_executor=target_executor,
                        instruction=exec_instruction,
                        cwd=str(self.project_path),
                        read_only=self.read_only,
                        timeout_seconds=300,
                        models_config=self.models_config,
                        model=step_model,
                        thinking_level=step_thinking,
                        subagents=subagents_arg,
                        session_id=executor_sessions.get(target_executor),
                        agent=step_agent,
                    )

                if exec_res.metadata.get("session_id"):
                    new_sess = exec_res.metadata["session_id"]
                    executor_sessions[used_executor] = new_sess
                    task_state.executor_sessions = executor_sessions
                    initialized_sessions.add(f"{used_executor}:{new_sess}")

                logger.execution_result(
                    used_executor,
                    exec_res.success,
                    exec_res.output or (exec_res.error or ""),
                    exec_res.files_changed,
                )

                # Post-execution safety check: validate all modified files
                post_exec_safe = True
                post_exec_reason = None
                if exec_res.files_changed:
                    for changed_file in exec_res.files_changed:
                        p_ok, p_msg = self.safety_engine.validate_path_modification(changed_file)
                        if not p_ok:
                            post_exec_safe = False
                            post_exec_reason = p_msg
                            logger.safety_check(False, p_msg)
                            break

                if not post_exec_safe:
                    # Selectively revert modified files violating safety policies
                    import subprocess
                    for cf in (exec_res.files_changed or []):
                        fpath = self.project_path / cf
                        subprocess.run(["git", "checkout", "HEAD", "--", cf], cwd=str(self.project_path), capture_output=True)
                        res_stat = subprocess.run(["git", "status", "--porcelain", cf], cwd=str(self.project_path), capture_output=True, text=True)
                        if res_stat.stdout.strip().startswith("??") and fpath.exists():
                            try:
                                if fpath.is_file() or fpath.is_symlink():
                                    fpath.unlink()
                                elif fpath.is_dir():
                                    import shutil
                                    shutil.rmtree(fpath)
                            except OSError:
                                pass
                    rec = IterationRecord(
                        iteration_number=iter_num,
                        reasoner_used=lead_reasoner,
                        lead_decision=decision,
                        executor_used=used_executor,
                        instruction=instruction,
                        execution_result=exec_res,
                        tests_passed=False,
                        safety_passed=False,
                        safety_message=post_exec_reason,
                        files_changed=exec_res.files_changed,
                    )
                    self.state_mgr.record_iteration(task_state, rec)
                    if not self._update_cost_and_budget(task_state, rec, logger):
                        break
                    continue

                # 4. Optional verification check
                tests_passed = None
                if decision.get("verification_needed") and test_cmd and not self.read_only:
                    py_ex = self.router.get_executor("python")
                    test_res = py_ex.execute(test_cmd, cwd=str(self.project_path))
                    tests_passed = test_res.success
                    logger.test_result(tests_passed, test_res.output or test_res.error)

                rec_metrics = dict(exec_res.metrics) if (exec_res and exec_res.metrics) else {}
                if isinstance(decision.get("metrics"), dict):
                    for k, v in decision["metrics"].items():
                        if isinstance(v, (int, float)):
                            rec_metrics[k] = float(v)

                rec = IterationRecord(
                    iteration_number=iter_num,
                    reasoner_used=lead_reasoner,
                    lead_decision=decision,
                    executor_used=used_executor,
                    instruction=instruction,
                    execution_result=exec_res,
                    tests_passed=tests_passed,
                    safety_passed=True,
                    files_changed=exec_res.files_changed,
                    metrics=rec_metrics,
                )
                self.state_mgr.record_iteration(task_state, rec)
                if not self._update_cost_and_budget(task_state, rec, logger):
                    break

                # Track consecutive execution failures for infinite error loop breaker
                if not exec_res.success:
                    consecutive_failures += 1
                    last_error_text = exec_res.error or exec_res.output or "Execution failure"
                    if consecutive_failures >= 3:
                        msg = f"Task aborted: Executor hit an unresolvable 3-iteration error loop. Last error: {last_error_text[:200]}"
                        self.state_mgr.complete_task(task_state, TaskStatus.FAILED, error=msg)
                        logger.error(msg)
                        break
                    elif consecutive_failures == 2:
                        from orchestrator.context import classify_failure
                        fail_category = classify_failure(last_error_text, exec_res.exit_code)
                        escalation_header = (
                            f"🚨 CRITICAL ESCALATION: The executor has failed 2 consecutive times. "
                            f"Diagnostic Category: [{fail_category}]\n"
                            f"Last error:\n{last_error_text[:300]}\n\n"
                            f"MANDATORY ROOT CAUSE ANALYSIS:\n"
                            f"1. Do NOT repeat the previous instruction or make minor tweaks.\n"
                            f"2. Diagnose the root cause (Category: {fail_category}) and switch strategy or executor."
                        )
                else:
                    consecutive_failures = 0
                    last_error_text = ""

                # If reached max iterations, attempt final synthesis / extension
                if task_state.current_iteration >= self.max_iterations and task_state.status in (TaskStatus.PENDING, TaskStatus.RUNNING):
                    if task_state.iterations and any(it.execution_result and it.execution_result.success for it in task_state.iterations):
                        logger._write_log("INFO", "Running final evaluation and synthesis pass...")
                        iter_num = task_state.current_iteration + 1
                        prompt = build_reasoning_prompt(task_state, self.knowledge, available_executors, models_config=self.models_config)
                        prompt += (
                            "\nIMPORTANT: All planned execution iterations are complete. Please synthesize the findings from the execution "
                            "history above. If the task is finished, set 'action': 'COMPLETE' with your full summary in 'analysis'. "
                            "If more work is strictly necessary, set 'action': 'EXTEND' with 'extension_iterations' (integer, e.g. 3) and explain why in 'analysis'.\n"
                        )
                        synthesis_kwargs = {
                            "instruction": prompt,
                            "cwd": str(self.project_path),
                            "read_only": True,
                            "timeout_seconds": 180,
                        }
                        if lead_reasoner == "claude":
                            synthesis_kwargs["output_format"] = "json"
                        elif lead_reasoner == "agy":
                            synthesis_kwargs["output_format"] = "json"
                            synthesis_kwargs["json_schema"] = json.dumps(DECISION_JSON_SCHEMA)
                        synthesis_res = reasoner_ex.execute(**synthesis_kwargs)
                        synthesis_decision = parse_reasoner_decision(synthesis_res.output)
                        synthesis_action = synthesis_decision.get("action", "COMPLETE").upper()
                        synthesis_analysis = synthesis_decision.get("analysis", synthesis_res.output)

                        synthesis_rec = IterationRecord(
                            iteration_number=iter_num,
                            reasoner_used=lead_reasoner,
                            lead_decision=synthesis_decision,
                            executor_used="none",
                            instruction="Final Synthesis / Extension",
                            execution_result=synthesis_res,
                            safety_passed=True,
                        )
                        self.state_mgr.record_iteration(task_state, synthesis_rec)
                        if not self._update_cost_and_budget(task_state, synthesis_rec, logger):
                            break

                        if synthesis_action == "EXTEND":
                            ext = int(synthesis_decision.get("extension_iterations", 3))
                            self.max_iterations = task_state.current_iteration + ext
                            task_state.max_iterations = self.max_iterations
                            logger._write_log("INFO", f"Lead reasoner requested extension of {ext} iterations. New max: {self.max_iterations}")
                            continue
                        elif synthesis_action == "COMPLETE":
                            self.state_mgr.complete_task(task_state, TaskStatus.COMPLETED, summary=synthesis_analysis)
                            logger.complete(synthesis_analysis)
                            break
                        else:
                            self.state_mgr.complete_task(task_state, TaskStatus.FAILED, summary=synthesis_analysis, error=synthesis_analysis)
                            logger.error(synthesis_analysis)
                            break
                    else:
                        msg = f"Task reached maximum iterations ({self.max_iterations}) without completion."
                        self.state_mgr.complete_task(task_state, TaskStatus.FAILED, error=msg)
                        logger.error(msg)
                        break

            # If loop terminated without completing or failing
            if task_state.status in (TaskStatus.PENDING, TaskStatus.RUNNING):
                msg = f"Task reached maximum iterations ({self.max_iterations}) without completion."
                self.state_mgr.complete_task(task_state, TaskStatus.FAILED, error=msg)
                logger.error(msg)
        finally:
            if original_sigint and callable(original_sigint):
                try:
                    signal.signal(signal.SIGINT, original_sigint)
                except (ValueError, AttributeError):
                    pass

        # Generate report
        report_path = task_dir / "report.md"
        generate_task_report(task_state, report_path)
        logger._write_log("INFO", f"Report written to {report_path}")

        return task_state
