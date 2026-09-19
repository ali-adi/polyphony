"""Base abstract class and result models for execution adapters."""

from __future__ import annotations

from abc import ABC, abstractmethod
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


class ExecutorResult(BaseModel):
    """Normalized result returned by any executor engine."""
    success: bool
    executor_name: str
    output: str = ""
    error: Optional[str] = None
    exit_code: int = 0
    duration_seconds: float = 0.0
    files_changed: List[str] = Field(default_factory=list)
    metrics: Dict[str, float] = Field(default_factory=dict)
    raw_response: Optional[Any] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class BaseExecutor(ABC):
    """Abstract interface for all agent executors."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Name of the executor adapter (e.g. claude, agy, cursor, python)."""
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Check if the underlying CLI binary or runtime is installed and accessible."""
        pass

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
