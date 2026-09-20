"""Diagnostic engine and health verification for Polyphony (Section 11)."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

import click
import yaml

from executors.router import ExecutorRouter
from orchestrator.models_config import resolve_models_config
from orchestrator.safety import resolve_safety_config


class CheckStatus(str, Enum):
    OK = "OK"
    WARNING = "WARNING"
    ERROR = "ERROR"
    BLOCKED = "BLOCKED"


@dataclass
class DiagnosticCheck:
    name: str
    category: str
    status: CheckStatus
    message: str
    details: Optional[str] = None


@dataclass
class DoctorReport:
    checks: List[DiagnosticCheck] = field(default_factory=list)

    @property
    def has_errors(self) -> bool:
        return any(c.status in (CheckStatus.ERROR, CheckStatus.BLOCKED) for c in self.checks)

    @property
    def summary_counts(self) -> Dict[str, int]:
        counts = {"OK": 0, "WARNING": 0, "ERROR": 0, "BLOCKED": 0}
        for c in self.checks:
            counts[c.status.value] += 1
        return counts


class PolyphonyDoctor:
    """Performs comprehensive diagnostics on the Polyphony runtime and environment."""

    def __init__(self, root_dir: str | Path = "."):
        self.root_dir = Path(root_dir).resolve()

    def run_all_checks(self) -> DoctorReport:
        report = DoctorReport()

        report.checks.append(self._check_polyphony_installation())
        report.checks.append(self._check_python_environment())
        report.checks.append(self._check_git())
        report.checks.append(self._check_claude_cli())
        report.checks.append(self._check_agy_cli())
        report.checks.append(self._check_cursor_cli())
        report.checks.append(self._check_authentication())
        report.checks.append(self._check_model_configuration())
        report.checks.append(self._check_project_registration())
        report.checks.append(self._check_state_directory())
        report.checks.append(self._check_permissions())
        report.checks.append(self._check_disk_space())
        report.checks.append(self._check_hooks())
        report.checks.append(self._check_safety_configuration())
        report.checks.append(self._check_migration_state())
        report.checks.append(self._check_executor_health())

        return report

    def _check_polyphony_installation(self) -> DiagnosticCheck:
        try:
            import importlib.metadata
            version = importlib.metadata.version("polyphony")
            return DiagnosticCheck(
                name="Polyphony Installation",
                category="Installation",
                status=CheckStatus.OK,
                message=f"Polyphony v{version} installed",
            )
        except Exception:
            return DiagnosticCheck(
                name="Polyphony Installation",
                category="Installation",
                status=CheckStatus.OK,
                message="Polyphony loaded from source repository",
            )

    def _check_python_environment(self) -> DiagnosticCheck:
        v = sys.version_info
        ver_str = f"{v.major}.{v.minor}.{v.micro}"
        if v.major < 3 or (v.major == 3 and v.minor < 11):
            return DiagnosticCheck(
                name="Python Environment",
                category="Environment",
                status=CheckStatus.ERROR,
                message=f"Python {ver_str} is incompatible (requires Python >= 3.11)",
            )
        in_venv = hasattr(sys, "real_prefix") or (hasattr(sys, "base_prefix") and sys.base_prefix != sys.prefix)
        msg = f"Python {ver_str} (virtualenv: {'active' if in_venv else 'none'})"
        return DiagnosticCheck(
            name="Python Environment",
            category="Environment",
            status=CheckStatus.OK if in_venv else CheckStatus.WARNING,
            message=msg,
        )

    def _check_git(self) -> DiagnosticCheck:
        git_path = shutil.which("git")
        if not git_path:
            return DiagnosticCheck(
                name="Git",
                category="Tools",
                status=CheckStatus.BLOCKED,
                message="Git executable not found in PATH",
            )
        try:
            res = subprocess.run(["git", "--version"], capture_output=True, text=True, check=True)
            return DiagnosticCheck(
                name="Git",
                category="Tools",
                status=CheckStatus.OK,
                message=res.stdout.strip(),
            )
        except Exception as e:
            return DiagnosticCheck(
                name="Git",
                category="Tools",
                status=CheckStatus.ERROR,
                message=f"Git check failed: {e}",
            )

    def _check_claude_cli(self) -> DiagnosticCheck:
        router = ExecutorRouter()
        claude = router.get_executor("claude")
        if not claude or not claude.is_available():
            return DiagnosticCheck(
                name="Claude CLI",
                category="Executors",
                status=CheckStatus.WARNING,
                message="Claude CLI binary not found in PATH",
            )
        h = claude.health()
        return DiagnosticCheck(
            name="Claude CLI",
            category="Executors",
            status=CheckStatus.OK if h.get("status") == "OK" else CheckStatus.WARNING,
            message=h.get("details", "Claude CLI ready"),
        )

    def _check_agy_cli(self) -> DiagnosticCheck:
        router = ExecutorRouter()
        agy = router.get_executor("agy")
        if not agy or not agy.is_available():
            return DiagnosticCheck(
                name="AGY CLI",
                category="Executors",
                status=CheckStatus.WARNING,
                message="Antigravity CLI (agy) not found in PATH",
            )
        return DiagnosticCheck(
            name="AGY CLI",
            category="Executors",
            status=CheckStatus.OK,
            message="Antigravity CLI ready",
        )

    def _check_cursor_cli(self) -> DiagnosticCheck:
        router = ExecutorRouter()
        cursor = router.get_executor("cursor")
        if not cursor or not cursor.is_available():
            return DiagnosticCheck(
                name="Cursor CLI",
                category="Executors",
                status=CheckStatus.WARNING,
                message="Cursor CLI or agent subcommand not ready",
            )
        return DiagnosticCheck(
            name="Cursor CLI",
            category="Executors",
            status=CheckStatus.OK,
            message="Cursor agent ready",
        )

    def _check_authentication(self) -> DiagnosticCheck:
        has_anthropic = bool(os.environ.get("ANTHROPIC_API_KEY"))
        has_gemini = bool(os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"))
        details = []
        if has_anthropic:
            details.append("ANTHROPIC_API_KEY detected")
        if has_gemini:
            details.append("GEMINI_API_KEY detected")

        if not details:
            return DiagnosticCheck(
                name="Authentication",
                category="Security",
                status=CheckStatus.WARNING,
                message="No direct API keys found in environment (relying on CLI subscription logins)",
            )
        return DiagnosticCheck(
            name="Authentication",
            category="Security",
            status=CheckStatus.OK,
            message=", ".join(details),
        )

    def _check_model_configuration(self) -> DiagnosticCheck:
        global_path = self.root_dir / "config" / "global.yaml"
        if not global_path.exists():
            return DiagnosticCheck(
                name="Model Configuration",
                category="Configuration",
                status=CheckStatus.WARNING,
                message=f"Global config file not found at {global_path}",
            )
        try:
            with open(global_path, "r", encoding="utf-8") as f:
                cfg = yaml.safe_load(f) or {}
            models_cfg = resolve_models_config(global_cfg=cfg)
            return DiagnosticCheck(
                name="Model Configuration",
                category="Configuration",
                status=CheckStatus.OK,
                message=f"Resolved lead ({len(models_cfg.lead)} profiles), executors ({len(models_cfg.executors)} profiles)",
            )
        except Exception as e:
            return DiagnosticCheck(
                name="Model Configuration",
                category="Configuration",
                status=CheckStatus.ERROR,
                message=f"Failed to parse model configuration: {e}",
            )

    def _check_project_registration(self) -> DiagnosticCheck:
        proj_dir = self.root_dir / "projects"
        if not proj_dir.exists():
            return DiagnosticCheck(
                name="Project Registration",
                category="Projects",
                status=CheckStatus.WARNING,
                message="No 'projects' directory discovered",
            )
        projects = [p.name for p in proj_dir.iterdir() if p.is_dir() and (p / "project.yaml").exists()]
        return DiagnosticCheck(
            name="Project Registration",
            category="Projects",
            status=CheckStatus.OK if projects else CheckStatus.WARNING,
            message=f"{len(projects)} registered project(s): {', '.join(projects) if projects else 'none'}",
        )

    def _check_state_directory(self) -> DiagnosticCheck:
        tasks_dir = self.root_dir / "tasks"
        tasks_dir.mkdir(parents=True, exist_ok=True)
        return DiagnosticCheck(
            name="State Directory",
            category="Storage",
            status=CheckStatus.OK,
            message=f"State directory accessible at {tasks_dir}",
        )

    def _check_permissions(self) -> DiagnosticCheck:
        try:
            test_file = self.root_dir / ".polyphony_doctor_perm_test"
            test_file.write_text("test", encoding="utf-8")
            test_file.unlink()
            return DiagnosticCheck(
                name="Permissions",
                category="Storage",
                status=CheckStatus.OK,
                message="Workspace directory has read/write permissions",
            )
        except Exception as e:
            return DiagnosticCheck(
                name="Permissions",
                category="Storage",
                status=CheckStatus.BLOCKED,
                message=f"Permission check failed: {e}",
            )

    def _check_disk_space(self) -> DiagnosticCheck:
        try:
            total, used, free = shutil.disk_usage(self.root_dir)
            free_gb = free / (1024 ** 3)
            status = CheckStatus.OK if free_gb >= 2.0 else CheckStatus.WARNING
            return DiagnosticCheck(
                name="Disk Space",
                category="Storage",
                status=status,
                message=f"{free_gb:.1f} GB free disk space",
            )
        except Exception as e:
            return DiagnosticCheck(
                name="Disk Space",
                category="Storage",
                status=CheckStatus.WARNING,
                message=f"Could not determine disk space: {e}",
            )

    def _check_hooks(self) -> DiagnosticCheck:
        hooks_found = 0
        proj_dir = self.root_dir / "projects"
        if proj_dir.exists():
            for p in proj_dir.iterdir():
                hooks_dir = p / "hooks"
                if hooks_dir.exists():
                    hooks_found += len(list(hooks_dir.iterdir()))
        return DiagnosticCheck(
            name="Hooks",
            category="Customizations",
            status=CheckStatus.OK,
            message=f"{hooks_found} project hook(s) discovered",
        )

    def _check_safety_configuration(self) -> DiagnosticCheck:
        global_path = self.root_dir / "config" / "global.yaml"
        cfg = {}
        if global_path.exists():
            with open(global_path, "r", encoding="utf-8") as f:
                cfg = yaml.safe_load(f) or {}
        safety = resolve_safety_config(global_cfg=cfg)
        return DiagnosticCheck(
            name="Safety Configuration",
            category="Safety",
            status=CheckStatus.OK,
            message=f"{len(safety.blocked_commands)} blocked commands, {len(safety.protected_paths)} protected paths configured",
        )

    def _check_migration_state(self) -> DiagnosticCheck:
        mig_dir = self.root_dir / "migration"
        count = len(list(mig_dir.iterdir())) if mig_dir.exists() else 0
        return DiagnosticCheck(
            name="Migration State",
            category="Migration",
            status=CheckStatus.OK,
            message=f"{count} migration asset directories",
        )

    def _check_executor_health(self) -> DiagnosticCheck:
        router = ExecutorRouter()
        avail_map = router.get_available_executors()
        ready_count = sum(1 for v in avail_map.values() if v)
        total_count = len(avail_map)
        status = CheckStatus.OK if ready_count >= 1 else CheckStatus.ERROR
        details = ", ".join(f"{k}={'READY' if v else 'OFFLINE'}" for k, v in avail_map.items())
        return DiagnosticCheck(
            name="Executor Health",
            category="Executors",
            status=status,
            message=f"{ready_count}/{total_count} executors ready ({details})",
        )
