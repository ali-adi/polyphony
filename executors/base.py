"""Base abstract class, formal executor protocol, and normalized result models."""

from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum
from pathlib import Path
import subprocess
from typing import Any, Dict, List, Optional, Tuple
from pydantic import BaseModel, Field


def _get_changed_files_via_git(cwd: str) -> List[str]:
    """Inspect git status to see modified or untracked files."""
    try:
        res = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if res.returncode == 0:
            lines = res.stdout.strip().splitlines()
            files = []
            for line in lines:
                if not line.strip():
                    continue
                parts = line.strip().split(maxsplit=1)
                if len(parts) == 2:
                    path_str = parts[1]
                    if " -> " in path_str:
                        # For renames, take the target (new) path
                        target_file = path_str.split(" -> ", 1)[1].strip().strip('"')
                        files.append(target_file)
                    else:
                        files.append(path_str.strip('"'))
            return files
    except Exception:
        pass
    return []


def _snapshot_file_states(cwd: str, get_changed_files_fn=None) -> Dict[str, Tuple[float, int]]:
    """Capture mtime and size of files in workspace via git status, falling back to directory walk if not a git repo."""
    fn = get_changed_files_fn or _get_changed_files_via_git
    snapshots: Dict[str, Tuple[float, int]] = {}
    changed_files = fn(cwd)
    if not changed_files and not (Path(cwd) / ".git").exists():
        for p in Path(cwd).rglob("*"):
            if p.is_file() and not any(part.startswith(".") for part in p.parts):
                try:
                    rel_path = str(p.relative_to(cwd))
                    st = p.stat()
                    snapshots[rel_path] = (st.st_mtime, st.st_size)
                except OSError:
                    pass
        return snapshots

    for rel_path in changed_files:
        full_p = Path(cwd) / rel_path
        if full_p.exists():
            try:
                st = full_p.stat()
                snapshots[rel_path] = (st.st_mtime, st.st_size)
            except OSError:
                pass
        else:
            snapshots[rel_path] = (-1.0, -1)
    return snapshots


def detect_changed_files(initial_snapshot: Dict[str, Tuple[float, int]], cwd: str, snapshot_fn=None) -> List[str]:
    """Identify files modified or created during execution, including re-modified dirty files."""
    s_fn = snapshot_fn or _snapshot_file_states
    current_snapshot = s_fn(cwd)
    newly_changed = [
        p for p, st in current_snapshot.items()
        if p not in initial_snapshot or initial_snapshot[p] != st
    ]
    return sorted(newly_changed)


class ExecutorStatus(str, Enum):
    """Normalized execution status schema."""
    SUCCESS = "SUCCESS"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"
    TIMEOUT = "TIMEOUT"
    CANCELLED = "CANCELLED"


class ExecutorResult(BaseModel):
    """Normalized result returned by any executor engine conforming to Section 6 schema."""
    success: bool = True
    executor_name: str
    status: ExecutorStatus = ExecutorStatus.SUCCESS
    summary: str = ""
    output: str = ""
    error: Optional[str] = None
    exit_code: int = 0
    duration_seconds: float = 0.0
    files_changed: List[str] = Field(default_factory=list)
    tests: Dict[str, Any] = Field(default_factory=dict)
    metrics: Dict[str, float] = Field(default_factory=dict)
    errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    artifacts: List[str] = Field(default_factory=list)
    remaining_risks: List[str] = Field(default_factory=list)
    next_action: Optional[str] = None
    confidence: float = 1.0
    raw_response: Optional[Any] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

    def model_post_init(self, __context: Any) -> None:
        if not self.summary and self.output:
            lines = [l.strip() for l in self.output.splitlines() if l.strip()]
            self.summary = lines[0] if lines else ""
        if self.error and self.error not in self.errors:
            self.errors.append(self.error)
        if not self.success and self.status == ExecutorStatus.SUCCESS:
            self.status = ExecutorStatus.TIMEOUT if self.exit_code == 124 else ExecutorStatus.FAILED
        elif self.success and self.status in (ExecutorStatus.FAILED, ExecutorStatus.TIMEOUT):
            self.status = ExecutorStatus.SUCCESS

    def to_concise_contract(self) -> Dict[str, Any]:
        """Returns concise executor contract complying with Section 23."""
        return {
            "status": self.status.value if isinstance(self.status, ExecutorStatus) else str(self.status),
            "summary": self.summary,
            "files_changed": self.files_changed,
            "tests": self.tests,
            "errors": self.errors,
            "warnings": self.warnings,
            "artifacts": self.artifacts,
            "remaining_risks": self.remaining_risks,
            "next_action": self.next_action,
        }

    def format_concise_contract(self) -> str:
        """Formats concise YAML representation for downstream agents."""
        import yaml
        return yaml.dump(self.to_concise_contract(), sort_keys=False).strip()


