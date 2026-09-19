"""Unit tests for models, thinking levels, and subagent policies configuration."""

import json
from unittest.mock import patch
import pytest

from orchestrator.models_config import (
    map_thinking_to_tokens,
    map_thinking_to_effort,
    resolve_models_config,
    SubagentsPolicy,
    SubagentRoleProfile,
)
from orchestrator.context import build_reasoning_prompt
from orchestrator.state import TaskState
from executors.claude_executor import ClaudeExecutor
from executors.agy_executor import AgyExecutor
from executors.cursor_executor import CursorExecutor
from executors.router import ExecutorRouter


def test_map_thinking_to_tokens():
    assert map_thinking_to_tokens("low") == 2048
    assert map_thinking_to_tokens("medium") == 8192
    assert map_thinking_to_tokens("high") == 16384
    assert map_thinking_to_tokens("max") == 32768
    assert map_thinking_to_tokens(4000) == 4000
    assert map_thinking_to_tokens("5000") == 5000
    assert map_thinking_to_tokens(None) is None


def test_map_thinking_to_effort():
    assert map_thinking_to_effort("low") == "low"
    assert map_thinking_to_effort("medium") == "medium"
    assert map_thinking_to_effort("high") == "high"
    assert map_thinking_to_effort("max") == "high"
    assert map_thinking_to_effort(2000) == "low"
    assert map_thinking_to_effort(10000) == "medium"
    assert map_thinking_to_effort(20000) == "high"
    assert map_thinking_to_effort(None) is None


def test_resolve_models_config_cascading():
    global_cfg = {
        "models": {
            "lead": {
                "claude": {"model": "claude-global-default", "thinking_level": "medium"},
                "agy": {"model": "gemini-global", "thinking_level": "low"},
            },
            "executors": {
                "agy": {"model": "agy-global-exec", "thinking_level": "low"},
                "cursor": {"model": "cursor-global-exec", "thinking_level": "medium"},
            },
            "subagents": {
                "default_model": "subagent-global-default",
                "default_thinking_level": "low",
                "roles": {
                    "reviewer": {"model": "reviewer-global", "thinking_level": "high"}
                }
            }
        }
    }

    # 1. Test global defaults only
    cfg1 = resolve_models_config(global_cfg)
    assert cfg1.lead["claude"].model == "claude-global-default"
    assert cfg1.lead["claude"].thinking_level == "medium"
    assert cfg1.executors["agy"].model == "agy-global-exec"
    assert cfg1.subagents.default_model == "subagent-global-default"
    assert cfg1.subagents.roles["reviewer"].model == "reviewer-global"

    # 2. Test project overrides
    project_cfg = {
        "models": {
            "lead": {
                "claude": {"model": "claude-project-override", "thinking_level": "high"},
            },
            "executors": {
                "agy": {"model": "agy-project-override"},
            },
            "subagents": {
                "roles": {
                    "tester": {"model": "tester-project-model", "thinking_level": "low"}
                }
            }
        }
    }
    cfg2 = resolve_models_config(global_cfg, project_cfg)
    assert cfg2.lead["claude"].model == "claude-project-override"
    assert cfg2.lead["claude"].thinking_level == "high"
    assert cfg2.executors["agy"].model == "agy-project-override"
    # Fallback to global where not overridden in project
    assert cfg2.executors["cursor"].model == "cursor-global-exec"
    assert cfg2.subagents.roles["reviewer"].model == "reviewer-global"
    assert cfg2.subagents.roles["tester"].model == "tester-project-model"

    # 3. Test CLI overrides (highest precedence)
    cli_overrides = {
        "lead_model": "claude-cli-flag",
        "lead_thinking": "max",
        "executor_model": "executor-cli-flag",
        "subagent_model": "subagent-cli-flag",
    }
    cfg3 = resolve_models_config(global_cfg, project_cfg, cli_overrides)
    assert cfg3.lead["claude"].model == "claude-cli-flag"
    assert cfg3.lead["claude"].thinking_level == "max"
    assert cfg3.executors["agy"].model == "executor-cli-flag"
    assert cfg3.subagents.default_model == "subagent-cli-flag"


def test_subagents_policy_to_claude_agents_json():
    policy = SubagentsPolicy(
        default_model="gemini-flash",
        roles={
            "reviewer": SubagentRoleProfile(
                model="claude-3-7-sonnet",
                description="Performs code reviews",
                prompt="You are a strict code reviewer",
            ),
            "tester": SubagentRoleProfile(
                model="claude-3-5-haiku",
                description="Runs tests",
            ),
        }
    )
    agents_json_str = policy.to_claude_agents_json()
    assert agents_json_str is not None
    data = json.loads(agents_json_str)
    assert data["reviewer"]["model"] == "claude-3-7-sonnet"
    assert data["reviewer"]["description"] == "Performs code reviews"
    assert data["tester"]["model"] == "claude-3-5-haiku"


