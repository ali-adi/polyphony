"""Safety policy enforcement engine for Polyphony."""

from __future__ import annotations

import fnmatch
import os
import re
import shlex
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from pydantic import BaseModel, Field


class SafetyViolation(Exception):
    """Raised when an operation violates a safety policy."""
    pass


class SafetyConfig(BaseModel):
    """Safety configuration loaded from project.yaml and global.yaml."""
    protected_paths: List[str] = Field(default_factory=list)
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
    require_approval_for: List[str] = Field(default_factory=list)
    block_ai_attribution: bool = True
    read_only: bool = False
    isolate_git_branch: bool = False
    max_cost_usd: Optional[float] = None


def resolve_safety_config(
    global_cfg: Optional[Dict[str, Any]] = None,
    project_cfg: Optional[Dict[str, Any]] = None,
    read_only: bool = False,
) -> SafetyConfig:
    """Merge safety configuration from global.yaml and project.yaml."""
    global_cfg = global_cfg or {}
    project_cfg = project_cfg or {}

    g_safety = global_cfg.get("safety", {})
    p_safety = project_cfg.get("safety", {})
    p_git = project_cfg.get("git", {})

    # 1. Blocked commands merge
    blocked = list(p_safety.get("blocked_commands", []))
    for g_cmd in g_safety.get("blocked_global_commands", []):
        if g_cmd not in blocked:
            blocked.append(g_cmd)

    if not blocked:
        # Defaults
        blocked = [
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
            ":(){ :|:& };:",
            "mkfs",
            "dd if=",
        ]
    else:
        # Ensure critical dangerous commands from global are present if block_dangerous_git is on
        if g_safety.get("block_dangerous_git", True):
            dangerous_git = ["git push", "git merge"]
            for dg in dangerous_git:
                if dg not in blocked:
                    blocked.append(dg)

    # 2. Protected paths merge
    protected = list(p_safety.get("protected_paths", []))
    for g_prot in g_safety.get("protected_paths", []):
        if g_prot not in protected:
            protected.append(g_prot)

    # 3. Require tests before stop
    req_tests = p_safety.get(
        "require_tests_before_stop",
        g_safety.get("enforce_verification_tests", True),
    )

    # 4. Approval list
    approvals = list(p_safety.get("require_approval_for", []))
    for g_app in g_safety.get("require_approval_for", []):
        if g_app not in approvals:
            approvals.append(g_app)

    # 5. Read-only mode
    enforce_ro = read_only or g_safety.get("enforce_read_only_default", False)

    # 6. Block AI attribution & branch isolation
    block_attrib = p_git.get("block_ai_attribution", True)
    isolate_branch = p_git.get("isolate_branch", False) or g_safety.get("isolate_git_branch", False)

    # 7. Max cost budget
    max_cost = p_safety.get("max_cost_usd", g_safety.get("max_cost_usd", None))
    if max_cost is not None:
        try:
            max_cost = float(max_cost)
        except (ValueError, TypeError):
            max_cost = None

    return SafetyConfig(
        protected_paths=protected,
        blocked_commands=blocked,
        require_tests_before_stop=req_tests,
        require_approval_for=approvals,
        block_ai_attribution=block_attrib,
        read_only=enforce_ro,
        isolate_git_branch=isolate_branch,
        max_cost_usd=max_cost,
    )


