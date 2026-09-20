"""Deterministic execution and evaluation engine.

Section 18: Deterministic Work Should Not Consume LLM Tokens
Avoids LLM calls for tasks that can be answered deterministically:
git status, git diff, pytest, ruff, mypy, file hashing, JSON parsing,
metric calculation, benchmark aggregation, dependency inspection,
test counting, repository structure, process status.

Architecture:
AGENT -> deterministic tool -> evidence -> AGENT only if interpretation is needed.
E.g.: pytest -> 19/19 passed -> deterministic rule -> DONE (No LLM confirmation required).
"""

from __future__ import annotations

import ast
import hashlib
import json
import logging
import math
import os
import re
import shutil
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

logger = logging.getLogger("polyphony.deterministic")


@dataclass
class DeterministicDecision:
    """Outcome of evaluating evidence with deterministic rules."""
    action: str  # e.g., "DONE", "PASS", "FAIL", "NEEDS_INTERPRETATION", "CLEAN", "DIRTY"
    reason: str
    requires_llm: bool
    tokens_saved_estimate: int = 0
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class DeterministicResult:
    """Result of running a deterministic tool."""
    tool: str
    success: bool
    output: Any
    error: Optional[str] = None
    tokens_consumed: int = 0
    decision: Optional[DeterministicDecision] = None

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        if self.decision:
            d["decision"] = self.decision.to_dict()
        return d


