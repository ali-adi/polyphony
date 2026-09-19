"""Core decision loop and orchestrator engine for ai-orch."""

from __future__ import annotations

import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
import yaml

from executors.base import ExecutorResult
from executors.router import ExecutorRouter
from orchestrator.context import build_reasoning_prompt, load_project_knowledge, parse_reasoner_decision
from orchestrator.logging import TaskLogger
from orchestrator.report import generate_task_report
from orchestrator.safety import SafetyConfig, SafetyEngine
from orchestrator.state import IterationRecord, StateManager, TaskState, TaskStatus


class Orchestrator:
    """Coordinates lead reasoning agent, executor adapters, safety gates, and state persistence."""

    def __init__(
        self,
        project_name: str,
        root_dir: str | Path = ".",
        read_only: bool = False,
        max_iterations: int = 10,
        preferred_lead: Optional[str] = None,
    ):
        self.root_dir = Path(root_dir).resolve()
        self.project_name = project_name
        self.read_only = read_only
        self.max_iterations = max_iterations
        self.preferred_lead = preferred_lead

        # 1. Load project definition
        self.knowledge = load_project_knowledge(project_name, self.root_dir)
        self.project_cfg = self.knowledge.get("config", {})
        self.project_path = Path(self.project_cfg.get("path", self.root_dir / project_name)).resolve()

        if not self.project_path.exists():
            raise FileNotFoundError(f"Target project directory does not exist: {self.project_path}")

        # 2. State and Safety
        self.state_mgr = StateManager(self.root_dir)
        safety_dict = self.project_cfg.get("safety", {})
        self.safety_config = SafetyConfig(
            protected_paths=safety_dict.get("protected_paths", ["database/", "**/database/**"]),
            blocked_commands=safety_dict.get("blocked_commands", []),
            require_tests_before_stop=safety_dict.get("require_tests_before_stop", True),
            require_approval_for=safety_dict.get("require_approval_for", []),
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

    def _select_lead_reasoner(self) -> str:
        """Select primary reasoning engine, falling back to agy if Claude is rate-limited."""
        if self.preferred_lead:
            return self.preferred_lead

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

        task_dir = self.state_mgr._get_task_dir(self.project_name, task_state.task_id)
        log_file = task_dir / "logs" / "execution.log"
        logger = TaskLogger(task_state.task_id, log_file=log_file)

        logger.header(f"Starting Task {task_state.task_id} for '{self.project_name}'")
        logger._write_log("INFO", f"Goal: {goal} | Read-Only: {self.read_only}")

        # Choose lead reasoner
        lead_reasoner = self._select_lead_reasoner()
        logger._write_log("INFO", f"Active Lead Reasoner: {lead_reasoner}")

        available_executors = [name for name, ok in self.router.get_available_executors().items() if ok]
        test_cmd = self.project_cfg.get("testing", {}).get("command")

        while task_state.current_iteration < self.max_iterations:
            iter_num = task_state.current_iteration + 1
            logger.iteration(iter_num, self.max_iterations)

            # 1. Build prompt and invoke lead reasoner
            prompt = build_reasoning_prompt(task_state, self.knowledge, available_executors)

            reasoner_ex = self.router.get_executor(lead_reasoner)
            if not reasoner_ex:
                reasoner_ex = self.router.get_executor("agy") or self.router.get_executor("python")

            reason_res = reasoner_ex.execute(
                instruction=prompt,
                cwd=str(self.project_path),
                read_only=True,
                timeout_seconds=180,
            )

            decision = parse_reasoner_decision(reason_res.output)
            action = decision.get("action", "COMPLETE").upper()
            target_executor = decision.get("executor", "python").lower()
            instruction = decision.get("instruction", "")
            analysis = decision.get("analysis", "")

            logger.reasoning(lead_reasoner, analysis, action, target_executor)

            # Check action outcomes
            if action == "COMPLETE":
                # Check verification before stop
                tests_passed: Optional[bool] = None
                test_output: Optional[str] = None

                if self.safety_config.require_tests_before_stop and test_cmd and not self.read_only:
                    logger._write_log("INFO", f"Running quality verification test suite: {test_cmd}")
                    py_ex = self.router.get_executor("python")
                    test_res = py_ex.execute(test_cmd, cwd=str(self.project_path))
                    tests_passed = test_res.success
                    test_output = test_res.output or test_res.error
                    logger.test_result(tests_passed, test_output)

                    if not tests_passed:
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
                        )
                        self.state_mgr.record_iteration(task_state, rec)
                        continue

                # Everything verified, task complete!
                rec = IterationRecord(
                    iteration_number=iter_num,
                    reasoner_used=lead_reasoner,
                    lead_decision=decision,
                    executor_used="none",
                    instruction="Complete",
                    tests_passed=tests_passed,
                    safety_passed=True,
                )
                self.state_mgr.record_iteration(task_state, rec)
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
                self.state_mgr.complete_task(task_state, TaskStatus.ABORTED, summary=analysis, error=analysis)
                logger.error(analysis)
                break

            # Action is DELEGATE or VERIFY
            # 2. Safety policy check on instruction / command
            safe, safe_reason = self.safety_engine.validate_command(instruction)
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
                continue

            # 3. Execute instruction via router
            logger.execution(target_executor, instruction)
            exec_res, used_executor = self.router.execute(
                target_executor=target_executor,
                instruction=instruction,
                cwd=str(self.project_path),
                read_only=self.read_only,
                timeout_seconds=300,
            )

            logger.execution_result(
                used_executor,
                exec_res.success,
                exec_res.output or (exec_res.error or ""),
                exec_res.files_changed,
            )

            # 4. Optional verification check
            tests_passed = None
            if decision.get("verification_needed") and test_cmd and not self.read_only:
                py_ex = self.router.get_executor("python")
                test_res = py_ex.execute(test_cmd, cwd=str(self.project_path))
                tests_passed = test_res.success
                logger.test_result(tests_passed, test_res.output or test_res.error)

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
            )
            self.state_mgr.record_iteration(task_state, rec)

        # Loop ended: check if still running
        if task_state.status == TaskStatus.PENDING or task_state.status == TaskStatus.RUNNING:
            # If we had successful execution turns, allow the lead reasoner to perform a final synthesis pass
            if task_state.iterations and any(it.execution_result and it.execution_result.success for it in task_state.iterations):
                logger._write_log("INFO", "Running final evaluation and synthesis pass...")
                prompt = build_reasoning_prompt(task_state, self.knowledge, available_executors)
                prompt += (
                    "\nIMPORTANT: All execution iterations are complete. Please synthesize the findings from the execution "
                    "history above and provide your final conclusion. Set 'action': 'COMPLETE' with your full summary in 'analysis'.\n"
                )
                reason_res = reasoner_ex.execute(
                    instruction=prompt,
                    cwd=str(self.project_path),
                    read_only=True,
                    timeout_seconds=180,
                )
                decision = parse_reasoner_decision(reason_res.output)
                action = decision.get("action", "COMPLETE").upper()
                analysis = decision.get("analysis", reason_res.output)

                if action == "COMPLETE":
                    self.state_mgr.complete_task(task_state, TaskStatus.COMPLETED, summary=analysis)
                    logger.complete(analysis)
                else:
                    self.state_mgr.complete_task(task_state, TaskStatus.FAILED, summary=analysis, error=analysis)
                    logger.error(analysis)
            else:
                msg = f"Task reached maximum iterations ({self.max_iterations}) without completion."
                self.state_mgr.complete_task(task_state, TaskStatus.FAILED, error=msg)
                logger.error(msg)

        # Generate report
        report_path = task_dir / "report.md"
        generate_task_report(task_state, report_path)
        logger._write_log("INFO", f"Report written to {report_path}")

        return task_state
