"""Every module in the package must be reachable from an entry point.

The first version of this project had 24 modules that nothing imported.
Their tests passed, so nothing looked wrong. This walks the static import
graph and fails on any module no entry point can reach.
"""

import ast
from pathlib import Path

PKG = Path(__file__).resolve().parents[1] / "polyphony"

# Modules started directly rather than imported: polyphony.cli is the
# console script, polyphony.worker is launched with python -m by jobs.launch.
ENTRY_POINTS = ["polyphony.cli", "polyphony.worker"]


def _module_name(path: Path) -> str:
    parts = list(path.relative_to(PKG.parent).with_suffix("").parts)
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _imports(path: Path, modname: str) -> set[str]:
    is_pkg = path.name == "__init__.py"
    found: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = modname.split(".")
                base = base if is_pkg else base[:-1]
                base = base[: len(base) - (node.level - 1)]
                if node.module:
                    base = base + node.module.split(".")
                module = ".".join(base)
            else:
                module = node.module or ""
            found.add(module)
            found.update(f"{module}.{alias.name}" for alias in node.names)
    return found


def _with_parents(name: str) -> list[str]:
    parts = name.split(".")
    return [".".join(parts[:i]) for i in range(1, len(parts) + 1)]


def test_every_module_is_reachable():
    modules = {_module_name(p): p for p in PKG.rglob("*.py")}
    seen: set[str] = set()
    stack = list(ENTRY_POINTS)
    while stack:
        name = stack.pop()
        for mod in _with_parents(name):
            if mod in modules and mod not in seen:
                seen.add(mod)
                stack.extend(_imports(modules[mod], mod))
    unreachable = sorted(set(modules) - seen)
    assert not unreachable, f"Unreachable from {ENTRY_POINTS}: {unreachable}"
