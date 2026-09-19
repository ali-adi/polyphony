"""Core decision loop and orchestrator engine for Polyphony."""

from __future__ import annotations

import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
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
    ):
        self.root_dir = Path(root_dir).resolve()
        self.project_name = project_name
        self.read_only = read_only
        self.max_iterations = max_iterations
        self.preferred_lead = preferred_lead
        self.cli_overrides = cli_overrides or {}
        self.history_window = history_window
        self.dry_run = dry_run

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

    def resume_task(self, task_id: str) -> TaskState:
        """Resume an existing task from its saved state."""
        task_state = self.state_mgr.load_state(self.project_name, task_id)
        if not task_state:
            raise FileNotFoundError(f"Task '{task_id}' not found for project '{self.project_name}'.")
        task_state.status = TaskStatus.RUNNING
        self.state_mgr.save_state(task_state)
        return self._execute_task_loop(task_state)

    def _execute_task_loop(self, task_state: TaskState) -> TaskState:
        task_dir = self.state_mgr._get_task_dir(self.project_name, task_state.task_id)
        log_cfg = self.global_cfg.get("logging", {})
        log_dir_name = log_cfg.get("log_dir", "logs")
        log_file = task_dir / log_dir_name / "execution.log"
        logger = TaskLogger(task_state.task_id, log_file=log_file, logging_config=log_cfg)

        logger.header(f"Starting Task {task_state.task_id} for '{self.project_name}'")
        logger._write_log("INFO", f"Goal: {task_state.goal} | Read-Only: {self.read_only} | Dry-Run: {self.dry_run}")

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

        lead_session_id: Optional[str] = None
        executor_sessions: Dict[str, str] = {}

        available_executors = [name for name, ok in self.router.get_available_executors().items() if ok]
        test_cmd = self.project_cfg.get("testing", {}).get("command")

        while task_state.current_iteration < self.max_iterations:
            iter_num = task_state.current_iteration + 1
            logger.iteration(iter_num, self.max_iterations)

            # 1. Build prompt and invoke lead reasoner
            system_prompt = build_system_prompt(
                knowledge=self.knowledge,
                available_executors=available_executors,
                models_config=self.models_config,
                project_path=str(self.project_path),
            )
            user_prompt = build_user_prompt(
                task_state=task_state,
                history_window=self.history_window,
            )

            reasoner_ex = self.router.get_executor(lead_reasoner)
            if not reasoner_ex:
                reasoner_ex = self.router.get_executor("agy") or self.router.get_executor("python")

            lead_profile = self.models_config.lead.get(lead_reasoner)
            lead_model = lead_profile.model if lead_profile else None
            lead_thinking = lead_profile.thinking_level if lead_profile else None

            # Split prompt: pass system_prompt to Claude or combine for others
            if lead_reasoner == "claude":
                instruction_arg = user_prompt
                sys_prompt_arg = system_prompt
            else:
                instruction_arg = f"{system_prompt}\n\n---\n\n{user_prompt}"
                sys_prompt_arg = None

            reason_res = reasoner_ex.execute(
                instruction=instruction_arg,
                cwd=str(self.project_path),
                read_only=True,
                timeout_seconds=180,
                model=lead_model,
                thinking_level=lead_thinking,
                system_prompt=sys_prompt_arg,
                session_id=lead_session_id,
            )

            # Track lead session ID if returned
            if reason_res.metadata.get("session_id"):
                lead_session_id = reason_res.metadata["session_id"]

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
                    )

            decision = parse_reasoner_decision(reason_res.output)
            # Parse retry instead of immediate abort
            if decision.get("action") == "ABORT" and "raw_text" in decision:
                logger._write_log("WARN", "Reasoner response could not be parsed as valid JSON. Retrying with format correction prompt...")
                retry_prompt = (
                    f"Your previous response could not be parsed as valid JSON matching the required schema.\n"
                    f"Please re-emit ONLY the raw JSON object without markdown formatting, code fences, or extraneous text.\n\n"
                    f"Required schema:\n"
                    f'{{\n  "analysis": "...",\n  "action": "DELEGATE | VERIFY | COMPLETE | ABORT",\n  "executor": "agy | cursor | python | claude",\n  "instruction": "...",\n  "success_criteria": [],\n  "verification_needed": false\n}}\n\n'
                    f"Your previous output was:\n{decision['raw_text'][:500]}"
                )
                retry_res = reasoner_ex.execute(
                    instruction=retry_prompt,
                    cwd=str(self.project_path),
                    read_only=True,
                    timeout_seconds=90,
                    model=lead_model,
                    thinking_level=lead_thinking,
                )
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
                # Check verification before stop
                tests_passed: Optional[bool] = None
                test_output: Optional[str] = None

                if self.safety_config.require_tests_before_stop and test_cmd and not self.read_only:
                    if self.dry_run:
                        logger._write_log("INFO", f"[DRY-RUN] Would run quality verification test suite: {test_cmd}")
                        tests_passed = True
                        test_output = "[DRY-RUN] Verification test execution skipped"
                    else:
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
            step_model = decision.get("model")
            step_thinking = decision.get("thinking_level")
            subagents_arg = (
                self.models_config.subagents
                if (action == "DELEGATE" and hasattr(self.models_config, "subagents"))
                else None
            )

            # Inject lightweight context header when delegating to coding agent engines
            exec_instruction = instruction
            if action == "DELEGATE" and target_executor in ("claude", "agy", "cursor"):
                ctx_hdr = build_delegation_context_header(self.knowledge)
                exec_instruction = ctx_hdr + instruction

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
                )

            if exec_res.metadata.get("session_id"):
                executor_sessions[used_executor] = exec_res.metadata["session_id"]

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
                # Rollback changes violating safety
                from executors.router import rollback_workspace
                rollback_workspace(str(self.project_path))
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
                continue

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
                prompt = build_reasoning_prompt(task_state, self.knowledge, available_executors, models_config=self.models_config)
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