class SafetyEngine:
    """Enforces safety rules across all executors before and during execution."""

    def __init__(self, config: Optional[SafetyConfig] = None, project_root: Optional[str] = None):
        self.config = config or SafetyConfig()
        self.project_root = Path(project_root).resolve() if project_root else None

    def _tokenize(self, text: str) -> List[str]:
        """Tokenize text into arguments and shell punctuation."""
        try:
            lexer = shlex.shlex(text, posix=True, punctuation_chars=True)
            lexer.whitespace_split = True
            return list(lexer)
        except Exception:
            return text.strip().split()

    def _split_into_subcommands(self, command: str) -> List[List[str]]:
        """Tokenize and split command line across chaining operators (; && || | &)."""
        tokens = self._tokenize(command)

        subcommands: List[List[str]] = []
        current: List[str] = []
        for t in tokens:
            if t in (";", "&&", "||", "|", "&", "\n"):
                if current:
                    subcommands.append(current)
                    current = []
            else:
                current.append(t)
        if current:
            subcommands.append(current)

        return subcommands

    def validate_command(self, command: str, is_shell: bool = True) -> Tuple[bool, Optional[str]]:
        """Validate whether a shell or CLI command complies with safety policies."""
        cmd_str = command.strip()
        if not cmd_str:
            return True, None

        # 1. Check commands requiring explicit approval (e.g. expensive pipeline runs)
        for req in self.config.require_approval_for:
            if req in cmd_str:
                return (
                    False,
                    f"Blocked by safety policy: command requires operator approval ({req}). "
                    f"Full runs must not be triggered autonomously.",
                )

        # 2. Check AI attribution in git commits
        if self.config.block_ai_attribution:
            if "git" in cmd_str and "co-authored-by" in cmd_str.lower():
                return False, "Blocked by safety policy: AI attribution in git commits is prohibited."

        # 3. Check read-only mode violations (shell commands)
        if self.config.read_only and is_shell:
            write_indicators = ["git commit", "git add", "git rm", "rm ", "mv ", "sed -i", "echo >", "tee ", "touch "]
            for ind in write_indicators:
                if ind in cmd_str:
                    return False, f"Blocked: task is running in read-only mode, write command '{ind.strip()}' is disallowed."

        # 4. Check raw substring patterns (e.g. fork bombs, raw byte writing)
        raw_signatures = [":(){ :|:& };:", "mkfs", "dd if="]
        for sig in raw_signatures:
            if sig in self.config.blocked_commands or sig in cmd_str:
                if sig in cmd_str:
                    return False, f"Blocked by safety policy: command matches blocked pattern '{sig}'"

        # 5. Tokenized analysis of subcommands (only if executed in a shell environment)
        if not is_shell:
            return True, None

        subcommands = self._split_into_subcommands(cmd_str)
        for sub_tokens in subcommands:
            if not sub_tokens:
                continue

            # Normalized subcmd string
            sub_str = " ".join(sub_tokens)

            # Check if any configured blocked command is an exact or subsequence match
            for blocked in self.config.blocked_commands:
                b_tokens = self._tokenize(blocked)
                if not b_tokens:
                    continue

                # Check contiguous token subsequence
                b_len = len(b_tokens)
                for i in range(len(sub_tokens) - b_len + 1):
                    if sub_tokens[i : i + b_len] == b_tokens:
                        return False, f"Blocked by safety policy: command matches blocked pattern '{blocked}'"

            # Check Git commands with flag variations (e.g., git -C repo push, git --no-pager push)
            if sub_tokens[0] == "git":
                git_verdict, git_reason = self._validate_git_tokens(sub_tokens)
                if not git_verdict:
                    return False, git_reason

            # Check rm commands with split flags (e.g., rm -r -f /, rm -rf /)
            if sub_tokens[0] == "rm":
                rm_verdict, rm_reason = self._validate_rm_tokens(sub_tokens)
                if not rm_verdict:
                    return False, rm_reason

            # Check sqlite3 commands for unsafe SQL operations
            if sub_tokens[0] == "sqlite3":
                # Find SQL query argument
                for arg in sub_tokens[1:]:
                    if any(kw in arg.lower() for kw in ["insert", "update", "delete", "drop", "alter", "create"]):
                        safe_sql, sql_reason = self.validate_sqlite_query(arg)
                        if not safe_sql:
                            return False, sql_reason

            # Check redirection or file targeting to protected paths
            for arg in sub_tokens:
                # Remove quotes or redirection operators
                cleaned = arg.lstrip(">").strip()
                if cleaned and any(cleaned.startswith(p.rstrip("/*")) for p in self.config.protected_paths):
                    # If this is a write-like command
                    if sub_tokens[0] in ("rm", "mv", "cp", "touch", "sed", "tee") or ">" in arg:
                        safe_path, path_reason = self.validate_path_modification(cleaned)
                        if not safe_path:
                            return False, path_reason

        return True, None

    def _validate_git_tokens(self, tokens: List[str]) -> Tuple[bool, Optional[str]]:
        """Inspect git subcommands and flags resisting flag injection like -C or --no-pager."""
        flags_with_args = {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path", "--super-prefix"}

        idx = 1
        while idx < len(tokens):
            tok = tokens[idx]
            if tok in flags_with_args:
                idx += 2  # skip flag and its argument
            elif tok.startswith("--") or tok.startswith("-"):
                idx += 1  # boolean flag like --no-pager
            else:
                break

        if idx >= len(tokens):
            return True, None

        subcmd = tokens[idx]
        remaining = tokens[idx + 1 :]

        # 1. Blocked: git push
        if subcmd == "push" and any("git push" in b for b in self.config.blocked_commands):
            return False, "Blocked by safety policy: command matches blocked pattern 'git push'"

        # 2. Blocked: git merge
        if subcmd == "merge" and any("git merge" in b for b in self.config.blocked_commands):
            return False, "Blocked by safety policy: command matches blocked pattern 'git merge'"

        # 3. Blocked: git add bulk staging (-A, ., --all, -u)
        if subcmd == "add":
            bulk_indicators = {"-A", "--all", "-u", "--update", "."}
            if any(tok in bulk_indicators for tok in remaining) and any("git add" in b for b in self.config.blocked_commands):
                return False, "Blocked by safety policy: command matches blocked pattern 'git add -A'"

        # 4. Blocked: git commit automatic staging (-a, -am)
        if subcmd == "commit":
            for r in remaining:
                if r in ("-a", "-am") or (r.startswith("-") and "a" in r):
                    if any("git commit -a" in b or "git commit -am" in b for b in self.config.blocked_commands):
                        return False, "Blocked by safety policy: command matches blocked pattern 'git commit -am'"

        return True, None

    def _validate_rm_tokens(self, tokens: List[str]) -> Tuple[bool, Optional[str]]:
        """Inspect rm flags and arguments resisting split flags like rm -r -f /."""
        has_recursive = False
        has_force = False
        targets: List[str] = []
        end_of_flags = False

        for tok in tokens[1:]:
            if end_of_flags:
                targets.append(tok)
            elif tok == "--":
                end_of_flags = True
            elif tok.startswith("--"):
                if tok in ("--recursive", "-R"):
                    has_recursive = True
                elif tok == "--force":
                    has_force = True
            elif tok.startswith("-") and len(tok) > 1:
                flag_chars = set(tok[1:])
                if "r" in flag_chars or "R" in flag_chars:
                    has_recursive = True
                if "f" in flag_chars:
                    has_force = True
            else:
                targets.append(tok)

        if has_recursive:
            for tgt in targets:
                norm_tgt = tgt.rstrip("/")
                if norm_tgt in ("", "/*") and "/" in tgt:
                    return False, "Blocked by safety policy: command matches blocked pattern 'rm -rf /'"
                if norm_tgt in ("~", "~/*", "$HOME"):
                    return False, "Blocked by safety policy: command matches blocked pattern 'rm -rf ~'"
                # Also check protected paths
                safe_p, p_reason = self.validate_path_modification(tgt)
                if not safe_p:
                    return False, p_reason

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
            # Glob match
            if fnmatch.fnmatch(rel_posix, prot_norm) or fnmatch.fnmatch(rel_posix, f"*/{prot_norm}"):
                return (
                    False,
                    f"Blocked by safety policy: '{target_path}' is in protected location '{protected}'.",
                )
            # Prefix or substring match
            if (
                rel_posix == prot_norm
                or rel_posix.startswith(prot_norm + "/")
                or f"/{prot_norm}/" in f"/{rel_posix}/"
            ):
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
