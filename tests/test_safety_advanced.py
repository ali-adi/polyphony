"""Advanced safety tests verifying resilience against command bypasses and trickery."""

import pytest
from orchestrator.safety import SafetyEngine, SafetyConfig, resolve_safety_config


def test_multispace_git_bypass():
    engine = SafetyEngine()
    ok, reason = engine.validate_command("git   push origin main")
    assert ok is False
    assert "Blocked by safety policy" in reason


def test_git_flag_injection_bypasses():
    engine = SafetyEngine()

    # git --no-pager push
    ok, reason = engine.validate_command("git --no-pager push")
    assert ok is False
    assert "Blocked by safety policy" in reason

    # git -C repo push
    ok, reason = engine.validate_command("git -C /some/repo push origin feature")
    assert ok is False
    assert "Blocked by safety policy" in reason

    # git merge with flags
    ok, reason = engine.validate_command("git -C repo merge master")
    assert ok is False
    assert "Blocked by safety policy" in reason


def test_rm_flag_separation_bypasses():
    engine = SafetyEngine()

    # rm -r -f /
    ok, reason = engine.validate_command("rm -r -f /")
    assert ok is False
    assert "Blocked by safety policy" in reason

    # rm --recursive --force /
    ok, reason = engine.validate_command("rm --recursive --force /")
    assert ok is False
    assert "Blocked by safety policy" in reason

    # rm -rf ~
    ok, reason = engine.validate_command("rm -r -f ~")
    assert ok is False
    assert "Blocked by safety policy" in reason


def test_command_chaining():
    engine = SafetyEngine()

    # Chained with &&
    ok, reason = engine.validate_command("echo 'Building...' && git  push")
    assert ok is False
    assert "Blocked by safety policy" in reason

    # Chained with ;
    ok, reason = engine.validate_command("ls -la; rm -rf /")
    assert ok is False
    assert "Blocked by safety policy" in reason

    # Chained with |
    ok, reason = engine.validate_command("cat file.txt | git push")
    assert ok is False
    assert "Blocked by safety policy" in reason


def test_sqlite_query_safety():
    engine = SafetyEngine()

    # Safe SELECT query
    ok, reason = engine.validate_sqlite_query("SELECT id, name FROM users WHERE active = 1;")
    assert ok is True
    assert reason is None

    # Unsafe queries
    unsafe_queries = [
        "DROP TABLE users;",
        "DELETE FROM records WHERE id = 5;",
        "INSERT INTO logs VALUES ('bad');",
        "UPDATE accounts SET balance = 0;",
        "ALTER TABLE users ADD COLUMN hacked TEXT;",
    ]
    for q in unsafe_queries:
        ok, reason = engine.validate_sqlite_query(q)
        assert ok is False
        assert "unsafe SQLite operation" in reason

    # Invoked via sqlite3 CLI
    ok, reason = engine.validate_command("sqlite3 app.db \"DROP TABLE users;\"")
    assert ok is False
    assert "unsafe SQLite operation" in reason


def test_resolve_safety_config_merging():
    global_cfg = {
        "safety": {
            "enforce_read_only_default": False,
            "block_dangerous_git": True,
            "enforce_verification_tests": True,
            "blocked_global_commands": [
                "rm -rf /",
                "rm -rf ~",
                ":(){ :|:& };:",
                "mkfs",
                "dd if=",
            ],
            "protected_paths": ["secrets/"],
        }
    }
    project_cfg = {
        "safety": {
            "protected_paths": ["database/", "configs/smoke.yml"],
            "blocked_commands": ["git push", "git merge"],
            "require_tests_before_stop": False,
        },
        "git": {
            "block_ai_attribution": True,
        }
    }

    resolved = resolve_safety_config(global_cfg, project_cfg)
    # Check that global blocked commands are present
    assert ":(){ :|:& };:" in resolved.blocked_commands
    assert "mkfs" in resolved.blocked_commands
    assert "git push" in resolved.blocked_commands
    # Check protected paths merged
    assert "database/" in resolved.protected_paths
    assert "secrets/" in resolved.protected_paths
    assert "configs/smoke.yml" in resolved.protected_paths
    # Project-level override for require_tests_before_stop
    assert resolved.require_tests_before_stop is False


def test_rm_flag_exact_matching():
    engine = SafetyEngine()

    # rm with non-recursive flags should not be blocked
    ok, _ = engine.validate_command("rm --preserve-root file.txt")
    assert ok is True

    ok, _ = engine.validate_command("rm -v -i myfile.txt")
    assert ok is True

    # rm with recursive flag on root should be blocked
    ok, reason = engine.validate_command("rm --recursive /")
    assert ok is False
    assert "Blocked by safety policy" in reason

    ok, reason = engine.validate_command("rm -r /")
    assert ok is False
    assert "Blocked by safety policy" in reason


def test_context_aware_validation_prose_vs_shell():
    engine = SafetyEngine(SafetyConfig(read_only=True))

    # Natural language prompt containing words like "touch" or "rm" in prose
    prose = "Please review the code and check where we touch the database or if we need to rm legacy helpers"
    # When is_shell=False (delegated AI prompt), this should pass
    ok, _ = engine.validate_command(prose, is_shell=False)
    assert ok is True

    # When is_shell=True (shell command in read-only), this must be blocked
    ok, reason = engine.validate_command("rm -rf temp.txt", is_shell=True)
    assert ok is False
    assert "read-only mode" in reason


def test_python_executor_interactive_mode(monkeypatch, tmp_path):
    from executors.python_executor import PythonExecutor

    # Test rejection
    monkeypatch.setattr("builtins.input", lambda prompt: "n")
    ex = PythonExecutor(interactive=True)
    res = ex.execute("echo 'hello'", cwd=str(tmp_path))
    assert res.success is False
    assert res.exit_code == 130
    assert "rejected" in res.error

    # Test approval
    monkeypatch.setattr("builtins.input", lambda prompt: "y")
    res_ok = ex.execute("echo 'approved'", cwd=str(tmp_path))
    assert res_ok.success is True
    assert "approved" in res_ok.output