def test_claude_executor_flags(tmp_path):
    claude_ex = ClaudeExecutor(binary_path="/dummy/claude")
    subagents = SubagentsPolicy(
        roles={"reviewer": SubagentRoleProfile(model="claude-opus", description="Audit")}
    )

    with patch("pathlib.Path.exists", return_value=True), \
         patch("executors.claude_executor._get_changed_files_via_git", return_value=[]), \
         patch("subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = "Execution complete"
        mock_run.return_value.stderr = ""

        res = claude_ex.execute(
            instruction="Fix issue",
            cwd=str(tmp_path),
            model="claude-3-7-sonnet",
            thinking_level="high",
            subagents=subagents,
        )

        assert res.success is True
        args, kwargs = mock_run.call_args
        cmd = args[0]
        assert "--model" in cmd
        assert cmd[cmd.index("--model") + 1] == "claude-3-7-sonnet"
        assert "--agents" in cmd
        assert "reviewer" in cmd[cmd.index("--agents") + 1]
        assert kwargs["env"]["MAX_THINKING_TOKENS"] == "16384"


def test_agy_executor_flags(tmp_path):
    agy_ex = AgyExecutor(binary_path="/dummy/agy")

    with patch("pathlib.Path.exists", return_value=True), \
         patch("executors.agy_executor._get_changed_files_via_git", return_value=[]), \
         patch("subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = "Agy done"
        mock_run.return_value.stderr = ""

        res = agy_ex.execute(
            instruction="Implement feature",
            cwd=str(tmp_path),
            model="gemini-3.1-pro-high",
            thinking_level="high",
        )

        assert res.success is True
        args, kwargs = mock_run.call_args
        cmd = args[0]
        assert "--model" in cmd
        assert cmd[cmd.index("--model") + 1] == "gemini-3.1-pro-high"
        assert "--effort" in cmd
        assert cmd[cmd.index("--effort") + 1] == "high"


def test_cursor_executor_flags(tmp_path):
    cursor_ex = CursorExecutor(binary_path="/dummy/cursor")
    cursor_ex._is_agent_ready = True

    with patch("pathlib.Path.exists", return_value=True), \
         patch("executors.cursor_executor._get_changed_files_via_git", return_value=[]), \
         patch("subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = "Cursor complete"
        mock_run.return_value.stderr = ""

        res = cursor_ex.execute(
            instruction="Refactor code",
            cwd=str(tmp_path),
            model="claude-3.7-sonnet",
        )

        assert res.success is True
        args, kwargs = mock_run.call_args
        cmd = args[0]
        assert "--model" in cmd
        assert cmd[cmd.index("--model") + 1] == "claude-3.7-sonnet"


def test_router_with_models_config(tmp_path):
    router = ExecutorRouter()
    global_cfg = {
        "models": {
            "executors": {
                "agy": {"model": "gemini-for-agy", "thinking_level": "medium"},
                "cursor": {"model": "claude-for-cursor", "thinking_level": "high"},
            }
        }
    }
    models_cfg = resolve_models_config(global_cfg)

    # Mock executors
    with patch.object(router, "get_executor") as mock_get_ex:
        mock_candidate = patch("executors.base.BaseExecutor").start()
        mock_candidate.is_available.return_value = True
        mock_candidate.execute.return_value.success = True
        mock_candidate.execute.return_value.error = None
        mock_candidate.execute.return_value.output = "Success"
        mock_candidate.execute.return_value.exit_code = 0
        mock_candidate.execute.return_value.files_changed = []
        mock_get_ex.return_value = mock_candidate

        res, used = router.execute(
            target_executor="agy",
            instruction="Do something",
            cwd=str(tmp_path),
            models_config=models_cfg,
        )

        assert res.success is True
        assert used == "agy"
        _, call_kwargs = mock_candidate.execute.call_args
        assert call_kwargs["model"] == "gemini-for-agy"
        assert call_kwargs["thinking_level"] == "medium"


def test_context_build_reasoning_prompt_includes_models():
    state = TaskState(
        task_id="task-test",
        project_name="medicoder",
        project_path="/tmp/medicoder",
        goal="Test goal",
    )
    knowledge = {"name": "medicoder"}
    global_cfg = {
        "models": {
            "lead": {"claude": {"model": "claude-3-7-sonnet", "thinking_level": "high"}},
            "executors": {"agy": {"model": "gemini-3.8-flash", "thinking_level": "low"}},
            "subagents": {
                "default_model": "subagent-flash",
                "roles": {"reviewer": {"model": "claude-reviewer", "description": "Review code"}}
            }
        }
    }
    models_cfg = resolve_models_config(global_cfg)
    prompt = build_reasoning_prompt(state, knowledge, ["agy", "cursor"], models_config=models_cfg)

    assert "Active Model & Thinking Configuration" in prompt
    assert "claude-3-7-sonnet" in prompt
    assert "gemini-3.8-flash" in prompt
    assert "subagent-flash" in prompt
    assert "claude-reviewer" in prompt
