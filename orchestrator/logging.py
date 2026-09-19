"""Structured logging subsystem for Polyphony."""

from __future__ import annotations

import logging
import sys
from pathlib import Path
import datetime
import json
from typing import Any, Dict, Optional
import click


class JsonLogFormatter(logging.Formatter):
    """Formats log records as JSON lines."""

    def format(self, record: logging.LogRecord) -> str:
        data = {
            "timestamp": datetime.datetime.fromtimestamp(record.created).isoformat(),
            "level": record.levelname,
            "message": record.getMessage(),
            "logger": record.name,
        }
        return json.dumps(data)


class TaskLogger:
    """Provides human-friendly console output and persistent file logging for tasks."""

    def __init__(
        self,
        task_id: str,
        log_file: Optional[Path] = None,
        logging_config: Optional[Dict[str, Any]] = None,
    ):
        self.task_id = task_id
        self.log_file = log_file
        cfg = logging_config or {}

        level_str = cfg.get("level", "INFO").upper()
        log_level = getattr(logging, level_str, logging.INFO)
        use_json = cfg.get("structured_json", False)

        if self.log_file:
            self.log_file.parent.mkdir(parents=True, exist_ok=True)
            self._file_handler = logging.FileHandler(str(self.log_file), encoding="utf-8")
            if use_json:
                self._file_handler.setFormatter(JsonLogFormatter())
            else:
                self._file_handler.setFormatter(
                    logging.Formatter("[%(asctime)s] [%(levelname)s] %(message)s")
                )
            self._logger = logging.getLogger(f"polyphony.{task_id}")
            self._logger.setLevel(log_level)
            self._logger.handlers.clear()
            self._logger.addHandler(self._file_handler)
        else:
            self._logger = None

    def _write_log(self, level: str, message: str):
        if self._logger:
            if level == "INFO":
                self._logger.info(message)
            elif level == "WARNING":
                self._logger.warning(message)
            elif level == "ERROR":
                self._logger.error(message)

    def header(self, title: str):
        click.secho(f"\n{'=' * 60}", fg="cyan")
        click.secho(f"🚀 {title}", fg="cyan", bold=True)
        click.secho(f"{'=' * 60}", fg="cyan")
        self._write_log("INFO", f"=== {title} ===")

    def iteration(self, iter_num: int, max_iters: int):
        click.secho(f"\n🔄 Iteration {iter_num}/{max_iters}", fg="magenta", bold=True)
        self._write_log("INFO", f"--- Iteration {iter_num}/{max_iters} ---")

    def reasoning(self, reasoner: str, analysis: str, action: str, target_executor: str):
        click.secho(f"🧠 [{reasoner.upper()} DECISION]", fg="blue", bold=True)
        click.echo(f"   Analysis: {analysis[:300]}..." if len(analysis) > 300 else f"   Analysis: {analysis}")
        click.secho(f"   Action: {action} ➔ Executor: {target_executor}", fg="yellow", bold=True)
        self._write_log("INFO", f"[{reasoner}] Action={action}, Executor={target_executor}, Analysis={analysis}")

    def execution(self, executor: str, instruction: str):
        click.secho(f"⚙️  [{executor.upper()} RUNNING]", fg="blue")
        click.echo(f"   Instruction: {instruction[:200]}..." if len(instruction) > 200 else f"   Instruction: {instruction}")
        self._write_log("INFO", f"[{executor}] Executing: {instruction}")

    def execution_result(self, executor: str, success: bool, output: str, files_changed: list):
        color = "green" if success else "red"
        status_text = "SUCCESS" if success else "FAILED"
        click.secho(f"   Result: [{status_text}]", fg=color, bold=True)
        if output:
            lines = output.strip().splitlines()
            preview = "\n   ".join(lines[:6])
            if len(lines) > 6:
                preview += f"\n   ... ({len(lines) - 6} more lines)"
            click.echo(f"   Output:\n   {preview}")
        if files_changed:
            click.secho(f"   Files Modified ({len(files_changed)}): {', '.join(files_changed)}", fg="yellow")
        self._write_log("INFO", f"[{executor}] Result={status_text}, Files={files_changed}, Output={output[:500]}")

    def safety_check(self, passed: bool, message: Optional[str] = None):
        if passed:
            click.secho("🛡️  Safety check: PASSED", fg="green")
            self._write_log("INFO", "Safety check: PASSED")
        else:
            click.secho(f"🛡️  Safety check: BLOCKED — {message}", fg="red", bold=True)
            self._write_log("WARNING", f"Safety check: BLOCKED — {message}")

    def test_result(self, passed: bool, output: Optional[str] = None):
        if passed:
            click.secho("✅ Verification tests: PASSED", fg="green", bold=True)
            self._write_log("INFO", "Verification tests: PASSED")
        else:
            click.secho("❌ Verification tests: FAILED", fg="red", bold=True)
            if output:
                tail = "\n   ".join(output.strip().splitlines()[-8:])
                click.echo(f"   {tail}")
            self._write_log("WARNING", f"Verification tests: FAILED\n{output}")

    def complete(self, summary: str):
        click.secho(f"\n🎉 Task completed successfully!", fg="green", bold=True)
        click.echo(f"\nSummary:\n{summary}\n")
        self._write_log("INFO", f"TASK COMPLETED: {summary}")

    def error(self, err_msg: str):
        click.secho(f"\n❌ Task halted with error: {err_msg}", fg="red", bold=True)
        self._write_log("ERROR", f"TASK HALTED: {err_msg}")