class BaseExecutor(ABC):
    """Formalized abstract interface for all Polyphony agent and tool executors."""

    def __init__(self):
        self._active_handles: Dict[str, Any] = {}

    @property
    def _handles(self) -> Dict[str, Any]:
        if not hasattr(self, "_active_handles"):
            self._active_handles = {}
        return self._active_handles

    @property
    @abstractmethod
    def name(self) -> str:
        """Name of the executor adapter (e.g. claude, agy, cursor, python)."""
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Check if the underlying CLI binary or runtime is installed and accessible."""
        pass

    def capabilities(self) -> List[str]:
        """Return declared capabilities of this executor (e.g. code_editing, high_reasoning)."""
        return ["general_execution"]

    def health(self) -> Dict[str, Any]:
        """Check and report health status, version, and connectivity of the executor."""
        avail = self.is_available()
        return {
            "status": "OK" if avail else "UNAVAILABLE",
            "available": avail,
            "details": "Ready" if avail else f"Executor {self.name} is unavailable",
        }

    def start(self, instruction: str, cwd: str, **kwargs) -> str:
        """Initiate execution asynchronously, returning a trackable handle."""
        import uuid
        handle = f"{self.name}-{uuid.uuid4().hex[:8]}"
        res = self.execute(instruction=instruction, cwd=cwd, **kwargs)
        self._handles[handle] = {
            "status": "COMPLETED",
            "result": res,
            "instruction": instruction,
            "cwd": cwd,
        }
        return handle

    def send(self, handle: str, message: str) -> None:
        """Send follow-up instructions or messages to an active execution handle."""
        if handle in self._handles:
            self._handles[handle]["last_message"] = message

    def poll(self, handle: str) -> Dict[str, Any]:
        """Poll lifecycle state of an execution handle."""
        if handle in self._handles:
            item = self._handles[handle]
            return {
                "handle": handle,
                "completed": item.get("status") in ("COMPLETED", "CANCELLED", "FAILED"),
                "status": item.get("status", "RUNNING"),
            }
        return {"handle": handle, "completed": True, "status": "UNKNOWN"}

    def cancel(self, handle: str) -> bool:
        """Cancel an in-flight execution."""
        if handle in self._handles:
            self._handles[handle]["status"] = "CANCELLED"
            return True
        return False

    def collect(self, handle: str) -> ExecutorResult:
        """Collect normalized execution result and free the handle."""
        if handle in self._handles:
            item = self._handles.pop(handle)
            res = item.get("result")
            if res:
                return res
        return ExecutorResult(
            executor_name=self.name,
            success=False,
            status=ExecutorStatus.FAILED,
            error=f"No execution found for handle '{handle}'",
        )

    @abstractmethod
    def execute(
        self,
        instruction: str,
        cwd: str,
        read_only: bool = False,
        timeout_seconds: int = 300,
        model: Optional[str] = None,
        thinking_level: Optional[Any] = None,
        subagents: Optional[Any] = None,
        **kwargs,
    ) -> ExecutorResult:
        """Execute a given instruction inside the target repository working directory."""
        pass
