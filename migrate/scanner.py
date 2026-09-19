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
    category: str     # agent | skill | hook | rule | workflow | setting | mcp | secret | doc | other
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


def _detect_category(rel_path: str, is_dir: bool = False) -> str:
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

    if name.endswith(".mdc"):
        return "rule"

    if name in ("CLAUDE.md", "AGENTS.md", "GEMINI.md", "SKILL.md", "README.md"):
        return "doc"

    return "other"


def scan_project(project_path: str | Path) -> List[ScannedItem]:
    """Scan a project directory for AI configurations across Claude, Cursor, AGY, etc."""
    root = Path(project_path).resolve()
    if not root.exists():
        raise FileNotFoundError(f"Project path does not exist: {root}")

    scanned: List[ScannedItem] = []

    # Directories to specifically look into
    target_dirs = [".claude", ".cursor", ".agents", ".gemini"]
    target_files = [".mcp.json", ".env", "CLAUDE.md", "AGENTS.md", "GEMINI.md", "SKILL.md", "README.md"]

    # 1. Check known top-level files
    for filename in target_files:
        file_path = root / filename
        if file_path.exists() and file_path.is_file():
            scanned.append(
                ScannedItem(
                    rel_path=filename,
                    abs_path=file_path,
                    source_tool=_detect_source_tool(filename),
                    category=_detect_category(filename),
                    size_bytes=file_path.stat().st_size,
                    is_directory=False,
                    description=f"Project-level AI file: {filename}",
                )
            )

    # 2. Walk target AI directories
    for d_name in target_dirs:
        d_path = root / d_name
        if not d_path.exists() or not d_path.is_dir():
            continue

        for dirpath, dirnames, filenames in os.walk(d_path):
            # Skip VCS / node_modules if any inside
            dirnames[:] = [d for d in dirnames if d not in (".git", "node_modules", "__pycache__")]

            cur_path = Path(dirpath)
            for fname in sorted(filenames):
                if fname.startswith(".DS_Store"):
                    continue

                full_file = cur_path / fname
                rel_file = full_file.relative_to(root).as_posix()

                category = _detect_category(rel_file)
                source_tool = _detect_source_tool(rel_file)

                scanned.append(
                    ScannedItem(
                        rel_path=rel_file,
                        abs_path=full_file,
                        source_tool=source_tool,
                        category=category,
                        size_bytes=full_file.stat().st_size,
                        is_directory=False,
                        description=f"{source_tool.title()} {category}: {rel_file}",
                    )
                )

    # 3. Find any other rules or skill files in workspace (e.g. .cursor/rules/*.mdc anywhere or skills/)
    for dirpath, dirnames, filenames in os.walk(root):
        # Exclude common large / build directories
        dirnames[:] = [
            d for d in dirnames
            if d not in (".git", "node_modules", "__pycache__", ".venv", "venv", "env", "dist", "build", ".claude", ".cursor", ".agents", ".gemini")
        ]
        cur_path = Path(dirpath)
        for fname in filenames:
            if fname.endswith(".mdc") or fname in ("CLAUDE.md", "AGENTS.md", "GEMINI.md", "SKILL.md"):
                full_file = cur_path / fname
                rel_file = full_file.relative_to(root).as_posix()
                if not any(item.rel_path == rel_file for item in scanned):
                    scanned.append(
                        ScannedItem(
                            rel_path=rel_file,
                            abs_path=full_file,
                            source_tool=_detect_source_tool(rel_file),
                            category=_detect_category(rel_file),
                            size_bytes=full_file.stat().st_size,
                            is_directory=False,
                            description=f"Workspace rule/doc: {rel_file}",
                        )
                    )

    return sorted(scanned, key=lambda x: (x.source_tool, x.category, x.rel_path))
