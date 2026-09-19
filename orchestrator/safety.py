"""Safety policy enforcement engine for ai-orch."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple
from pydantic import BaseModel, Field


class SafetyViolation(Exception):
    """Raised when an operation violates a safety policy."""
    pass


class SafetyConfig(BaseModel):
    """Safety configuration loaded from project.yaml and global.yaml."""
    protected_paths: List[str] = Field(default_factory=lambda: ["database/", "**/database/**"])
    blocked_commands: List[str] = Field(
        default_factory=lambda: [
            "git push",
            "git merge",
            "git add -A",
            "git add .",
            "git add --all",
            "git add -u",
            "git commit -a",
            "git commit -am",
            "rm -rf /",
            "rm -rf ~",
        ]
    )
    require_tests_before_stop: bool = True
    require_approval_for: List[str] = Field(
        default_factory=lambda: [
            "configs/full.yml",
            "tune_level.py --force-full",
            "--force-full",
        ]
    )
    block_ai_attribution: bool = True
    read_only: bool = False


class SafetyEngine:
    """Enforces safety rules across all executors before and during execution."""

    def __init__(self, config: Optional[SafetyConfig] = None, project_root: Optional[str] = None):
        self.config = config or SafetyConfig()
        self.project_root = Path(project_root).resolve() if project_root else None

    def validate_command(self, command: str) -> Tuple[bool, Optional[str]]:
        """Validate whether a shell or CLI command complies with safety policies."""
        cmd_str = command.strip()

        # 1. Check blocked commands
        for blocked in self.config.blocked_commands:
            # Match word boundary or exact token
            pattern = r"(?:^|\s|;|&|\|)" + re.escape(blocked) + r"(?:\s|;|&|\||$)"
            if re.search(pattern, cmd_str):
                return False, f"Blocked by safety policy: command matches blocked pattern '{blocked}'"

        # 2. Check commands requiring explicit approval (e.g. expensive pipeline runs)
        for req in self.config.require_approval_for:
            if req in cmd_str:
                return (
                    False,
                    f"Blocked by safety policy: command requires operator approval ({req}). "
                    f"Full runs must not be triggered autonomously.",
                )

        # 3. Check AI attribution in git commits
        if self.config.block_ai_attribution:
            if "git commit" in cmd_str and "co-authored-by" in cmd_str.lower():
                return False, "Blocked by safety policy: AI attribution in git commits is prohibited."

        # 4. If in read-only mode, block file-modifying tools/commands
        if self.config.read_only:
            write_indicators = ["git commit", "git add", "rm ", "mv ", "sed -i", "echo >", "tee "]
            for ind in write_indicators:
                if ind in cmd_str:
                    return False, f"Blocked: task is running in read-only mode, write command '{ind}' is disallowed."

        return True, None

    def validate_path_modification(self, target_path: str) -> Tuple[bool, Optional[str]]:
        """Validate whether a file path is safe to modify or write to."""
        if self.config.read_only:
            return False, "Blocked: task is running in read-only mode, no file edits allowed."

        # Normalize relative path
        if self.project_root:
            try:
                abs_target = Path(target_path).resolve()
                rel = os.path.relpath(abs_target, self.project_root).lower()
            except Exception:
                rel = target_path.lower()
        else:
            rel = target_path.lower()

        rel_posix = rel.replace("\\", "/")

        for protected in self.config.protected_paths:
            prot_norm = protected.strip("/").lower()
            if rel_posix == prot_norm or rel_posix.startswith(prot_norm + "/") or f"/{prot_norm}/" in f"/{rel_posix}/":
                return (
                    False,
                    f"Blocked by safety policy: '{target_path}' is in protected location '{protected}'.",
                )

        return True, None

    def validate_sqlite_query(self, query: str) -> Tuple[bool, Optional[str]]:
        """Ensure database queries against SQLite are strictly read-only."""
        disallowed = ["insert", "update", "delete", "drop", "alter", "create", "truncate", "replace"]
        q_lower = query.lower()
        for kw in disallowed:
            if re.search(r"\b" + kw + r"\b", q_lower):
                return False, f"Blocked: unsafe SQLite operation '{kw}' detected. Only read-only queries allowed."
        return True, None
