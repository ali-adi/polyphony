"""Scanner for discovering AI configuration files across different tools and frameworks."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional


@dataclass
class ScannedItem:
    rel_path: str
    abs_path: Path
    source_tool: str  # claude | cursor | antigravity | mcp | generic
    category: str     # agent | skill | hook | rule | workflow | setting | mcp | secret | doc | convention
    size_bytes: int
    is_directory: bool = False
    description: str = ""
    metadata: dict = field(default_factory=dict)


def _detect_source_tool(rel_path: str) -> str:
    parts = Path(rel_path).parts
    if not parts:
        return "generic"
    top = parts[0]
    if top == ".claude":
        return "claude"
    if top == ".cursor":
        return "cursor"
    if top in (".agents", ".gemini"):
        return "antigravity"
    if top == ".mcp.json":
        return "mcp"
    return "generic"


def _detect_category(rel_path: str) -> str:
    p = Path(rel_path)
    name = p.name
    parts = p.parts

    if name in (".env", ".env.local", ".env.production", ".env.development"):
        return "secret"

    if name == ".mcp.json":
        return "mcp"

    if name in ("settings.json", "settings.local.json", "hooks.json"):
        return "setting"

    if len(parts) > 1:
        parent = parts[1]
        if parent == "agents":
            return "agent"
        if parent == "skills":
            return "skill"
        if parent == "hooks":
            return "hook"
        if parent == "workflows":
            return "workflow"
        if parent == "rules":
            return "rule"

    if name.endswith(".mdc") or "rules" in parts:
        return "rule"

    if "runbook" in name.lower() or "convention" in name.lower() or "style" in name.lower() or "guideline" in name.lower():
        return "convention"

    if name in ("CLAUDE.md", "AGENTS.md", "GEMINI.md", "SKILL.md", "README.md"):
        return "doc"

    return "doc" if name.endswith(".md") else "other"


def scan_project(project_path: str | Path) -> List[ScannedItem]:
    """Scan a project directory for genuine AI configurations, ignoring worktrees and caches."""
    root = Path(project_path).resolve()
    if not root.exists():
        raise FileNotFoundError(f"Project path does not exist: {root}")

    scanned: List[ScannedItem] = []
    seen_paths = set()

    def add_item(rel_p: str, abs_p: Path, desc: str = ""):
        if rel_p in seen_paths:
            return
        if not abs_p.exists() or abs_p.is_dir():
            return
        seen_paths.add(rel_p)
        cat = _detect_category(rel_p)
        tool = _detect_source_tool(rel_p)
        scanned.append(
            ScannedItem(
                rel_path=rel_p,
                abs_path=abs_p,
                source_tool=tool,
                category=cat,
                size_bytes=abs_p.stat().st_size,
                description=desc or f"{tool.title()} {cat}: {rel_p}",
            )
        )

    # 1. Known top-level files
    target_files = [".mcp.json", ".env", "CLAUDE.md", "AGENTS.md", "GEMINI.md", "SKILL.md", "README.md"]
    for fname in target_files:
        fpath = root / fname
        if fpath.exists() and fpath.is_file():
            add_item(fname, fpath, f"Top-level {fname}")

    # 2. Walk AI directories: .claude, .cursor, .agents, .gemini
    target_dirs = [".claude", ".cursor", ".agents"]
    ignore_dirs = {
        ".git",
        "node_modules",
        "__pycache__",
        ".venv",
        "venv",
        "env",
        "worktrees",  # Critical: never scan worktrees
        ".pytest_cache",
        "dist",
        "build",
    }

    for d_name in target_dirs:
        d_path = root / d_name
        if not d_path.exists() or not d_path.is_dir():
            continue

        for dirpath, dirnames, filenames in os.walk(d_path):
            # Prune ignored subdirectories in-place
            dirnames[:] = [d for d in dirnames if d not in ignore_dirs and not d.startswith(".")]

            # Double check path parts
            path_parts = Path(dirpath).parts
            if any(part in ignore_dirs for part in path_parts):
                continue

            cur_path = Path(dirpath)
            for fname in sorted(filenames):
                if fname.startswith(".DS_Store") or fname.endswith(".pyc"):
                    continue
                full_file = cur_path / fname
                rel_file = full_file.relative_to(root).as_posix()
                add_item(rel_file, full_file)

    # 3. Targeted project conventions / runbooks / guidelines in docs/ or tuning/
    doc_dirs = ["docs", "tuning"]
    for d_name in doc_dirs:
        d_path = root / d_name
        if not d_path.exists():
            continue
        for dirpath, dirnames, filenames in os.walk(d_path):
            dirnames[:] = [d for d in dirnames if d not in ignore_dirs and not d.startswith(".")]
            cur_path = Path(dirpath)
            for fname in sorted(filenames):
                if "runbook" in fname.lower() or "convention" in fname.lower() or "guideline" in fname.lower():
                    full_file = cur_path / fname
                    rel_file = full_file.relative_to(root).as_posix()
                    add_item(rel_file, full_file, f"Project convention/runbook: {rel_file}")

    return sorted(scanned, key=lambda x: (x.source_tool, x.category, x.rel_path))