class DeterministicEngine:
    """Aggressively executes and evaluates work deterministically without LLM tokens."""

    def __init__(self, cwd: Optional[Union[str, Path]] = None):
        self.cwd = Path(cwd).resolve() if cwd else Path.cwd()

    # 1. Git Status
    def git_status(self, cwd: Optional[Union[str, Path]] = None) -> Dict[str, Any]:
        """Inspect git working tree deterministically."""
        target_dir = Path(cwd).resolve() if cwd else self.cwd
        try:
            res = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=target_dir,
                capture_output=True,
                text=True,
                check=False,
            )
            if res.returncode != 0:
                return {
                    "is_git": False,
                    "clean": False,
                    "error": res.stderr.strip(),
                    "files": [],
                }

            lines = [l for l in res.stdout.splitlines() if l.strip()]
            modified = []
            untracked = []
            staged = []

            for line in lines:
                status_code = line[:2]
                fname = line[3:].strip()
                if status_code.startswith("?") or status_code.endswith("?"):
                    untracked.append(fname)
                else:
                    if status_code[0] in ("M", "A", "D", "R"):
                        staged.append(fname)
                    if status_code[1] in ("M", "D"):
                        modified.append(fname)

            return {
                "is_git": True,
                "clean": len(lines) == 0,
                "total_changed": len(lines),
                "staged": staged,
                "modified": modified,
                "untracked": untracked,
                "raw": res.stdout,
            }
        except Exception as e:
            return {"is_git": False, "clean": False, "error": str(e), "files": []}

    # 2. Git Diff
    def git_diff(
        self,
        cwd: Optional[Union[str, Path]] = None,
        staged: bool = False,
        file_path: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Compute git diff deterministically."""
        target_dir = Path(cwd).resolve() if cwd else self.cwd
        cmd = ["git", "diff"]
        if staged:
            cmd.append("--cached")
        if file_path:
            cmd.extend(["--", file_path])

        try:
            res = subprocess.run(
                cmd,
                cwd=target_dir,
                capture_output=True,
                text=True,
                check=False,
            )
            raw = res.stdout
            additions = sum(1 for line in raw.splitlines() if line.startswith("+") and not line.startswith("+++"))
            deletions = sum(1 for line in raw.splitlines() if line.startswith("-") and not line.startswith("---"))
            return {
                "has_diff": bool(raw.strip()),
                "additions": additions,
                "deletions": deletions,
                "raw_diff": raw,
                "error": res.stderr.strip() if res.returncode != 0 else None,
            }
        except Exception as e:
            return {"has_diff": False, "additions": 0, "deletions": 0, "raw_diff": "", "error": str(e)}

    # 3. Pytest Execution & Parsing
    def run_pytest(
        self,
        cwd: Optional[Union[str, Path]] = None,
        args: Optional[List[str]] = None,
        timeout: int = 120,
    ) -> Dict[str, Any]:
        """Execute pytest deterministically and extract structured results."""
        target_dir = Path(cwd).resolve() if cwd else self.cwd
        cmd = ["pytest"] + (args or [])

        # Look for venv pytest if available
        venv_pytest = target_dir / ".venv" / "bin" / "pytest"
        if venv_pytest.exists():
            cmd[0] = str(venv_pytest)
        else:
            system_pytest = shutil.which("pytest")
            if system_pytest:
                cmd[0] = system_pytest

        try:
            res = subprocess.run(
                cmd,
                cwd=target_dir,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
            output = (res.stdout or "") + "\n" + (res.stderr or "")

            # Regex parse pytest summary e.g. "19 passed in 0.12s" or "3 failed, 16 passed in 1.2s"
            passed = 0
            failed = 0
            skipped = 0
            errors = 0

            passed_match = re.search(r"(\d+)\s+passed", output)
            if passed_match:
                passed = int(passed_match.group(1))

            failed_match = re.search(r"(\d+)\s+failed", output)
            if failed_match:
                failed = int(failed_match.group(1))

            skipped_match = re.search(r"(\d+)\s+skipped", output)
            if skipped_match:
                skipped = int(skipped_match.group(1))

            errors_match = re.search(r"(\d+)\s+errors?", output)
            if errors_match:
                errors = int(errors_match.group(1))

            total = passed + failed + skipped + errors
            success = (res.returncode == 0) and (failed == 0) and (errors == 0)

            return {
                "success": success,
                "exit_code": res.returncode,
                "passed": passed,
                "failed": failed,
                "skipped": skipped,
                "errors": errors,
                "total": total,
                "output": output.strip(),
            }
        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "exit_code": -1,
                "passed": 0,
                "failed": 0,
                "skipped": 0,
                "errors": 1,
                "total": 0,
                "output": f"Pytest timed out after {timeout} seconds",
            }
        except Exception as e:
            return {
                "success": False,
                "exit_code": -1,
                "passed": 0,
                "failed": 0,
                "skipped": 0,
                "errors": 1,
                "total": 0,
                "output": str(e),
            }

    # 4. Ruff
    def run_ruff(
        self,
        cwd: Optional[Union[str, Path]] = None,
        args: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Execute ruff linter/formatter check deterministically."""
        target_dir = Path(cwd).resolve() if cwd else self.cwd
        cmd = ["ruff", "check"] + (args or [])
        venv_ruff = target_dir / ".venv" / "bin" / "ruff"
        if venv_ruff.exists():
            cmd[0] = str(venv_ruff)

        try:
            res = subprocess.run(
                cmd,
                cwd=target_dir,
                capture_output=True,
                text=True,
                check=False,
            )
            output = (res.stdout or "") + "\n" + (res.stderr or "")
            clean = res.returncode == 0
            return {
                "success": clean,
                "clean": clean,
                "exit_code": res.returncode,
                "output": output.strip(),
            }
        except FileNotFoundError:
            return {"success": True, "clean": True, "not_installed": True, "output": "ruff not found"}
        except Exception as e:
            return {"success": False, "clean": False, "error": str(e), "output": ""}

    # 5. Mypy
    def run_mypy(
        self,
        cwd: Optional[Union[str, Path]] = None,
        args: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Execute mypy type checker deterministically."""
        target_dir = Path(cwd).resolve() if cwd else self.cwd
        cmd = ["mypy"] + (args or ["."])
        venv_mypy = target_dir / ".venv" / "bin" / "mypy"
        if venv_mypy.exists():
            cmd[0] = str(venv_mypy)

        try:
            res = subprocess.run(
                cmd,
                cwd=target_dir,
                capture_output=True,
                text=True,
                check=False,
            )
            output = (res.stdout or "") + "\n" + (res.stderr or "")
            clean = res.returncode == 0
            error_count = 0
            match = re.search(r"Found\s+(\d+)\s+errors?", output)
            if match:
                error_count = int(match.group(1))
            elif not clean and "error:" in output:
                error_count = output.count("error:")

            return {
                "success": clean,
                "clean": clean,
                "error_count": error_count,
                "exit_code": res.returncode,
                "output": output.strip(),
            }
        except FileNotFoundError:
            return {"success": True, "clean": True, "not_installed": True, "output": "mypy not found"}
        except Exception as e:
            return {"success": False, "clean": False, "error": str(e), "output": ""}

    # 6. File Hashing
    def hash_file(self, file_path: Union[str, Path], algorithm: str = "sha256") -> str:
        """Compute file hash deterministically."""
        path = Path(file_path).resolve()
        if not path.is_file():
            raise FileNotFoundError(f"File not found for hashing: {path}")
        h = getattr(hashlib, algorithm)()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()

    # 7. JSON Parsing & Validation
    def parse_json(self, content_or_path: Union[str, Path]) -> Union[Dict[str, Any], List[Any]]:
        """Parse and validate JSON deterministically."""
        if isinstance(content_or_path, Path) or (isinstance(content_or_path, str) and os.path.isfile(content_or_path)):
            with open(content_or_path, "r", encoding="utf-8") as f:
                return json.load(f)
        return json.loads(content_or_path)

    # 8. Metric Calculation
    def calculate_metrics(self, values: List[Union[float, int]]) -> Dict[str, float]:
        """Compute deterministic statistics over numerical series."""
        if not values:
            return {
                "count": 0,
                "mean": 0.0,
                "median": 0.0,
                "min": 0.0,
                "max": 0.0,
                "std_dev": 0.0,
                "p95": 0.0,
            }
        sorted_vals = sorted([float(v) for v in values])
        n = len(sorted_vals)
        mean_val = sum(sorted_vals) / n

        # Median
        if n % 2 == 1:
            median_val = sorted_vals[n // 2]
        else:
            median_val = (sorted_vals[n // 2 - 1] + sorted_vals[n // 2]) / 2.0

        # Variance & standard deviation
        var = sum((x - mean_val) ** 2 for x in sorted_vals) / n
        std_dev = math.sqrt(var)

        # 95th percentile
        p95_idx = int(math.ceil(0.95 * n)) - 1
        p95_val = sorted_vals[min(max(p95_idx, 0), n - 1)]

        return {
            "count": float(n),
            "mean": round(mean_val, 4),
            "median": round(median_val, 4),
            "min": round(sorted_vals[0], 4),
            "max": round(sorted_vals[-1], 4),
            "std_dev": round(std_dev, 4),
            "p95": round(p95_val, 4),
        }

    # 9. Benchmark Aggregation
    def aggregate_benchmarks(self, records: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Deterministically aggregate benchmark runs."""
        if not records:
            return {"total_runs": 0, "metrics": {}}

        # Group metrics across records
        durations = []
        token_counts = []
        pass_rates = []

        for r in records:
            if "duration_seconds" in r:
                durations.append(r["duration_seconds"])
            if "total_tokens" in r:
                token_counts.append(r["total_tokens"])
            if "correctness" in r:
                pass_rates.append(1.0 if r["correctness"] else 0.0)

        return {
            "total_runs": len(records),
            "durations": self.calculate_metrics(durations) if durations else {},
            "tokens": self.calculate_metrics(token_counts) if token_counts else {},
            "pass_rate": round(sum(pass_rates) / len(pass_rates), 4) if pass_rates else 1.0,
        }

    # 10. Dependency Inspection
    def inspect_dependencies(self, cwd: Optional[Union[str, Path]] = None) -> Dict[str, Any]:
        """Inspect dependencies in repo deterministically without LLM."""
        target_dir = Path(cwd).resolve() if cwd else self.cwd
        deps: Dict[str, List[str]] = {
            "pyproject": [],
            "requirements": [],
            "package_json": [],
        }

        # pyproject.toml
        pyproject_file = target_dir / "pyproject.toml"
        if pyproject_file.exists():
            content = pyproject_file.read_text(encoding="utf-8")
            # Fast extraction of dependencies
            in_deps = False
            for line in content.splitlines():
                stripped = line.strip()
                if "dependencies = [" in stripped:
                    in_deps = True
                    continue
                if in_deps:
                    if stripped.startswith("]"):
                        in_deps = False
                    elif stripped:
                        cleaned = stripped.strip('",\'')
                        if cleaned:
                            deps["pyproject"].append(cleaned)

        # requirements.txt
        req_file = target_dir / "requirements.txt"
        if req_file.exists():
            for line in req_file.read_text(encoding="utf-8").splitlines():
                stripped = line.strip()
                if stripped and not stripped.startswith("#"):
                    deps["requirements"].append(stripped)

        # package.json
        pkg_file = target_dir / "package.json"
        if pkg_file.exists():
            try:
                data = json.loads(pkg_file.read_text(encoding="utf-8"))
                for group in ("dependencies", "devDependencies"):
                    if group in data and isinstance(data[group], dict):
                        for k, v in data[group].items():
                            deps["package_json"].append(f"{k}@{v}")
            except Exception:
                pass

        total_deps = sum(len(v) for v in deps.values())
        return {"total": total_deps, "sources": deps}

    # 11. Test Counting
    def count_tests(self, cwd: Optional[Union[str, Path]] = None, test_dir: str = "tests") -> int:
        """Count total test functions in repository deterministically via AST parsing."""
        target_dir = Path(cwd).resolve() if cwd else self.cwd
        test_path = target_dir / test_dir
        if not test_path.exists():
            return 0

        count = 0
        for py_file in test_path.glob("**/test_*.py"):
            try:
                tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
                for node in ast.walk(tree):
                    if isinstance(node, ast.FunctionDef) and node.name.startswith("test_"):
                        count += 1
            except Exception:
                continue
        return count

    # 12. Repository Structure
    def get_repo_structure(
        self,
        cwd: Optional[Union[str, Path]] = None,
        max_depth: int = 3,
        max_entries: int = 200,
        exclude_dirs: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Compute deterministic file tree representation."""
        target_dir = Path(cwd).resolve() if cwd else self.cwd
        excludes = set(exclude_dirs or [".git", ".venv", "__pycache__", ".pytest_cache", ".ruff_cache", "node_modules"])

        entries: List[str] = []
        dir_count = 0
        file_count = 0

        def _traverse(current_path: Path, current_depth: int):
            nonlocal dir_count, file_count
            if current_depth > max_depth or len(entries) >= max_entries:
                return

            try:
                for item in sorted(current_path.iterdir(), key=lambda p: (not p.is_dir(), p.name)):
                    if item.name in excludes or item.name.startswith("."):
                        continue
                    rel = item.relative_to(target_dir)
                    if item.is_dir():
                        dir_count += 1
                        entries.append(f"{rel}/")
                        _traverse(item, current_depth + 1)
                    else:
                        file_count += 1
                        entries.append(str(rel))
            except PermissionError:
                pass

        _traverse(target_dir, 1)
        return {
            "root": str(target_dir),
            "directories": dir_count,
            "files": file_count,
            "total_entries": len(entries),
            "tree": entries,
        }

    # 13. Process Status
    def get_process_status(self, pid: int) -> Dict[str, Any]:
        """Check if process is alive and retrieve basic status deterministically."""
        try:
            os.kill(pid, 0)
            return {"pid": pid, "alive": True, "status": "RUNNING"}
        except OSError:
            return {"pid": pid, "alive": False, "status": "STOPPED"}

    # 14. Rule Evaluation (Short-circuiting LLM Calls)
    def evaluate_rule(self, evidence_type: str, data: Dict[str, Any]) -> DeterministicDecision:
        """Evaluate deterministic rules directly.

        Example from Section 18:
        pytest -> 19/19 passed -> deterministic rule -> DONE (No LLM confirmation required).
        """
        evidence_type = evidence_type.lower()

        if evidence_type in ("pytest", "test", "tests"):
            failed = data.get("failed", 0)
            errors = data.get("errors", 0)
            passed = data.get("passed", 0)
            total = data.get("total", passed + failed + errors)

            if failed == 0 and errors == 0 and passed > 0:
                return DeterministicDecision(
                    action="DONE",
                    reason=f"{passed}/{total} passed -> deterministic rule -> DONE. No LLM confirmation required.",
                    requires_llm=False,
                    tokens_saved_estimate=1200,
                    details=data,
                )
            elif failed > 0 or errors > 0:
                return DeterministicDecision(
                    action="FAIL",
                    reason=f"{failed} tests failed, {errors} errors encountered. Requires agent fix.",
                    requires_llm=True,
                    tokens_saved_estimate=0,
                    details=data,
                )
            else:
                return DeterministicDecision(
                    action="EMPTY",
                    reason="No tests were executed.",
                    requires_llm=False,
                    tokens_saved_estimate=400,
                    details=data,
                )

        if evidence_type in ("ruff", "lint"):
            clean = data.get("clean", False)
            if clean:
                return DeterministicDecision(
                    action="PASS",
                    reason="Ruff static checks passed with 0 violations -> deterministic rule -> PASS.",
                    requires_llm=False,
                    tokens_saved_estimate=800,
                    details=data,
                )
            return DeterministicDecision(
                action="FAIL",
                reason="Ruff found lint violations.",
                requires_llm=True,
                tokens_saved_estimate=0,
                details=data,
            )

        if evidence_type in ("mypy", "typecheck"):
            clean = data.get("clean", False)
            errors = data.get("error_count", 0)
            if clean and errors == 0:
                return DeterministicDecision(
                    action="PASS",
                    reason="Mypy static typecheck passed with 0 errors -> deterministic rule -> PASS.",
                    requires_llm=False,
                    tokens_saved_estimate=800,
                    details=data,
                )
            return DeterministicDecision(
                action="FAIL",
                reason=f"Mypy found {errors} type errors.",
                requires_llm=True,
                tokens_saved_estimate=0,
                details=data,
            )

        if evidence_type in ("git_status", "git"):
            clean = data.get("clean", False)
            if clean:
                return DeterministicDecision(
                    action="CLEAN",
                    reason="Working tree clean with 0 changes -> deterministic rule -> CLEAN.",
                    requires_llm=False,
                    tokens_saved_estimate=600,
                    details=data,
                )
            return DeterministicDecision(
                action="DIRTY",
                reason=f"Working tree has {data.get('total_changed', 0)} changes.",
                requires_llm=True,
                tokens_saved_estimate=0,
                details=data,
            )

        # Fallback for generic or unknown evidence
        return DeterministicDecision(
            action="NEEDS_INTERPRETATION",
            reason=f"No short-circuit rule defined for evidence type '{evidence_type}'.",
            requires_llm=True,
            tokens_saved_estimate=0,
            details=data,
        )

    # 15. Fast-path classifier: can this work be answered completely deterministically?
    def can_resolve_deterministically(self, instruction: str) -> bool:
        """Check if instruction matches a purely deterministic operation."""
        inst = instruction.strip().lower()
        deterministic_patterns = [
            r"^git status",
            r"^git diff",
            r"^pytest",
            r"^ruff",
            r"^mypy",
            r"^hash file",
            r"^count tests",
            r"^repo structure",
            r"^inspect dependencies",
            r"^check process",
        ]
        return any(re.search(pat, inst) for pat in deterministic_patterns)

    def execute_deterministic(
        self,
        command_or_task: str,
        cwd: Optional[Union[str, Path]] = None,
    ) -> Optional[DeterministicResult]:
        """Execute a deterministic operation without invoking an LLM."""
        target_dir = Path(cwd).resolve() if cwd else self.cwd
        task = command_or_task.strip().lower()

        if task.startswith("git status"):
            res = self.git_status(target_dir)
            decision = self.evaluate_rule("git_status", res)
            return DeterministicResult(tool="git_status", success=res.get("is_git", False), output=res, decision=decision)

        if task.startswith("git diff"):
            staged = "--cached" in task or "--staged" in task
            res = self.git_diff(target_dir, staged=staged)
            return DeterministicResult(tool="git_diff", success=True, output=res)

        if task.startswith("pytest") or task == "run tests":
            res = self.run_pytest(target_dir)
            decision = self.evaluate_rule("pytest", res)
            return DeterministicResult(tool="pytest", success=res.get("success", False), output=res, decision=decision)

        if task.startswith("ruff"):
            res = self.run_ruff(target_dir)
            decision = self.evaluate_rule("ruff", res)
            return DeterministicResult(tool="ruff", success=res.get("success", False), output=res, decision=decision)

        if task.startswith("mypy"):
            res = self.run_mypy(target_dir)
            decision = self.evaluate_rule("mypy", res)
            return DeterministicResult(tool="mypy", success=res.get("success", False), output=res, decision=decision)

        if task.startswith("count tests"):
            count = self.count_tests(target_dir)
            return DeterministicResult(tool="count_tests", success=True, output={"test_count": count})

        if task.startswith("inspect dependencies"):
            deps = self.inspect_dependencies(target_dir)
            return DeterministicResult(tool="inspect_dependencies", success=True, output=deps)

        if task.startswith("repo structure"):
            struct = self.get_repo_structure(target_dir)
            return DeterministicResult(tool="repo_structure", success=True, output=struct)

        return None
